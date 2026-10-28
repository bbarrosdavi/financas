"""Sincronização entre o app do celular e o servidor.

Cada aparelho tem o seu banco e funciona sozinho. Quando o celular alcança o servidor, os dois trocam o que
mudou desde a última vez, registro por registro:

- Cada linha das tabelas sincronizadas tem uma identidade comum aos aparelhos (`uid`) e a hora da última
  alteração (`alterado_em`, UTC). Os gatilhos do SQLite anotam isso em `sync_registro` a cada INSERT, UPDATE
  ou DELETE, então nenhuma regra de negócio precisa saber que a sincronização existe.
- O lançamento viaja inteiro, com as partes: classificar muda o lançamento.
- Conflito: vence a alteração mais recente, registro por registro. Empate fica com o servidor. O que já
  existia antes da sincronização (o vocabulário inicial, os dados de um banco antigo) conta como o mais antigo
  possível, então a primeira troca nunca troca o dado de alguém pelo padrão de fábrica do outro.
- Apagar também viaja: a linha some e o registro fica marcado como apagado, com a hora.

O celular manda o que mudou nele (`enviar`); o servidor aplica e devolve o que mudou nele desde o `cursor` que
o celular já tinha. Cada lado aplica numa transação: ou entra inteiro, ou nada.

Dois casos de "o mesmo dado chegou pelos dois lados" são casados em vez de duplicados: a mesma linha de
extrato importada nos dois aparelhos (mesma `chave` de deduplicação) e a compra que o celular viu pelo push
depois que o extrato com ela já tinha sido importado no servidor (o casamento que a importação faz, ao
contrário).
"""

import json
import sqlite3
import urllib.error
import urllib.request
from datetime import datetime, timezone

EPOCA = "1970-01-01T00:00:00.000Z"
AGORA_SQL = "strftime('%Y-%m-%dT%H:%M:%fZ','now')"
PROTOCOLO = 1

# tabela: (chave primária local, uid formado pelo gatilho; None = aleatório). Na ordem de dependência:
# quem é referenciado vem antes de quem referencia.
TABELAS: dict[str, tuple[str, str | None]] = {
    "contas": ("{r}.id", "{r}.id"),
    "pessoas": ("{r}.id", "{r}.id"),
    "categorias": ("{r}.id", "{r}.id"),
    "metas": ("{r}.id", None),
    "eventos": ("{r}.id", None),
    "itens_fixos": ("{r}.id", None),
    "regras": ("{r}.id", "{r}.origem || '|' || {r}.padrao"),
    "parcelas_futuras": ("{r}.id", "{r}.conta || '|' || {r}.mes || '|' || {r}.descricao || '|' || COALESCE({r}.parcela, '')"),
    "orcamento": ("{r}.chave || '|' || {r}.mes", "{r}.chave || '|' || {r}.mes"),
    "parametros": ("{r}.chave", "{r}.chave"),
    "lancamentos": ("{r}.id", None),
    "importacoes": ("{r}.id", None),
    "ignorados": ("{r}.id", None),
}
# Tabelas cuja chave primária é o id inteiro local (não viaja: cada aparelho numera do seu jeito).
COM_ID = {"metas", "eventos", "itens_fixos", "regras", "parcelas_futuras", "lancamentos", "importacoes", "ignorados"}
# Parâmetros que são deste aparelho: o papel de parede (o arquivo não viaja) e o controle de avisos.
PARAMETROS_LOCAIS = ("papel_de_parede", "aviso_ultimo", "eventos_semeados")
ORIGENS_DE_ARQUIVO = ("push", "manual", "ape")      # o que NÃO veio de arquivo do banco

SCHEMA = """
CREATE TABLE IF NOT EXISTS sync_registro (
    tabela TEXT NOT NULL,
    uid TEXT NOT NULL,
    chave TEXT NOT NULL,                  -- chave primária local da linha
    alterado_em TEXT NOT NULL,            -- UTC; vence o mais recente
    versao INTEGER NOT NULL,              -- contador deste banco: o que mudou desde o cursor de quem pergunta
    apagado INTEGER NOT NULL DEFAULT 0,
    enviar INTEGER NOT NULL DEFAULT 0,    -- mudou aqui e ainda não foi mandado (só o celular manda)
    PRIMARY KEY (tabela, uid)
);
CREATE INDEX IF NOT EXISTS ix_sync_chave ON sync_registro(tabela, chave);
CREATE INDEX IF NOT EXISTS ix_sync_versao ON sync_registro(versao);
CREATE TABLE IF NOT EXISTS sync_estado (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    seq INTEGER NOT NULL DEFAULT 0,
    aplicando INTEGER NOT NULL DEFAULT 0  -- 1 enquanto aplica o que veio do outro lado: os gatilhos param
);
INSERT OR IGNORE INTO sync_estado (id) VALUES (1);
-- Estado do lado cliente (celular): cursor do servidor, titular, último push mandado pelo webhook.
CREATE TABLE IF NOT EXISTS sync_cliente (chave TEXT PRIMARY KEY, valor TEXT NOT NULL);
"""


def _gatilhos(tabela: str) -> str:
    chave, uid = TABELAS[tabela]
    novo, velho = f"CAST({chave.format(r='NEW')} AS TEXT)", f"CAST({chave.format(r='OLD')} AS TEXT)"
    uid_novo = uid.format(r="NEW") if uid else "lower(hex(randomblob(16)))"
    ativo = "(SELECT aplicando FROM sync_estado) = 0"
    filtro_n = filtro_o = ""
    if tabela == "parametros":
        locais = ",".join(f"'{p}'" for p in PARAMETROS_LOCAIS)
        filtro_n, filtro_o = f" AND NEW.chave NOT IN ({locais})", f" AND OLD.chave NOT IN ({locais})"
    seq = "UPDATE sync_estado SET seq = seq + 1;"
    v = "(SELECT seq FROM sync_estado)"
    return f"""
    DROP TRIGGER IF EXISTS sync_{tabela}_i;
    CREATE TRIGGER sync_{tabela}_i AFTER INSERT ON {tabela} WHEN {ativo}{filtro_n} BEGIN
        {seq}
        INSERT INTO sync_registro (tabela, uid, chave, alterado_em, versao, apagado, enviar)
        VALUES ('{tabela}', {uid_novo}, {novo}, {AGORA_SQL}, {v}, 0, 1)
        ON CONFLICT (tabela, uid) DO UPDATE SET chave = excluded.chave, alterado_em = excluded.alterado_em,
            versao = excluded.versao, apagado = 0, enviar = 1;
    END;
    DROP TRIGGER IF EXISTS sync_{tabela}_u;
    CREATE TRIGGER sync_{tabela}_u AFTER UPDATE ON {tabela} WHEN {ativo}{filtro_n} BEGIN
        {seq}
        INSERT INTO sync_registro (tabela, uid, chave, alterado_em, versao, apagado, enviar)
        SELECT '{tabela}', {uid_novo}, {novo}, {AGORA_SQL}, {v}, 0, 1
        WHERE NOT EXISTS (SELECT 1 FROM sync_registro WHERE tabela = '{tabela}' AND chave = {velho} AND apagado = 0)
        ON CONFLICT (tabela, uid) DO NOTHING;
        UPDATE sync_registro SET chave = {novo}, alterado_em = {AGORA_SQL}, versao = {v}, apagado = 0, enviar = 1
        WHERE tabela = '{tabela}' AND chave = {velho} AND apagado = 0;
    END;
    DROP TRIGGER IF EXISTS sync_{tabela}_d;
    CREATE TRIGGER sync_{tabela}_d AFTER DELETE ON {tabela} WHEN {ativo}{filtro_o} BEGIN
        {seq}
        UPDATE sync_registro SET apagado = 1, alterado_em = {AGORA_SQL}, versao = {v}, enviar = 1
        WHERE tabela = '{tabela}' AND chave = {velho} AND apagado = 0;
    END;
    """


def _gatilhos_partes() -> str:
    """Mudar uma parte é mudar o lançamento dela."""
    out = []
    for nome, evento, r in (("i", "INSERT", "NEW"), ("u", "UPDATE", "NEW"), ("d", "DELETE", "OLD")):
        out.append(f"""
        DROP TRIGGER IF EXISTS sync_partes_{nome};
        CREATE TRIGGER sync_partes_{nome} AFTER {evento} ON partes WHEN (SELECT aplicando FROM sync_estado) = 0 BEGIN
            UPDATE sync_estado SET seq = seq + 1;
            UPDATE sync_registro SET alterado_em = {AGORA_SQL}, versao = (SELECT seq FROM sync_estado), enviar = 1
            WHERE tabela = 'lancamentos' AND chave = CAST({r}.lancamento_id AS TEXT) AND apagado = 0;
        END;""")
    return "".join(out)


def preparar(con: sqlite3.Connection) -> None:
    """Tabelas e gatilhos da sincronização, e o registro (como o mais antigo possível) do que já existia."""
    con.executescript(SCHEMA + "".join(_gatilhos(t) for t in TABELAS) + _gatilhos_partes())
    con.execute("UPDATE sync_estado SET seq = seq + 1")
    for tabela, (chave, uid) in TABELAS.items():
        filtro = (f" AND t.chave NOT IN ({','.join(repr(p) for p in PARAMETROS_LOCAIS)})" if tabela == "parametros" else "")
        k = f"CAST({chave.format(r='t')} AS TEXT)"
        con.execute(
            f"INSERT INTO sync_registro (tabela, uid, chave, alterado_em, versao, apagado, enviar) "
            f"SELECT '{tabela}', {uid.format(r='t') if uid else 'lower(hex(randomblob(16)))'}, {k}, ?, "
            f"(SELECT seq FROM sync_estado), 0, 0 FROM {tabela} t "
            f"WHERE NOT EXISTS (SELECT 1 FROM sync_registro s WHERE s.tabela = '{tabela}' AND s.chave = {k} AND s.apagado = 0)"
            f"{filtro} ON CONFLICT (tabela, uid) DO NOTHING", (EPOCA,))


# ---------------------------------------------------------------------------
# Ler e escrever uma linha, traduzindo o que é local (ids de meta) para o que viaja (uid)
# ---------------------------------------------------------------------------
def _agora() -> str:
    t = datetime.now(timezone.utc)
    return t.strftime("%Y-%m-%dT%H:%M:%S.") + f"{t.microsecond // 1000:03d}Z"


def _proxima_versao(con) -> int:
    con.execute("UPDATE sync_estado SET seq = seq + 1")
    return con.execute("SELECT seq FROM sync_estado").fetchone()[0]


def _uid_da_meta(con, mid) -> str | None:
    if mid is None:
        return None
    r = con.execute("SELECT uid FROM sync_registro WHERE tabela = 'metas' AND chave = ?", (str(mid),)).fetchone()
    return r[0] if r else None


def _meta_local(con, uid) -> int | None:
    if not uid:
        return None
    r = con.execute("SELECT chave FROM sync_registro WHERE tabela = 'metas' AND uid = ? AND apagado = 0", (uid,)).fetchone()
    return int(r[0]) if r else None


def _uid_exportado(con, tabela: str, uid: str) -> str | None:
    """No orçamento, a meta aparece pelo id local dentro da chave: 'meta:5|2026-10' viaja como 'meta:<uid>|2026-10'."""
    if tabela == "orcamento" and uid.startswith("meta:"):
        chave, mes = uid.rsplit("|", 1)
        u = _uid_da_meta(con, chave[5:])
        return f"meta:{u}|{mes}" if u else None
    return uid


def _uid_local(con, tabela: str, uid: str) -> str | None:
    if tabela == "orcamento" and uid.startswith("meta:"):
        chave, mes = uid.rsplit("|", 1)
        mid = _meta_local(con, chave[5:])
        return f"meta:{mid}|{mes}" if mid is not None else None
    return uid


def _onde(tabela: str) -> str:
    if tabela == "parametros":
        return "chave = ?"
    if tabela == "orcamento":
        return "chave || '|' || mes = ?"
    return "id = ?"


def _colunas(con, tabela: str) -> list[str]:
    return [r[1] for r in con.execute(f"PRAGMA table_info({tabela})")]


def _sugestao(con, texto, exportar: bool):
    if not texto:
        return texto
    try:
        partes = json.loads(texto)
    except ValueError:
        return texto
    for p in partes:
        if p.get("meta") is not None:
            p["meta"] = _uid_da_meta(con, p["meta"]) if exportar else _meta_local(con, p["meta"])
    return json.dumps(partes, ensure_ascii=False)


def _ler(con, tabela: str, chave: str) -> dict | None:
    row = con.execute(f"SELECT * FROM {tabela} WHERE {_onde(tabela)}", (int(chave) if tabela in COM_ID else chave,)).fetchone()
    if row is None:
        return None
    d = dict(row)
    lid = d.pop("id") if tabela in COM_ID else None
    if tabela == "lancamentos":
        d["sugestao"] = _sugestao(con, d.get("sugestao"), True)
        d["partes"] = [{"valor": p["valor"], "natureza": p["natureza"], "categoria": p["categoria"], "pessoa": p["pessoa"],
                        "meta": _uid_da_meta(con, p["meta"]), "obs": p["obs"], "motivo": p["motivo"]}
                       for p in con.execute("SELECT * FROM partes WHERE lancamento_id = ? ORDER BY id", (lid,))]
    elif tabela == "orcamento" and d["chave"].startswith("meta:"):
        d["chave"] = "meta:" + (_uid_da_meta(con, d["chave"][5:]) or "")
    elif tabela == "ignorados":
        d["inbox_id"] = None
    return d


def _pendente(partes: list[dict], valor: float) -> bool:
    if not partes or abs(sum(p["valor"] for p in partes) - valor) > 0.005:
        return True
    return any((p["natureza"] in ("gasto", "renda") and not p.get("categoria")) or (p["natureza"] == "acerto" and not p.get("pessoa"))
               or (p["natureza"] == "poupanca" and not p.get("meta")) for p in partes)


def _gravar_partes(con, lid: int, partes: list[dict]) -> None:
    con.execute("DELETE FROM partes WHERE lancamento_id = ?", (lid,))
    for p in partes:
        con.execute("INSERT INTO partes (lancamento_id, valor, natureza, categoria, pessoa, meta, obs, motivo) VALUES (?,?,?,?,?,?,?,?)",
                    (lid, round(p["valor"], 2), p["natureza"], p.get("categoria"), p.get("pessoa"), _meta_local(con, p.get("meta")),
                     p.get("obs") or "", p.get("motivo") or ""))


def _escrever(con, tabela: str, chave_local: str | None, dados: dict) -> str:
    """Grava a linha (atualiza a que já existe, ou insere) e devolve a chave local dela."""
    dados = dict(dados)
    partes = dados.pop("partes", None)
    if tabela == "lancamentos":
        dados["sugestao"] = _sugestao(con, dados.get("sugestao"), False)
    elif tabela == "orcamento" and str(dados.get("chave", "")).startswith("meta:"):
        mid = _meta_local(con, dados["chave"][5:])
        if mid is None:
            raise LookupError("meta desconhecida")
        dados["chave"] = f"meta:{mid}"
    cols = [c for c in _colunas(con, tabela) if c in dados and not (c == "id" and tabela in COM_ID)]
    vals = [dados[c] for c in cols]
    if tabela in COM_ID:
        if chave_local is None and tabela == "regras":
            r = con.execute("SELECT id FROM regras WHERE padrao = ? AND origem = ?", (dados["padrao"], dados["origem"])).fetchone()
            chave_local = str(r[0]) if r else None
        elif chave_local is None and tabela == "parcelas_futuras":
            r = con.execute("SELECT id FROM parcelas_futuras WHERE conta = ? AND mes = ? AND descricao = ? AND parcela IS ?",
                            (dados["conta"], dados["mes"], dados["descricao"], dados.get("parcela"))).fetchone()
            chave_local = str(r[0]) if r else None
        if chave_local is not None and con.execute(f"SELECT 1 FROM {tabela} WHERE id = ?", (int(chave_local),)).fetchone():
            con.execute(f"UPDATE {tabela} SET {', '.join(c + ' = ?' for c in cols)} WHERE id = ?", vals + [int(chave_local)])
        else:
            cur = con.execute(f"INSERT INTO {tabela} ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})", vals)
            chave_local = str(cur.lastrowid)
        if partes is not None:
            _gravar_partes(con, int(chave_local), partes)
        return chave_local
    pk = {"parametros": ["chave"], "orcamento": ["chave", "mes"]}.get(tabela, ["id"])
    atualizar = [c for c in cols if c not in pk]
    con.execute(f"INSERT INTO {tabela} ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))}) "
                f"ON CONFLICT ({', '.join(pk)}) DO " + (f"UPDATE SET {', '.join(c + ' = excluded.' + c for c in atualizar)}" if atualizar else "NOTHING"),
                vals)
    return f"{dados['chave']}|{dados['mes']}" if tabela == "orcamento" else str(dados[pk[0]])


def _registrar(con, tabela: str, uid: str, chave: str, alterado_em: str, apagado: bool, enviar: bool) -> None:
    con.execute("INSERT INTO sync_registro (tabela, uid, chave, alterado_em, versao, apagado, enviar) VALUES (?,?,?,?,?,?,?) "
                "ON CONFLICT (tabela, uid) DO UPDATE SET chave = excluded.chave, alterado_em = excluded.alterado_em, "
                "versao = excluded.versao, apagado = excluded.apagado, enviar = excluded.enviar",
                (tabela, uid, chave, alterado_em, _proxima_versao(con), int(apagado), int(enviar)))


def _apagar_linha(con, tabela: str, chave: str) -> bool:
    """Apaga a linha local. Não apaga o que ainda é usado aqui (categoria, pessoa, meta ou conta com lançamentos)."""
    try:
        con.execute("SAVEPOINT apagar")
        con.execute(f"DELETE FROM {tabela} WHERE {_onde(tabela)}", (int(chave) if tabela in COM_ID else chave,))
        con.execute("RELEASE apagar")
        return True
    except sqlite3.IntegrityError:
        con.execute("ROLLBACK TO apagar")
        con.execute("RELEASE apagar")
        return False


# ---------------------------------------------------------------------------
# O mesmo dado chegando pelos dois lados
# ---------------------------------------------------------------------------
def _casar_por_chave(con, uid: str, dados: dict, alterado_em: str) -> list[int]:
    """A mesma linha de extrato importada nos dois aparelhos: fica uma, com o menor uid (os dois lados chegam ao mesmo)."""
    if not dados.get("chave"):
        return []
    row = con.execute("SELECT l.id, s.uid, s.alterado_em FROM lancamentos l JOIN sync_registro s ON s.tabela = 'lancamentos' "
                      "AND s.chave = CAST(l.id AS TEXT) AND s.apagado = 0 WHERE l.chave = ?", (dados["chave"],)).fetchone()
    if not row:
        return []
    lid, uid_local, alt_local = row
    chega_vence = alterado_em > alt_local
    if chega_vence:
        _escrever(con, "lancamentos", str(lid), dados)
    fica, sai = sorted((uid, uid_local))
    agora = _agora()
    con.execute("DELETE FROM sync_registro WHERE tabela = 'lancamentos' AND uid IN (?, ?)", (uid, uid_local))
    # Se o outro lado já tem exatamente isto (o uid dele, com o conteúdo dele), nada precisa voltar.
    igual_ao_outro = fica == uid and chega_vence
    _registrar(con, "lancamentos", fica, str(lid), alterado_em if igual_ao_outro else agora, False, not igual_ao_outro)
    _registrar(con, "lancamentos", sai, f"apagado:{sai}", agora, True, True)
    return [lid]


def _casar_push(con, uid: str, dados: dict) -> list[int]:
    """A compra que veio pelo push depois de o extrato com ela já estar aqui: como na importação, fica o lançamento
    do push, confirmado pelo arquivo, e a linha do arquivo sai."""
    if dados.get("origem") != "push" or dados.get("confirmado_por"):
        return []
    q = ",".join("?" * len(ORIGENS_DE_ARQUIVO))
    x = con.execute(f"SELECT * FROM lancamentos WHERE origem NOT IN ({q}) AND conta = ? AND ABS(valor - ?) < 0.005 "
                    f"AND ABS(julianday(data) - julianday(?)) <= 2 ORDER BY ABS(julianday(data) - julianday(?)) LIMIT 1",
                    (*ORIGENS_DE_ARQUIVO, dados["conta"], dados["valor"], dados["data"], dados["data"])).fetchone()
    if not x:
        return []
    x = dict(x)
    partes_x = [dict(p) for p in con.execute("SELECT valor, natureza, categoria, pessoa, meta, obs, motivo FROM partes "
                                             "WHERE lancamento_id = ? ORDER BY id", (x["id"],))]
    for p in partes_x:
        p["meta"] = _uid_da_meta(con, p["meta"])
    junto = {**dados, "confirmado_por": f"{x['origem']}:{x['ref']}", "data": x["data"],
             "contraparte": dados.get("contraparte") or x["contraparte"], "parcela": dados.get("parcela") or x["parcela"]}
    if _pendente(dados.get("partes") or [], dados["valor"]) and not _pendente(partes_x, x["valor"]):
        junto["partes"] = partes_x
    uid_x = con.execute("SELECT uid FROM sync_registro WHERE tabela = 'lancamentos' AND chave = ? AND apagado = 0",
                        (str(x["id"]),)).fetchone()
    con.execute("DELETE FROM lancamentos WHERE id = ?", (x["id"],))
    agora = _agora()
    if uid_x:
        _registrar(con, "lancamentos", uid_x[0], f"apagado:{uid_x[0]}", agora, True, True)
    chave = _escrever(con, "lancamentos", None, junto)
    _registrar(con, "lancamentos", uid, chave, agora, False, True)
    return [x["id"], int(chave)]


# ---------------------------------------------------------------------------
# Trocar mudanças
# ---------------------------------------------------------------------------
def mudancas(con, cursor: int | None = None) -> list[dict]:
    """O que mudou aqui: com cursor, tudo depois dele (servidor); sem, o que falta mandar (celular)."""
    if cursor is None:
        regs = con.execute("SELECT * FROM sync_registro WHERE enviar = 1 ORDER BY versao").fetchall()
    else:
        regs = con.execute("SELECT * FROM sync_registro WHERE versao > ? ORDER BY versao", (cursor,)).fetchall()
    out = []
    for r in regs:
        uid = _uid_exportado(con, r["tabela"], r["uid"])
        if uid is None:
            continue
        dados = None if r["apagado"] else _ler(con, r["tabela"], r["chave"])
        out.append({"tabela": r["tabela"], "uid": uid, "alterado_em": r["alterado_em"], "apagado": dados is None, "dados": dados})
    return out


def _aplicar_um(con, m: dict, empate_entra: bool, tocados: list[int]) -> bool:
    tabela, alt = m["tabela"], m["alterado_em"]
    uid = _uid_local(con, tabela, m["uid"])
    if uid is None or (tabela == "parametros" and m["uid"] in PARAMETROS_LOCAIS):
        return False
    reg = con.execute("SELECT * FROM sync_registro WHERE tabela = ? AND uid = ?", (tabela, uid)).fetchone()
    if reg and not (alt > reg["alterado_em"] or (empate_entra and alt == reg["alterado_em"])):
        return False
    if m["apagado"]:
        if reg and not reg["apagado"] and not _apagar_linha(con, tabela, reg["chave"]):
            return False        # ainda em uso aqui: fica, e a próxima mudança local leva de volta
        if tabela == "lancamentos" and reg and not reg["apagado"]:
            tocados.append(int(reg["chave"]))
        _registrar(con, tabela, uid, reg["chave"] if reg else f"apagado:{uid}", alt, True, False)
        return True
    vivo = reg is not None and not reg["apagado"]
    if tabela == "lancamentos" and not vivo:
        casados = _casar_por_chave(con, uid, m["dados"], alt) or _casar_push(con, uid, m["dados"])
        if casados:
            tocados.extend(casados)
            return True
    chave = _escrever(con, tabela, reg["chave"] if vivo else None, m["dados"])
    _registrar(con, tabela, uid, chave, alt, False, False)
    if tabela == "lancamentos":
        tocados.append(int(chave))
    return True


def aplicar(con, recebidas: list[dict], empate_entra: bool) -> dict:
    """Aplica as mudanças do outro lado. `empate_entra`: o celular aceita o servidor no empate; o servidor não.
    O que um casamento cria de novo fica marcado para voltar ao outro lado. Devolve também os ids locais dos
    lançamentos que mudaram aqui (`lancamentos`), para quem precisa avisar outro sistema deles."""
    ordem = list(TABELAS)
    vivas = sorted((m for m in recebidas if not m["apagado"] and m["tabela"] in TABELAS), key=lambda m: ordem.index(m["tabela"]))
    mortas = sorted((m for m in recebidas if m["apagado"] and m["tabela"] in TABELAS), key=lambda m: -ordem.index(m["tabela"]))
    aceitas = recusadas = 0
    tocados: list[int] = []
    # DML antes do primeiro SAVEPOINT: a transação já está aberta, e soltar um savepoint não grava pela metade.
    con.execute("UPDATE sync_estado SET aplicando = 1")
    try:
        for m in vivas + mortas:
            con.execute("SAVEPOINT registro")
            try:
                ok = _aplicar_um(con, m, empate_entra, tocados)
            except (LookupError, KeyError, TypeError, sqlite3.IntegrityError):
                con.execute("ROLLBACK TO registro")
                ok = False
            con.execute("RELEASE registro")
            aceitas, recusadas = aceitas + ok, recusadas + (not ok)
    finally:
        con.execute("UPDATE sync_estado SET aplicando = 0")
    return {"aceitas": aceitas, "recusadas": recusadas, "lancamentos": sorted(set(tocados))}


def servir(con, cursor: int, recebidas: list[dict], titular: str = "") -> dict:
    """O lado do servidor: aplica o que o celular mandou e devolve tudo o que mudou aqui depois do cursor dele."""
    r = aplicar(con, recebidas, empate_entra=False)
    return {"protocolo": PROTOCOLO, **r, "mudancas": mudancas(con, cursor),
            "cursor": con.execute("SELECT seq FROM sync_estado").fetchone()[0], "titular": titular}


# ---------------------------------------------------------------------------
# O lado do celular
# ---------------------------------------------------------------------------
def _cliente(con, chave: str, padrao: str | None = None) -> str | None:
    r = con.execute("SELECT valor FROM sync_cliente WHERE chave = ?", (chave,)).fetchone()
    return r[0] if r else padrao


def _definir_cliente(con, chave: str, valor) -> None:
    con.execute("INSERT INTO sync_cliente (chave, valor) VALUES (?, ?) ON CONFLICT (chave) DO UPDATE SET valor = excluded.valor",
                (chave, str(valor)))


class ErroSync(Exception):
    pass


def _post(url: str, chave_api: str, corpo: dict, timeout: float) -> tuple[int, dict]:
    req = urllib.request.Request(url, data=json.dumps(corpo, ensure_ascii=False).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "Authorization": f"Bearer {chave_api}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, {}
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise ErroSync(f"Servidor fora de alcance: {getattr(e, 'reason', e)}") from e


def sincronizar(conectar, base: str, chave_api: str, timeout: float = 30) -> dict:
    """Uma troca completa com o servidor. `conectar` abre o banco local (db.conectar)."""
    base = base.rstrip("/")
    with conectar() as con:
        cursor = int(_cliente(con, "cursor", "0"))
        enviadas = mudancas(con)
    status, resp = _post(f"{base}/api/v1/sync", chave_api, {"protocolo": PROTOCOLO, "cursor": cursor, "mudancas": enviadas}, timeout)
    if status == 404:
        return _pelo_webhook(conectar, base, chave_api, timeout)
    if status == 401:
        raise ErroSync("Chave recusada pelo servidor (confira a API_KEY).")
    if status != 200:
        raise ErroSync(f"O servidor respondeu {status}.")
    with conectar() as con:
        r = aplicar(con, resp.get("mudancas", []), empate_entra=True)
        r.pop("lancamentos")
        for m in enviadas:
            uid = _uid_local(con, m["tabela"], m["uid"])
            con.execute("UPDATE sync_registro SET enviar = 0 WHERE tabela = ? AND uid = ? AND alterado_em = ?",
                        (m["tabela"], uid, m["alterado_em"]))
        _definir_cliente(con, "cursor", resp.get("cursor", cursor))
        _definir_cliente(con, "titular", resp.get("titular", ""))
    return {"modo": "sync", "enviadas": len(enviadas), "recebidas": len(resp.get("mudancas", [])), **r}


def _pelo_webhook(conectar, base: str, chave_api: str, timeout: float) -> dict:
    """Servidor sem /api/v1/sync (versão antiga): manda só os pushes, pelo mesmo contrato do MacroDroid."""
    from app.config import settings
    with conectar() as con:
        ultimo = int(_cliente(con, "webhook_ultimo", "0"))
        fila = [dict(r) for r in con.execute("SELECT id, package, title, body, recebido_em FROM inbox WHERE id > ? ORDER BY id", (ultimo,))]
    enviados = 0
    for n in fila:
        quando = datetime.strptime(n["recebido_em"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=settings.tz)
        status, _ = _post(f"{base}/api/v1/transaction/webhook", chave_api,
                          {"package": n["package"], "title": n["title"], "text": n["body"], "timestamp": int(quando.timestamp() * 1000)},
                          timeout)
        if status == 401:
            raise ErroSync("Chave recusada pelo servidor (confira a API_KEY).")
        if status not in (202, 422):     # 503 (fila cheia) e outros: tenta de novo na próxima vez
            break
        with conectar() as con:
            _definir_cliente(con, "webhook_ultimo", n["id"])
        enviados += 1
    return {"modo": "webhook", "enviadas": enviados, "recebidas": 0, "aceitas": enviados, "recusadas": 0}
