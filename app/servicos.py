"""Regras de negócio: importar, casar com o push, classificar à mão e montar o painel."""

import calendar
import hashlib
import json
import sqlite3
from collections import defaultdict
from datetime import date, datetime, timedelta

from app import classificar, db, importadores
from app.db import PENDENTE_SQL


# ---------------------------------------------------------------------------
# Inserção e deduplicação
# ---------------------------------------------------------------------------
def _chave(conta, data, valor, descricao, n) -> str:
    base = f"{conta}|{data}|{valor:.2f}|{classificar.normalizar(descricao)}|{n}"
    return hashlib.sha1(base.encode()).hexdigest()


def inserir(con: sqlite3.Connection, conta, data, valor, descricao, contraparte="", origem="manual", ref="",
            parcela=None, chave=None, partes: list[dict] | None = None, nota="") -> int:
    cur = con.execute(
        "INSERT INTO lancamentos (data, conta, valor, descricao, contraparte, origem, ref, chave, parcela, nota) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        (data, conta, round(valor, 2), descricao, contraparte, origem, ref, chave, parcela, nota))
    lid = cur.lastrowid
    lc = {"id": lid, "data": data, "conta": conta, "valor": round(valor, 2), "descricao": descricao,
          "contraparte": contraparte, "parcela": parcela}
    if partes is None:
        partes, sugestao = classificar.classificar(con, lc)
        if sugestao:
            con.execute("UPDATE lancamentos SET sugestao=? WHERE id=?", (json.dumps(sugestao, ensure_ascii=False), lid))
    db.gravar_partes(con, lid, partes)
    if parcela and conta == "nubank_cartao":
        con.execute("DELETE FROM parcelas_futuras WHERE conta=? AND parcela=? AND ? LIKE '%' || substr(descricao,1,12) || '%'",
                    (conta, parcela, descricao))
    return lid


# Contas que nascem na primeira importação de um banco que ainda não estava aqui.
CONTAS_NOVAS = {"bradesco_conta": ("Bradesco", "corrente"), "bradesco_cartao": ("Cartão Bradesco", "cartao")}


def importar(con: sqlite3.Connection, nome: str, conteudo: bytes, hoje: date | None = None) -> dict:
    lt = importadores.ler_arquivo(nome, conteudo, hoje)
    for cid in {m.conta for m in lt.movimentos} & CONTAS_NOVAS.keys():
        if not con.execute("SELECT 1 FROM contas WHERE id=?", (cid,)).fetchone():
            nome_conta, tipo = CONTAS_NOVAS[cid]
            # O extrato traz o saldo antes do primeiro lançamento; a fatura, a dívida da fatura anterior.
            desde = lt.totais.get("data_saldo_inicial") or min(m.data for m in lt.movimentos if m.conta == cid)
            con.execute("INSERT INTO contas (id, nome, tipo, saldo_inicial, data_saldo_inicial) VALUES (?,?,?,?,?)",
                        (cid, nome_conta, tipo, lt.totais.get("saldo_inicial", 0.0), desde))
    inicio = {r["id"]: r["data_saldo_inicial"] for r in con.execute("SELECT id, data_saldo_inicial FROM contas")}
    novos = casados = repetidos = 0
    vistos: dict[tuple, int] = defaultdict(int)
    for mv in lt.movimentos:
        if mv.data < inicio.get(mv.conta, "0000"):
            continue
        k = (mv.conta, mv.data, round(mv.valor, 2))
        ordem = vistos[k]
        vistos[k] += 1
        # O mesmo movimento já veio de outro arquivo (mesma conta, dia e valor, na mesma ordem)?
        ja = con.execute("SELECT COUNT(*) FROM lancamentos WHERE conta=? AND data=? AND ABS(valor-?)<0.005 "
                         "AND (origem!='push' OR confirmado_por IS NOT NULL)",
                         k).fetchone()[0]
        if ordem < ja:
            repetidos += 1
            continue
        # Chegou antes pelo celular? Então o arquivo só confirma (e detalha) o lançamento do push.
        push = con.execute(
            "SELECT id FROM lancamentos WHERE origem='push' AND confirmado_por IS NULL AND conta=? AND ABS(valor-?)<0.005 "
            "AND ABS(julianday(data)-julianday(?)) <= 2 ORDER BY ABS(julianday(data)-julianday(?)) LIMIT 1",
            (mv.conta, mv.valor, mv.data, mv.data)).fetchone()
        if push:
            con.execute("UPDATE lancamentos SET confirmado_por=?, data=?, contraparte=CASE WHEN contraparte='' THEN ? ELSE contraparte END, "
                        "parcela=COALESCE(parcela, ?) WHERE id=?",
                        (f"{lt.tipo}:{nome}", mv.data, mv.contraparte, mv.parcela, push["id"]))
            casados += 1
            continue
        inserir(con, mv.conta, mv.data, mv.valor, mv.descricao, mv.contraparte, lt.tipo, nome, mv.parcela,
                _chave(mv.conta, mv.data, mv.valor, mv.descricao, ordem))
        novos += 1
    if lt.tipo == "fatura_csv" and lt.movimentos:
        rot = next((a for a in lt.avisos if a.startswith("Fatura com saldo no rotativo")), None)
        db.definir_parametro(con, "rotativo_valor", importadores.numero(rot.split(":")[1]) if rot else 0)
    for f in lt.futuras:
        con.execute("INSERT OR REPLACE INTO parcelas_futuras (conta, mes, descricao, valor, parcela, pessoa) VALUES (?,?,?,?,?,?)",
                    (f["conta"], f["mes"], f["descricao"], f["valor"], f["parcela"],
                     _pessoa_do_parcelamento(con, f["descricao"])))
    con.execute("INSERT INTO importacoes (arquivo, tipo, novos, casados, repetidos) VALUES (?,?,?,?,?)",
                (nome, lt.tipo, novos, casados, repetidos))
    return {"arquivo": nome, "tipo": lt.tipo, "novos": novos, "casados": casados, "repetidos": repetidos,
            "futuras": len(lt.futuras), "avisos": lt.avisos}


# ---------------------------------------------------------------------------
# Leitura
# ---------------------------------------------------------------------------
def _partes(con, ids: list[int]) -> dict[int, list[dict]]:
    out: dict[int, list[dict]] = defaultdict(list)
    if not ids:
        return out
    q = ",".join("?" * len(ids))
    for p in con.execute(f"SELECT * FROM partes WHERE lancamento_id IN ({q}) ORDER BY id", ids):
        out[p["lancamento_id"]].append(dict(p))
    return out


def lancamentos(con, mes=None, busca=None, pendentes=False, categoria=None, limite=500, de=None, ate=None) -> list[dict]:
    cond, args = ["1=1"], []
    corte = dia_corte(con)
    tem_renda = "EXISTS (SELECT 1 FROM partes p WHERE p.lancamento_id=l.id AND p.natureza='renda')"
    # Mês em que a renda do lançamento conta (a mesma regra do painel); o resto conta pela data.
    mes_renda = (f"CASE WHEN {tem_renda} AND CAST(substr(l.data,9,2) AS INTEGER) >= {int(corte)} "
                 "THEN strftime('%Y-%m', l.data, 'start of month', '+1 month') ELSE substr(l.data,1,7) END")
    if mes:
        cond.append(f"(substr(l.data,1,7)=? OR {mes_renda}=?)"); args += [mes, mes]
    if de:
        cond.append("l.data >= ?"); args.append(de)
    if ate:
        cond.append("l.data <= ?"); args.append(ate)
    if busca:
        cond.append("(l.descricao LIKE ? OR l.contraparte LIKE ?)"); args += [f"%{busca}%"] * 2
    if pendentes:
        cond.append(f"({PENDENTE_SQL})")
    if categoria:
        cond.append("EXISTS (SELECT 1 FROM partes p WHERE p.lancamento_id=l.id AND p.categoria=?)"); args.append(categoria)
    rows = [dict(r) for r in con.execute(
        f"SELECT l.*, ({PENDENTE_SQL}) AS pendente, {mes_renda} AS mes_renda FROM lancamentos l WHERE {' AND '.join(cond)} "
        f"ORDER BY l.data DESC, l.id DESC LIMIT ?", args + [limite])]
    ps = _partes(con, [r["id"] for r in rows])
    saldo = _saldo_apos(con)
    for r in rows:
        r["partes"] = ps[r["id"]]
        r["pendente"] = bool(r["pendente"])
        r["sugestao"] = json.loads(r["sugestao"]) if r["sugestao"] else None
        r["saldo_conta"] = saldo.get(r["id"])
    return rows


def _saldo_apos(con) -> dict[int, float]:
    """Saldo da conta logo depois de cada lançamento (a coluna 'Balance' da planilha)."""
    out, acum = {}, {}
    ini = {r["id"]: r["saldo_inicial"] for r in con.execute("SELECT id, saldo_inicial FROM contas")}
    for r in con.execute("SELECT id, conta, valor FROM lancamentos ORDER BY data, id"):
        acum[r["conta"]] = round(acum.get(r["conta"], ini.get(r["conta"], 0.0)) + r["valor"], 2)
        out[r["id"]] = acum[r["conta"]]
    return out


def definir_partes(con, lid: int, partes: list[dict], lembrar: bool, nota: str | None = None) -> dict:
    lc = dict(con.execute("SELECT * FROM lancamentos WHERE id=?", (lid,)).fetchone())
    if nota is not None:
        con.execute("UPDATE lancamentos SET nota=? WHERE id=?", (nota.strip(), lid))
    soma = round(sum(p["valor"] for p in partes), 2)
    if abs(soma - lc["valor"]) > 0.005:
        raise ValueError(f"As partes somam {soma}, o lançamento é {lc['valor']}.")
    for p in partes:
        if p["natureza"] not in db.NATUREZAS:
            raise ValueError(f"Natureza inválida: {p['natureza']}")
        if p["natureza"] in ("gasto", "renda") and not p.get("categoria"):
            raise ValueError("Gasto e renda precisam de categoria.")
        if p["natureza"] == "acerto" and not p.get("pessoa"):
            raise ValueError("Acerto precisa de pessoa.")
        if p["natureza"] == "poupanca" and not p.get("meta"):
            raise ValueError("Poupança precisa de meta.")
    db.gravar_partes(con, lid, partes)
    con.execute("UPDATE lancamentos SET sugestao=NULL WHERE id=?", (lid,))
    regra = None
    if lembrar and len(partes) == 1:
        # Vira sugestão para o mesmo lugar: os outros pendentes passam a oferecê-la, nunca a aplicam.
        p = partes[0]
        regra = classificar.aprender(con, lc, p["natureza"], p.get("categoria"), p.get("pessoa"))
        for o in lancamentos(con, pendentes=True, limite=5000):
            if o["id"] != lid and classificar.chave_regra(o["descricao"], o["contraparte"]) == regra:
                con.execute("UPDATE lancamentos SET sugestao=? WHERE id=?",
                            (json.dumps([{**p, "valor": o["valor"], "obs": "", "motivo": "como da última vez"}], ensure_ascii=False), o["id"]))
    return {"ok": True, "regra": regra}


def saldo_contas(con, ate: str | None = None) -> list[dict]:
    ate = ate or "9999-12-31"
    out = []
    for c in con.execute("SELECT * FROM contas"):
        mov = con.execute("SELECT COALESCE(SUM(valor),0) FROM lancamentos WHERE conta=? AND data>=? AND data<=?",
                          (c["id"], c["data_saldo_inicial"], ate)).fetchone()[0]
        saldo = round(c["saldo_inicial"] + mov, 2)
        # Até onde os arquivos do banco cobrem: depois disso, o calculado pode estar incompleto.
        cobertura = con.execute("SELECT MAX(data) FROM lancamentos WHERE conta=? AND origem IN "
                                "('extrato_pdf','extrato_csv','fatura_pdf','fatura_csv')", (c["id"],)).fetchone()[0]
        real = json.loads(db.parametro(con, f"saldo_real:{c['id']}", "null") or "null")
        item = {**dict(c), "saldo": saldo, "cobertura": cobertura, "saldo_real": None, "diferenca": None}
        if real:
            calc = round(c["saldo_inicial"] + con.execute(
                "SELECT COALESCE(SUM(valor),0) FROM lancamentos WHERE conta=? AND data>=? AND data<=?",
                (c["id"], c["data_saldo_inicial"], real["data"])).fetchone()[0], 2)
            item.update(saldo_real=real["valor"], data_real=real["data"], diferenca=round(real["valor"] - calc, 2))
        out.append(item)
    return out


def informar_saldo(con, conta: str, valor: float, data: str) -> None:
    """O saldo que o app do banco mostra. É a verdade; o calculado só mostra o que falta lançar."""
    db.definir_parametro(con, f"saldo_real:{conta}", json.dumps({"valor": round(valor, 2), "data": data}))


def saldo_pessoas(con) -> list[dict]:
    """Quanto cada pessoa te deve (+) ou você deve a ela (-)."""
    ajuste = json.loads(db.parametro(con, "pessoas_ajuste", '{"data": "2000-01-01", "saldos": {}}'))
    out = []
    for p in con.execute("SELECT * FROM pessoas"):
        mov = con.execute("SELECT COALESCE(SUM(pt.valor),0) FROM partes pt JOIN lancamentos l ON l.id=pt.lancamento_id "
                          "WHERE pt.natureza='acerto' AND pt.pessoa=? AND l.data>?", (p["id"], ajuste["data"])).fetchone()[0]
        futuro = con.execute("SELECT COALESCE(SUM(valor),0) FROM parcelas_futuras WHERE pessoa=?", (p["id"],)).fetchone()[0]
        saldo = round(ajuste["saldos"].get(p["id"], 0.0) - mov, 2)
        out.append({**dict(p), "saldo": saldo, "a_vencer": round(-futuro, 2)})
    return out


def dia_corte(con) -> int:
    """Dia a partir do qual a renda conta para o mês seguinte (salário do fim do mês). Com a opção
    desligada em Ajustes, 32: nenhuma renda muda de mês."""
    if db.parametro(con, "renda_mes_seguinte", "1") != "1":
        return 32
    return int(db.parametro(con, "dia_renda_mes_seguinte", "25") or 25)


def _mes_efetivo(data: str, tipo: str, dia_corte: int) -> str:
    """Renda que cai a partir do dia de corte conta para o mês seguinte (salário do fim do mês)."""
    if tipo == "renda" and int(data[8:10]) >= dia_corte:
        y, m = int(data[:4]), int(data[5:7])
        return f"{y + m // 12}-{m % 12 + 1:02d}"
    return data[:7]


def serie_mensal(con, meses=12) -> list[dict]:
    corte = dia_corte(con)
    tot = defaultdict(lambda: {"renda": 0.0, "gasto": 0.0, "juros": 0.0})
    for r in con.execute("SELECT l.data, pt.natureza, pt.categoria, pt.valor FROM partes pt JOIN lancamentos l ON l.id=pt.lancamento_id "
                         "WHERE pt.natureza IN ('gasto','renda')"):
        m = _mes_efetivo(r["data"], r["natureza"], corte)
        if r["natureza"] == "renda":
            tot[m]["renda"] += r["valor"]
        else:
            tot[m]["gasto"] += -r["valor"]
            if r["categoria"] == "juros":
                tot[m]["juros"] += -r["valor"]
    chaves = sorted(tot)[-meses:]
    return [{"mes": m, **{k: round(v, 2) for k, v in tot[m].items()}, "resultado": round(tot[m]["renda"] - tot[m]["gasto"], 2)}
            for m in chaves]


def itens_fixos(con) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    for i in con.execute("SELECT * FROM itens_fixos ORDER BY ordem, id"):
        out[i["categoria"]].append(dict(i))
    return out


def soma_itens(itens: list[dict], mes: str) -> float:
    return round(sum(i["valor"] for i in itens if _no_intervalo(mes, i["inicio"] or "", i["fim"])), 2)


def orcado(con, meses: list[str]) -> dict[str, dict[str, float | None]]:
    """Orçamento de cada chave (categoria ou 'meta:<id>') em cada mês: o valor do mês, se você definiu, senão o padrão.

    Padrão: gasto = teto, ou a soma das despesas fixas do mês se a categoria orça por itens; salário = renda base;
    outras rendas = nada; meta = aporte mensal (zero se inativa).
    """
    renda_base = float(db.parametro(con, "salario_mensal", "0") or 0)
    itens = itens_fixos(con)
    out: dict[str, dict[str, float | None]] = {}
    for c in con.execute("SELECT id, tipo, teto, orcar_por_itens FROM categorias"):
        if c["tipo"] == "gasto":
            out[c["id"]] = {mes: soma_itens(itens[c["id"]], mes) if c["orcar_por_itens"] else c["teto"] for mes in meses}
        else:
            out[c["id"]] = {mes: renda_base if c["id"] == "salario" else None for mes in meses}
    for m in con.execute("SELECT id, aporte_mensal, ativa FROM metas"):
        out[f"meta:{m['id']}"] = {mes: m["aporte_mensal"] if m["ativa"] else 0.0 for mes in meses}
    if meses:
        q = ",".join("?" * len(meses))
        for r in con.execute(f"SELECT chave, mes, valor FROM orcamento WHERE mes IN ({q})", meses):
            if r["chave"] in out:
                out[r["chave"]][r["mes"]] = r["valor"]
    return out


def _soma_orc(valores: dict[str, float | None], meses: list[str], fator: float) -> float | None:
    vs = [valores.get(m) for m in meses]
    return None if all(v is None for v in vs) else round(sum(v or 0 for v in vs) * fator, 2)


def gastos_por_categoria(con, inicio: str, fim: str, meses_orc: list[str] | None = None, fator: float = 1.0) -> list[dict]:
    """Gasto por categoria entre duas datas, com o orçamento dos meses do período (vezes `fator` na semana).

    Parcela a partir da 2ª é compromisso antigo, não decisão do período: fica em `parcelas`, fora do teto.
    """
    rows = {r["id"]: {**dict(r), "gasto": 0.0, "parcelas": 0.0, "n": 0}
            for r in con.execute("SELECT * FROM categorias WHERE tipo='gasto' ORDER BY ordem")}
    for r in con.execute("SELECT pt.categoria, pt.valor, l.parcela FROM partes pt JOIN lancamentos l ON l.id=pt.lancamento_id "
                         "WHERE pt.natureza='gasto' AND pt.categoria IS NOT NULL AND l.data BETWEEN ? AND ?", (inicio, fim)):
        antiga = bool(r["parcela"]) and not r["parcela"].startswith("1/")
        rows[r["categoria"]]["parcelas" if antiga else "gasto"] += -r["valor"]
        rows[r["categoria"]]["n"] += 1
    meses_orc = meses_orc or [inicio[:7]]
    orc = orcado(con, meses_orc)
    for v in rows.values():
        v["gasto"], v["parcelas"] = round(v["gasto"], 2), round(v["parcelas"], 2)
        v["teto"] = _soma_orc(orc.get(v["id"], {}), meses_orc, fator)
    return list(rows.values())


def entradas_por_categoria(con, inicio: str, fim: str, deslocar: bool) -> list[dict]:
    """Renda por categoria (a tabela 'Income' da planilha)."""
    corte = dia_corte(con)
    rows = {r["id"]: {**dict(r), "valor": 0.0, "n": 0} for r in con.execute("SELECT * FROM categorias WHERE tipo='renda' ORDER BY ordem")}
    for r in con.execute("SELECT l.data, pt.categoria, pt.valor FROM partes pt JOIN lancamentos l ON l.id=pt.lancamento_id "
                         "WHERE pt.natureza='renda' AND pt.categoria IS NOT NULL"):
        d = _data_efetiva(r["data"], corte) if deslocar else r["data"]
        if inicio <= d <= fim:
            rows[r["categoria"]]["valor"] += r["valor"]
            rows[r["categoria"]]["n"] += 1
    for v in rows.values():
        v["valor"] = round(v["valor"], 2)
    return list(rows.values())


def _data_efetiva(data: str, corte: int) -> str:
    """Renda que cai a partir do dia de corte conta como primeiro dia do mês seguinte."""
    if int(data[8:10]) >= corte:
        y, m = int(data[:4]), int(data[5:7])
        return f"{y + m // 12}-{m % 12 + 1:02d}-01"
    return data


def _mais_meses(mes: str, n: int) -> str:
    y, m = int(mes[:4]), int(mes[5:7]) + n
    while m > 12:
        y, m = y + 1, m - 12
    while m < 1:
        y, m = y - 1, m + 12
    return f"{y}-{m:02d}"


def _pessoa_do_parcelamento(con, descricao: str) -> str | None:
    """Quem te deve as parcelas que faltam: a pessoa do acerto na parcela mais recente já classificada."""
    alvo = classificar.normalizar(descricao)        # sem o número da parcela
    for r in con.execute("SELECT l.descricao, p.pessoa FROM lancamentos l JOIN partes p ON p.lancamento_id = l.id "
                         "WHERE l.parcela IS NOT NULL AND p.natureza = 'acerto' AND p.pessoa IS NOT NULL ORDER BY l.data DESC"):
        if classificar.normalizar(r["descricao"]) == alvo:
            return r["pessoa"]
    return None


def compromissos(con, hoje: date | None = None) -> list[dict]:
    """Parcelas que ainda vão ser cobradas no cartão, por mês de cobrança.

    Junta as explícitas (CSV de fatura futura) com as projetadas pela numeração
    n/N da última parcela já cobrada de cada compra.
    """
    hoje = hoje or date.today()
    atual = hoje.strftime("%Y-%m")
    out: dict[tuple, dict] = {}
    for r in con.execute("SELECT mes, descricao, -valor AS valor, parcela, pessoa FROM parcelas_futuras"):
        base = classificar.normalizar(r["descricao"])[:14]
        out[(base, r["parcela"])] = dict(r)
    ultimas: dict[str, dict] = {}
    for r in con.execute("SELECT data, descricao, valor, parcela FROM lancamentos WHERE conta='nubank_cartao' AND parcela IS NOT NULL ORDER BY data"):
        n, total = map(int, r["parcela"].split("/"))
        base = classificar.normalizar(r["descricao"])[:14]
        ultimas[base] = {"data": r["data"], "desc": r["descricao"], "valor": -r["valor"], "n": n, "total": total}
    for base, u in ultimas.items():
        for k in range(u["n"] + 1, u["total"] + 1):
            parcela = f"{k}/{u['total']}"
            if (base, parcela) in out:
                continue
            mes = _mais_meses(u["data"][:7], k - u["n"])
            if mes <= atual:
                continue
            desc = u["desc"].split(" - Parcela")[0] + f" - Parcela {parcela}"
            out[(base, parcela)] = {"mes": mes, "descricao": desc, "valor": round(u["valor"], 2), "parcela": parcela,
                                    "pessoa": _pessoa_do_parcelamento(con, desc)}
    return sorted(out.values(), key=lambda c: (c["mes"], -c["valor"]))


def fatura_aberta(con, hoje: date) -> dict:
    """Dívida atual do cartão e o que já entrou na fatura que fecha no dia 1 do mês seguinte."""
    cartao = next(c for c in saldo_contas(con) if c["id"] == "nubank_cartao")
    divida = round(-cartao["saldo"], 2)
    futuras = round(sum(c["valor"] for c in compromissos(con, hoje)), 2)
    return {"divida": divida, "futuras": futuras, "limite": cartao["limite"],
            "limite_livre": round((cartao["limite"] or 0) - divida - futuras, 2)}


def _totais(con, inicio: str, fim: str, deslocar: bool) -> dict:
    corte = dia_corte(con)
    renda = gasto = juros = 0.0
    for r in con.execute("SELECT l.data, pt.natureza, pt.categoria, pt.valor FROM partes pt JOIN lancamentos l ON l.id=pt.lancamento_id "
                         "WHERE pt.natureza IN ('gasto','renda')"):
        if r["natureza"] == "renda":
            d = _data_efetiva(r["data"], corte) if deslocar else r["data"]
            if inicio <= d <= fim:
                renda += r["valor"]
        elif inicio <= r["data"] <= fim:
            gasto -= r["valor"]
            juros -= r["valor"] if r["categoria"] == "juros" else 0
    return {"renda": round(renda, 2), "gasto": round(gasto, 2), "juros": round(juros, 2), "resultado": round(renda - gasto, 2)}


def periodo_info(periodo: str, hoje: date) -> dict:
    """'2026' (ano), '2026-10' (mês) ou '2026-W43' (semana ISO): intervalo, vizinhos, fator do teto e ritmo."""
    if "-W" in periodo:
        y, w = map(int, periodo.split("-W"))
        ini = date.fromisocalendar(y, w, 1)
        fim = ini + timedelta(days=6)
        viz = lambda d: f"{d.isocalendar()[0]}-W{d.isocalendar()[1]:02d}"
        ant, prox = viz(ini - timedelta(days=7)), viz(ini + timedelta(days=7))
        fator, tipo = 0.25, "semana"          # teto mensal dividido por 4
        meses_orc = [ini.strftime("%Y-%m")]
    elif len(periodo) == 4:
        y = int(periodo)
        ini, fim = date(y, 1, 1), date(y, 12, 31)
        ant, prox = str(y - 1), str(y + 1)
        fator, tipo = 1.0, "ano"
        meses_orc = [f"{y}-{m:02d}" for m in range(1, (hoje.month if y == hoje.year else 12) + 1)]
    else:
        y, m = map(int, periodo.split("-"))
        ini, fim = date(y, m, 1), date(y, m, calendar.monthrange(y, m)[1])
        ant = f"{y - (m == 1)}-{(m - 2) % 12 + 1:02d}"
        prox = f"{y + (m == 12)}-{m % 12 + 1:02d}"
        fator, tipo = 1.0, "mes"
        meses_orc = [periodo]
    total = (fim - ini).days + 1
    ritmo = 1.0 if hoje > fim else 0.0 if hoje < ini else ((hoje - ini).days + 1) / total
    return {"periodo": periodo, "tipo": tipo, "inicio": ini.isoformat(), "fim": fim.isoformat(), "anterior": ant,
            "proximo": prox, "fator": fator, "meses_orc": meses_orc, "ritmo": round(ritmo, 4), "dias": total}


def serie_semanal(con, ate: date, semanas: int = 12) -> list[dict]:
    fim_sem = ate - timedelta(days=ate.weekday()) + timedelta(days=6)
    out = []
    for i in range(semanas - 1, -1, -1):
        f = fim_sem - timedelta(days=7 * i)
        ini = f - timedelta(days=6)
        t = _totais(con, ini.isoformat(), f.isoformat(), deslocar=False)
        iso = ini.isocalendar()
        out.append({"mes": f"{iso[0]}-W{iso[1]:02d}", "inicio": ini.isoformat(), **t})
    return out


def _orcado_na_serie(con, serie: list[dict], tipo: str) -> None:
    """Orçado (renda, gasto, metas) e poupança realizada de cada barra do gráfico: o "Tracked (vs. Budget)"
    da planilha. Na semana, o orçado é o do mês dela dividido por 4."""
    semana = tipo == "semana"
    meses = sorted({s["inicio"][:7] if semana else s["mes"] for s in serie})
    orc = orcado(con, meses)
    tipos = {r["id"]: r["tipo"] for r in con.execute("SELECT id, tipo FROM categorias")}
    fator = 0.25 if semana else 1.0
    soma = lambda filtro, mes: round(sum((v.get(mes) or 0) for k, v in orc.items() if filtro(k)) * fator, 2)
    for s in serie:
        mes = s["inicio"][:7] if semana else s["mes"]
        s["orc_renda"] = soma(lambda k: tipos.get(k) == "renda", mes)
        s["orc_gasto"] = soma(lambda k: tipos.get(k) == "gasto", mes)
        s["orc_poupanca"] = soma(lambda k: k.startswith("meta:"), mes)
        ini, fim = ((s["inicio"], (date.fromisoformat(s["inicio"]) + timedelta(days=6)).isoformat()) if semana
                    else (f"{mes}-01", f"{mes}-31"))
        s["poupanca"] = round(-con.execute("SELECT COALESCE(SUM(pt.valor),0) FROM partes pt JOIN lancamentos l ON l.id=pt.lancamento_id "
                                           "WHERE pt.natureza='poupanca' AND l.data BETWEEN ? AND ?", (ini, fim)).fetchone()[0], 2)


def painel(con, hoje: date | None = None, periodo: str | None = None) -> dict:
    """Painel de uma semana, um mês ou um ano. Contas, cartão e pessoas são sempre de hoje."""
    hoje = hoje or date.today()
    pi = periodo_info(periodo or hoje.strftime("%Y-%m"), hoje)
    pa = periodo_info(pi["anterior"], hoje)
    desloca = pi["tipo"] != "semana"
    cats = gastos_por_categoria(con, pi["inicio"], pi["fim"], pi["meses_orc"], pi["fator"])
    cats_ant = {c["id"]: c for c in gastos_por_categoria(con, pa["inicio"], pa["fim"], pa["meses_orc"], pa["fator"])}
    for c in cats:
        ca = cats_ant.get(c["id"], {"gasto": 0.0, "parcelas": 0.0, "teto": None})
        c["anterior"] = round(ca["gasto"] + ca["parcelas"], 2)          # tudo, para comparar o total
        c["anterior_gasto"] = ca["gasto"]                               # sem parcelas antigas, para o teto
        c["acima"] = round(max(0.0, c["gasto"] - c["teto"]), 2) if c["teto"] is not None else 0.0
        c["acima_anterior"] = round(max(0.0, ca["gasto"] - ca["teto"]), 2) if ca.get("teto") is not None else 0.0
    ent = entradas_por_categoria(con, pi["inicio"], pi["fim"], desloca)
    ent_ant = {e["id"]: e["valor"] for e in entradas_por_categoria(con, pa["inicio"], pa["fim"], desloca)}
    for e in ent:
        e["anterior"] = round(ent_ant.get(e["id"], 0.0), 2)
    variavel = [c for c in cats if not c["fixa"] and c["teto"]]
    teto_var = sum(c["teto"] for c in variavel)
    gasto_var = sum(c["gasto"] for c in variavel)
    grupos: dict[str, float] = defaultdict(float)
    for c in cats:
        grupos[c["grupo"]] += c["gasto"] + c["parcelas"]
    if pi["tipo"] == "semana":
        serie = serie_semanal(con, date.fromisoformat(pi["fim"]))
    elif pi["tipo"] == "ano":
        tem = {x["mes"]: x for x in serie_mensal(con, 1000)}
        serie = [tem.get(m) or {"mes": m, "renda": 0.0, "gasto": 0.0, "juros": 0.0, "resultado": 0.0}
                 for m in (f"{pi['periodo']}-{i:02d}" for i in range(1, 13))]
    else:
        serie = [x for x in serie_mensal(con, 1000) if x["mes"] <= pi["periodo"]][-12:]
    _orcado_na_serie(con, serie, pi["tipo"])
    top = [dict(r) for r in con.execute(
        "SELECT COALESCE(NULLIF(l.contraparte,''), l.descricao) AS nome, COUNT(*) AS n, ROUND(-SUM(pt.valor),2) AS total "
        "FROM partes pt JOIN lancamentos l ON l.id=pt.lancamento_id WHERE pt.natureza='gasto' AND l.data BETWEEN ? AND ? "
        "GROUP BY nome ORDER BY total DESC LIMIT 8", (pi["inicio"], pi["fim"]))]
    juros_ano = con.execute("SELECT ROUND(-COALESCE(SUM(pt.valor),0),2) FROM partes pt JOIN lancamentos l ON l.id=pt.lancamento_id "
                            "WHERE pt.categoria='juros' AND substr(l.data,1,4)=?", (pi["inicio"][:4],)).fetchone()[0]
    anos = sorted({r[0] for r in con.execute("SELECT DISTINCT substr(data,1,4) FROM lancamentos")} | {str(hoje.year)})
    return {
        "hoje": hoje.isoformat(), **pi, "atual": hoje.strftime("%Y-%m"), "anos": anos,
        "totais": _totais(con, pi["inicio"], pi["fim"], desloca), "totais_anterior": _totais(con, pa["inicio"], pa["fim"], desloca),
        "contas": saldo_contas(con), "cartao": fatura_aberta(con, hoje), "pessoas": saldo_pessoas(con),
        "categorias": cats, "entradas": ent, "metas": metas(con, pi["inicio"], pi["fim"], pi["fator"], hoje, pi["meses_orc"]), "teto_variavel": round(teto_var, 2), "gasto_variavel": round(gasto_var, 2),
        "pode_gastar": round(teto_var - gasto_var, 2), "grupos": {k: round(v, 2) for k, v in grupos.items() if v},
        "serie": serie, "pendentes": con.execute(f"SELECT COUNT(*) FROM lancamentos l WHERE {PENDENTE_SQL}").fetchone()[0],
        "top": top, "compromissos": compromissos(con, hoje), "juros_ano": juros_ano, "plano": plano(con, hoje),
    }


def metas(con, inicio: str | None = None, fim: str | None = None, fator: float = 1.0, hoje: date | None = None,
          meses_orc: list[str] | None = None) -> list[dict]:
    """A tabela "Savings": planejado e guardado no período, completude, e o acumulado contra o objetivo."""
    hoje = hoje or date.today()
    meses_orc = meses_orc or [hoje.strftime("%Y-%m")]
    orc = orcado(con, meses_orc)
    out = []
    for m in con.execute("SELECT * FROM metas ORDER BY ativa DESC, ordem, id"):
        m = dict(m)
        tot = con.execute("SELECT COALESCE(SUM(-valor),0) FROM partes WHERE natureza='poupanca' AND meta=?", (m["id"],)).fetchone()[0]
        per = con.execute("SELECT COALESCE(SUM(-pt.valor),0) FROM partes pt JOIN lancamentos l ON l.id=pt.lancamento_id "
                          "WHERE pt.natureza='poupanca' AND pt.meta=? AND l.data BETWEEN ? AND ?",
                          (m["id"], inicio or "0000", fim or "9999")).fetchone()[0]
        planejado = _soma_orc(orc.get(f"meta:{m['id']}", {}), meses_orc, fator) or 0.0
        m.update(guardado_total=round(tot, 2), guardado_periodo=round(per, 2), planejado_periodo=planejado,
                 completude_periodo=round(per / planejado, 4) if planejado else None,
                 falta_periodo=round(max(planejado - per, 0), 2),
                 completude_alvo=round(tot / m["alvo"], 4) if m["alvo"] else None,
                 falta_alvo=round(max((m["alvo"] or 0) - tot, 0), 2) if m["alvo"] else None)
        if m["alvo"] and m["data_alvo"] and m["falta_alvo"]:
            meses = max((int(m["data_alvo"][:4]) - hoje.year) * 12 + int(m["data_alvo"][5:7]) - hoje.month, 1)
            m["por_mes_ate_prazo"] = round(m["falta_alvo"] / meses, 2)
        out.append(m)
    return out


def grade_orcamento(con, ano: int) -> dict:
    """O Budget Planning: cada categoria e meta em cada mês do ano, orçado e realizado.

    Como no painel, parcela a partir da 2ª não entra no realizado da categoria (é compromisso antigo, não
    decisão do mês): fica em `parcelas`, para o total do mês continuar verdadeiro.
    """
    meses = [f"{ano}-{m:02d}" for m in range(1, 13)]
    orc = orcado(con, meses)
    itens = itens_fixos(con)
    corte = dia_corte(con)
    real: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for r in con.execute("SELECT l.data, l.parcela, pt.natureza, pt.categoria, pt.meta, pt.valor FROM partes pt "
                         "JOIN lancamentos l ON l.id=pt.lancamento_id WHERE pt.natureza IN ('gasto','renda','poupanca') "
                         "AND substr(l.data,1,4) IN (?, ?)", (str(ano), str(ano - 1))):
        if r["natureza"] == "renda":
            real[r["categoria"]][_data_efetiva(r["data"], corte)[:7]] += r["valor"]
        elif r["natureza"] == "gasto":
            antiga = bool(r["parcela"]) and not r["parcela"].startswith("1/")
            real["parcelas" if antiga else r["categoria"]][r["data"][:7]] += -r["valor"]
        elif r["meta"]:
            real[f"meta:{r['meta']}"][r["data"][:7]] += -r["valor"]
    sobrescritos = {(r["chave"], r["mes"]) for r in con.execute("SELECT chave, mes FROM orcamento WHERE mes LIKE ?", (f"{ano}-%",))}
    linhas = []
    for c in con.execute("SELECT * FROM categorias ORDER BY tipo DESC, ordem"):
        l = {"chave": c["id"], "tipo": c["tipo"], "grupo": c["grupo"], "nome": c["nome"], "cor": c["cor"], "teto": c["teto"],
             "fixa": c["fixa"]}
        if c["tipo"] == "gasto":
            l.update(por_itens=bool(c["orcar_por_itens"]), itens=itens[c["id"]],
                     soma_itens={mes: soma_itens(itens[c["id"]], mes) for mes in meses})
        linhas.append(l)
    for m in con.execute("SELECT * FROM metas ORDER BY ativa DESC, ordem, id"):
        linhas.append({"chave": f"meta:{m['id']}", "tipo": "poupanca", "grupo": "Metas", "nome": m["nome"], "cor": None,
                       "teto": m["aporte_mensal"], "ativa": m["ativa"]})
    for l in linhas:
        l["orcado"] = {mes: orc.get(l["chave"], {}).get(mes) for mes in meses}
        l["realizado"] = {mes: round(real[l["chave"]].get(mes, 0.0), 2) for mes in meses}
        l["definido"] = [mes for mes in meses if (l["chave"], mes) in sobrescritos]
    return {"ano": ano, "meses": meses, "linhas": linhas,
            "parcelas": {mes: round(real["parcelas"].get(mes, 0.0), 2) for mes in meses},
            "cores_grupos": json.loads(db.parametro(con, "cores_grupos", "{}") or "{}")}


def definir_orcamento(con, chave: str, mes: str, valor: float | None, ate_dezembro: bool = False) -> None:
    """Define (ou limpa, com None) o orçamento de um mês; com ate_dezembro, repete até o fim do ano."""
    meses = [mes] + ([f"{mes[:4]}-{m:02d}" for m in range(int(mes[5:7]) + 1, 13)] if ate_dezembro else [])
    for m in meses:
        if valor is None:
            con.execute("DELETE FROM orcamento WHERE chave=? AND mes=?", (chave, m))
        else:
            con.execute("INSERT INTO orcamento (chave, mes, valor) VALUES (?,?,?) ON CONFLICT(chave, mes) DO UPDATE SET valor=excluded.valor",
                        (chave, m, round(valor, 2)))


def evolucao(con, hoje: date, tipo: str, categoria: str | None = None, grupo: str | None = None, n: int = 12) -> list[dict]:
    """Gasto e teto de uma categoria (ou de um grupo inteiro) nos últimos n períodos."""
    if categoria:
        ids = [categoria]
    else:
        ids = [r["id"] for r in con.execute("SELECT id FROM categorias WHERE grupo=? AND tipo='gasto'", (grupo,))]
    if tipo == "semana":
        seg = hoje - timedelta(days=hoje.weekday())
        periodos = [(seg - timedelta(days=7 * i)) for i in range(n - 1, -1, -1)]
        chaves = [f"{d.isocalendar()[0]}-W{d.isocalendar()[1]:02d}" for d in periodos]
    elif tipo == "ano":
        chaves = [f"{hoje.year}-{m:02d}" for m in range(1, 13)]
    else:
        chaves = [_mais_meses(hoje.strftime("%Y-%m"), -i) for i in range(n - 1, -1, -1)]
    out = []
    for k in chaves:
        pi = periodo_info(k, hoje)
        cats = [c for c in gastos_por_categoria(con, pi["inicio"], pi["fim"], pi["meses_orc"], pi["fator"]) if c["id"] in ids]
        teto = sum(c["teto"] for c in cats if c["teto"] is not None) if any(c["teto"] is not None for c in cats) else None
        out.append({"periodo": k, "inicio": pi["inicio"], "gasto": round(sum(c["gasto"] for c in cats), 2),
                    "parcelas": round(sum(c["parcelas"] for c in cats), 2), "teto": teto})
    return out


def _no_intervalo(mes: str, inicio: str, fim: str | None) -> bool:
    return inicio <= mes and (not fim or mes <= fim)


def plano(con, hoje: date) -> dict:
    """Projeção mês a mês até o horizonte. Nada aqui é específico: renda base, horizonte e eventos
    (mudança de renda ou de gasto a partir de um mês, entrada ou saída única) vêm do que você cadastrou.

    Renda, custo de vida e aportes vêm do orçamento de cada mês (sem valor definido: salário base, teto de
    cada categoria, aporte mensal de cada meta), mais os eventos. O cartão fica congelado: entram a fatura atual e as parcelas
    já contratadas (a fatura que vence em M soma as cobranças de M-1). Reembolsos esperados = parcelas
    que alguém te deve (acerto ligado a parcela no cartão).
    Sobra paga primeiro quem você deve; o resto vira saldo livre. Falta = o que precisa vir de algum lugar.
    """
    renda_base = float(db.parametro(con, "salario_mensal", "0") or 0)
    horizonte = db.parametro(con, "horizonte", None) or db.parametro(con, "contrato_fim", hoje.strftime("%Y-12"))
    tipos = {r["id"]: r["tipo"] for r in con.execute("SELECT id, tipo FROM categorias")}
    custo_base = round(sum(r["teto"] or 0 for r in con.execute("SELECT teto FROM categorias WHERE tipo='gasto'")), 2)
    eventos = [dict(r) for r in con.execute("SELECT * FROM eventos WHERE ativo=1")]
    aporte_base = round(sum(r["aporte_mensal"] for r in con.execute("SELECT aporte_mensal FROM metas WHERE ativa=1")), 2)
    cartao = fatura_aberta(con, hoje)
    juros_rot = round(float(db.parametro(con, "rotativo_valor", "0")) * 0.1673, 2)
    cobranca, reemb = defaultdict(float), defaultdict(float)
    for c in compromissos(con, hoje):
        venc = _mais_meses(c["mes"], 1)
        cobranca[venc] += c["valor"]
        if c["pessoa"]:
            reemb[venc] += c["valor"]
    # Parcelas que alguém te deve e já entraram na fatura aberta: o reembolso esperado vem no primeiro mês.
    ciclo = hoje.strftime("%Y-%m-01")
    ja = con.execute("SELECT COALESCE(SUM(-l.valor),0) FROM lancamentos l WHERE l.conta='nubank_cartao' AND l.data>=? AND l.parcela IS NOT NULL "
                     "AND EXISTS (SELECT 1 FROM partes p WHERE p.lancamento_id=l.id AND p.natureza='acerto')", (ciclo,)).fetchone()[0]
    deve = round(sum(-p["saldo"] for p in saldo_pessoas(con) if p["saldo"] < 0), 2)
    meses_proj, k = [], hoje.strftime("%Y-%m")
    while k < horizonte:
        k = _mais_meses(k, 1)
        meses_proj.append(k)
    orc = orcado(con, meses_proj)
    soma = lambda filtro, mes: sum((v.get(mes) or 0) for ch, v in orc.items() if filtro(ch))
    linhas, livre_acum, metas_acum = [], 0.0, 0.0
    k = hoje.strftime("%Y-%m")
    primeiro = True
    while k < horizonte:
        k = _mais_meses(k, 1)
        renda = soma(lambda ch: tipos.get(ch) == "renda", k) + \
            sum(e["valor"] for e in eventos if e["tipo"] == "renda_mensal" and _no_intervalo(k, e["inicio"], e["fim"]))
        custo = soma(lambda ch: tipos.get(ch) == "gasto", k) + \
            sum(e["valor"] for e in eventos if e["tipo"] == "gasto_mensal" and _no_intervalo(k, e["inicio"], e["fim"]))
        aporte_metas = round(soma(lambda ch: ch.startswith("meta:"), k), 2)
        unicos = sum(e["valor"] for e in eventos if e["tipo"] == "entrada_unica" and e["inicio"] == k) - \
            sum(e["valor"] for e in eventos if e["tipo"] == "saida_unica" and e["inicio"] == k)
        cart = round((cartao["divida"] + juros_rot if primeiro else 0.0) + cobranca.get(k, 0.0), 2)
        rb = round(reemb.get(k, 0.0) + (ja if primeiro else 0.0), 2)
        resultado = round(renda + rb + unicos - custo - cart - aporte_metas, 2)
        falta = round(max(0.0, -resultado), 2)
        sobra = max(0.0, resultado)
        pg = round(min(sobra, deve), 2)
        deve = round(deve - pg, 2)
        livre_acum = round(livre_acum + sobra - pg, 2)
        metas_acum = round(metas_acum + aporte_metas, 2)
        linhas.append({"mes": k, "renda": round(renda, 2), "custo": round(custo, 2), "cartao": cart, "reembolsos": rb,
                       "unicos": round(unicos, 2), "aportes": aporte_metas, "resultado": resultado, "falta": falta,
                       "pago_pessoas": pg, "deve_pessoas": deve, "livre": livre_acum, "metas": metas_acum})
        primeiro = False
    return {"renda_base": renda_base, "custo_base": custo_base, "horizonte": horizonte, "aporte_metas": aporte_base,
            "eventos": eventos, "linhas": linhas, "falta_total": round(sum(l["falta"] for l in linhas), 2)}
