"""Transforma um lançamento cru em partes (ver app/db.py), ou numa sugestão.

Dois níveis de confiança:

- **automático** (vira partes): só o que é verdade por definição, não por hábito.
  Pagamento de fatura que sai da sua conta; pagamento no cartão que tem esse par
  saindo da conta; Pix no crédito caindo na conta; dinheiro vindo de conta sua;
  taxa da recarga do PicPay no crédito; parcela seguinte de um parcelamento que
  você já classificou; compra em estabelecimento conhecido (regras do sistema).
- **sugestão** (fica pendente, o site oferece num toque): tudo que envolve
  pessoa ou intenção. Pix para ou de alguém, o que você ensinou com "sugerir da próxima vez". O mesmo Pix para a
  mesma pessoa pode ter finalidade diferente; quem confirma é você.

Nada aqui conhece valores ou casos do passado: o que valeu para um lançamento
antigo você classifica nele, sem virar regra.
"""

import json
import re
import sqlite3
import unicodedata

from app.config import settings

EMPRESA = re.compile(r"\b(LTDA|S\.?\s?A\.?|ME|EIRELI|INSTITUICAO|PAGAMENTO|PAGAMENTOS|FUNDACAO|IMOBILIARIA|BANCO|"
                     r"COMERCIO|MARKETPLACE|TECNOLOGIA|SOLUCOES)\b|\d{2}\.\d{3}\.\d{3}", re.I)


def normalizar(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().upper()
    t = re.sub(r"\s*-\s*PARCELA\s+\d+/\d+", "", t)
    t = re.sub(r"\s*-?\s*\d+/\d+\s*$", "", t)        # "... - 2/4" das faturas em CSV
    t = re.sub(r"[^A-Z0-9*]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def chave_regra(descricao: str, contraparte: str) -> str:
    """O que identifica 'o mesmo lugar' para uma sugestão aprendida."""
    base = contraparte if contraparte and len(normalizar(contraparte)) > 3 else f"{descricao} {contraparte}"
    base = re.sub(r"\s-\s.*$", "", base)
    return normalizar(base)[:60]


def e_pessoa(lc: dict) -> bool:
    """Pix ou transferência com pessoa física: a finalidade muda, então só sugestão."""
    return bool(re.match(r"Transfer[êe]ncia (enviada|recebida|Recebida)", lc["descricao"])) and not EMPRESA.search(lc["contraparte"] or "")


def _p(valor, natureza, categoria=None, pessoa=None, obs="", meta=None, motivo=""):
    """Uma parte. `obs` é sua (fica vazia aqui); `motivo` diz por que o sistema classificou ou sugeriu assim."""
    return {"valor": round(valor, 2), "natureza": natureza, "categoria": categoria, "pessoa": pessoa, "meta": meta, "obs": obs,
            "motivo": motivo}


# O que o classificador escrevia na observação antes de existir o campo motivo (db._migrar move para lá).
MOTIVOS_EXATOS = {"pagamento da fatura do cartão", "pagamento da fatura", "aporte na meta", "resgate da meta",
                  "Pix no crédito caindo na conta", "vindo de outra conta sua",
                  "principal: ponte para a fatura, pagamento a alguém ou compra?", "Pix no crédito: principal",
                  "IOF e juro do Pix no crédito", "como da última vez", "sua parte do aluguel", "sugestão pela pessoa (confira)",
                  "pela regra (confira)", "Pix pequeno (confira)"}
MOTIVOS_PADRAO = re.compile(r"^(taxa PicPay no crédito \(.*\)|parte de .+ no boleto|acerto com .+ \(confira\)|[a-z0-9-]+ pagou)$")


def e_motivo(texto: str) -> bool:
    return texto in MOTIVOS_EXATOS or bool(MOTIVOS_PADRAO.match(texto or ""))


def _param(con, chave, padrao):
    row = con.execute("SELECT valor FROM parametros WHERE chave = ?", (chave,)).fetchone()
    return row["valor"] if row else padrao


# ---------------------------------------------------------------------------
# Automático: verdade por definição
# ---------------------------------------------------------------------------
def definicao(con: sqlite3.Connection, lc: dict) -> list[dict] | None:
    d, c, v, conta = lc["descricao"], lc["contraparte"], lc["valor"], lc["conta"]

    # Pagar a fatura com dinheiro da conta é mover dinheiro da conta para o cartão.
    # Quem ajudou a pagar aparece no Pix que entrou, não aqui.
    if conta == "nubank_conta" and d.startswith("Pagamento de fatura"):
        return [_p(v, "transferencia", motivo="pagamento da fatura do cartão")]
    # No cartão, só é transferência se o par saiu da sua conta; senão alguém pagou por você.
    if conta == "nubank_cartao" and re.match(r"Pagamento (em|recebido)", d):
        par = con.execute("SELECT 1 FROM lancamentos WHERE conta='nubank_conta' AND descricao LIKE 'Pagamento de fatura%' "
                          "AND ABS(valor + ?) < 0.005 AND ABS(julianday(data) - julianday(?)) <= 3", (v, lc["data"])).fetchone()
        return [_p(v, "transferencia", motivo="pagamento da fatura")] if par else None
    # Caixinha / RDB do Nubank: dinheiro seu indo para (ou voltando de) uma meta. Qual meta, você diz.
    if conta == "nubank_conta" and re.search(r"Aplica[çc][ãa]o RDB|Resgate RDB|Dinheiro guardado|Dinheiro resgatado|Caixinha", d, re.I):
        unica = con.execute("SELECT id FROM metas WHERE ativa=1").fetchall()
        meta = unica[0]["id"] if len(unica) == 1 else None
        return [_p(v, "poupanca", meta=meta, motivo="aporte na meta" if v < 0 else "resgate da meta")]
    if conta == "nubank_conta" and d.startswith("Valor adicionado"):
        return [_p(v, "transferencia", motivo="Pix no crédito caindo na conta")]
    titular = settings.TITULAR.strip().upper()
    if conta == "nubank_conta" and v > 0 and titular and titular in c.upper():
        return [_p(v, "transferencia", motivo="vindo de outra conta sua")]

    # Parcela seguinte de um parcelamento já classificado: mesma divisão, mesmo destino.
    if lc.get("parcela") and not lc["parcela"].startswith("1/"):
        base = normalizar(d)
        for ant in con.execute("SELECT id, valor FROM lancamentos WHERE conta=? AND parcela IS NOT NULL AND parcela!=? "
                               "AND id != COALESCE(?, -1) ORDER BY data DESC", (conta, lc["parcela"], lc.get("id"))):
            outro = con.execute("SELECT descricao FROM lancamentos WHERE id=?", (ant["id"],)).fetchone()["descricao"]
            if normalizar(outro) != base:
                continue
            partes = [dict(p) for p in con.execute("SELECT valor, natureza, categoria, pessoa, meta, obs FROM partes WHERE lancamento_id=?",
                                                    (ant["id"],))]
            if partes and all((p["natureza"] not in ("gasto", "renda") or p["categoria"]) and (p["natureza"] != "poupanca" or p["meta"])
                              for p in partes) and ant["valor"]:
                f = v / ant["valor"]
                out = [_p(p["valor"] * f, p["natureza"], p["categoria"], p["pessoa"], p["obs"], p["meta"], "igual à parcela anterior")
                       for p in partes]
                out[-1]["valor"] = round(v - sum(p["valor"] for p in out[:-1]), 2)
                return out
            break

    # Recarga ou pagamento via PicPay com o cartão: a taxa é custo; o principal fica para você dizer.
    if conta == "nubank_cartao" and "PICPAY" in f"{d} {c}".upper():
        taxa = float(_param(con, "taxa_ponte_picpay", "0.049"))
        principal = round(v / (1 + taxa), 2)
        return [_p(v - principal, "gasto", "juros", motivo=f"taxa PicPay no crédito ({taxa:.2%})".replace(".", ",")),
                _p(principal, "gasto", None, motivo="principal: ponte para a fatura, pagamento a alguém ou compra?")]

    # Pix no crédito avulso: na fatura sem cartão, casado com o "valor adicionado" na conta.
    if conta == "nubank_cartao" and v < 0 and not lc.get("parcela"):
        pix = con.execute("SELECT valor FROM lancamentos WHERE conta='nubank_conta' AND descricao LIKE 'Valor adicionado%' "
                          "AND julianday(?) - julianday(data) BETWEEN 0 AND 7 AND valor < ? AND valor > ? * 0.75",
                          (lc["data"], -v, -v)).fetchone()
        if pix and (d.startswith("Pix no Crédito") or (re.match(r"^[A-Za-zÀ-ú ]+$", d) and len(d.split()) >= 2)):
            return [_p(-pix["valor"], "transferencia", motivo="Pix no crédito: principal"),
                    _p(v + pix["valor"], "gasto", "juros", motivo="IOF e juro do Pix no crédito")]
    return None


def por_regra_sistema(con: sqlite3.Connection, lc: dict) -> list[dict] | None:
    alvo = normalizar(f"{lc['descricao']} | {lc['contraparte']}")
    for r in con.execute("SELECT padrao, natureza, categoria, pessoa FROM regras WHERE origem='sistema' ORDER BY id"):
        if re.search(r["padrao"], alvo):
            return [_p(lc["valor"], r["natureza"], r["categoria"], r["pessoa"], motivo="estabelecimento conhecido")]
    return None


# ---------------------------------------------------------------------------
# Sugestão: precisa de você
# ---------------------------------------------------------------------------
def sugerir(con: sqlite3.Connection, lc: dict) -> list[dict] | None:
    v = lc["valor"]
    r = con.execute("SELECT natureza, categoria, pessoa FROM regras WHERE origem='aprendida' AND padrao = ?",
                    (chave_regra(lc["descricao"], lc["contraparte"]),)).fetchone()
    if r:
        return [_p(v, r["natureza"], r["categoria"], r["pessoa"], motivo="como da última vez")]
    alvo = f"{lc['descricao']} | {lc['contraparte']}".upper()
    pessoa = con.execute("SELECT * FROM pessoas WHERE apelido_extrato != '' AND ? LIKE '%' || UPPER(apelido_extrato) || '%'",
                         (alvo,)).fetchone()
    if pessoa:
        modo = pessoa["sugere_entrada"] if v > 0 else pessoa["sugere_saida"]
        if modo == "acerto":
            return [_p(v, "acerto", pessoa=pessoa["id"], motivo=f"acerto com {pessoa['nome']} (confira)")]
        natureza, categoria = modo.split(":", 1)
        return [_p(v, natureza, categoria, motivo="sugestão pela pessoa (confira)")]
    if e_pessoa(lc):
        regra = por_regra_sistema(con, lc)    # ex.: Pix para o psicólogo, cota de uma assinatura
        if regra:
            regra[0]["motivo"] = "pela regra (confira)"
            return regra
        if v < 0 and abs(v) < 30:
            return [_p(v, "gasto", "outros", motivo="Pix pequeno (confira)")]
    return None


def classificar(con: sqlite3.Connection, lc: dict) -> tuple[list[dict], list[dict] | None]:
    """(partes automáticas, sugestão). Partes vazias = pendente."""
    auto = definicao(con, lc)
    if auto:
        return auto, None
    sug = sugerir(con, lc)
    if sug or e_pessoa(lc):
        return [], sug
    regra = por_regra_sistema(con, lc)
    return (regra or []), None


def aprender(con: sqlite3.Connection, lc: dict, natureza: str, categoria: str | None, pessoa: str | None) -> str:
    """Guarda a classificação como sugestão para o mesmo lugar. Nunca classifica sozinho."""
    chave = chave_regra(lc["descricao"], lc["contraparte"])
    con.execute(
        "INSERT INTO regras (padrao, natureza, categoria, pessoa, origem) VALUES (?,?,?,?, 'aprendida') "
        "ON CONFLICT(padrao, origem) DO UPDATE SET natureza=excluded.natureza, categoria=excluded.categoria, pessoa=excluded.pessoa",
        (chave, natureza, categoria, pessoa))
    return chave
