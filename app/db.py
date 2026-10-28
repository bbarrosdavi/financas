"""Banco SQLite e o modelo de dados.

Um lançamento é um movimento de dinheiro numa conta, com o sinal da conta:
negativo sai, positivo entra. No cartão, compra é negativa e pagamento de fatura
ou estorno é positivo, então o saldo do cartão é menos a dívida.

O significado mora nas **partes**. Todo lançamento se divide em uma ou mais
partes que somam o valor dele, e cada parte tem uma natureza:

- ``gasto``: consumo seu, com categoria de gasto (estorno é gasto positivo).
- ``renda``: dinheiro que é seu, com categoria de renda.
- ``transferencia``: dinheiro entre contas suas (pagar a fatura, Pix no crédito
  caindo na conta, ponte do PicPay). Não é gasto nem renda.
- ``acerto``: dinheiro que alguém te deve ou que você deve a alguém (colegas,
  família, quem parcelou algo para você). O saldo de cada pessoa é a soma das partes de acerto com o
  sinal trocado: você pagou por ela (parte negativa), ela te deve.
- ``poupanca``: dinheiro seu indo para uma meta (reserva, compra planejada) numa
  conta separada. Aporte é negativo na conta de origem; resgate é positivo e
  desconta da meta. Não é gasto nem renda.

Assim o boleto do aluguel dividido com dois colegas vira a sua parte como gasto
mais duas partes de acerto, e o Pix de um deles devolvendo a parte dele é só acerto. Nada de despesa
negativa inventada.

Lançamento com parte sem categoria (ou sem pessoa, no acerto) está pendente.
"""

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from app.config import settings

NATUREZAS = ("gasto", "renda", "transferencia", "acerto", "poupanca")

SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS contas (
    id TEXT PRIMARY KEY,
    nome TEXT NOT NULL,
    tipo TEXT NOT NULL CHECK (tipo IN ('corrente','cartao','carteira')),
    saldo_inicial REAL NOT NULL DEFAULT 0,
    data_saldo_inicial TEXT NOT NULL DEFAULT '2026-01-01',
    limite REAL
);

CREATE TABLE IF NOT EXISTS pessoas (
    id TEXT PRIMARY KEY,
    nome TEXT NOT NULL,
    tipo TEXT NOT NULL CHECK (tipo IN ('colega','familia','credor','outro')),
    -- Como o nome aparece no extrato, e o que sugerir quando o dinheiro entra ou sai
    -- ('acerto' ou 'renda:<categoria>' / 'gasto:<categoria>'). Só sugestão: você confirma.
    apelido_extrato TEXT NOT NULL DEFAULT '',
    sugere_entrada TEXT NOT NULL DEFAULT 'acerto',
    sugere_saida TEXT NOT NULL DEFAULT 'acerto'
);

CREATE TABLE IF NOT EXISTS categorias (
    id TEXT PRIMARY KEY,
    grupo TEXT NOT NULL,
    nome TEXT NOT NULL,
    tipo TEXT NOT NULL CHECK (tipo IN ('gasto','renda')),
    teto REAL,
    fixa INTEGER NOT NULL DEFAULT 0,
    ordem INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS lancamentos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    data TEXT NOT NULL,
    conta TEXT NOT NULL REFERENCES contas(id),
    valor REAL NOT NULL,
    descricao TEXT NOT NULL,
    contraparte TEXT NOT NULL DEFAULT '',
    origem TEXT NOT NULL,
    ref TEXT NOT NULL DEFAULT '',
    chave TEXT UNIQUE,
    parcela TEXT,
    nota TEXT NOT NULL DEFAULT '',
    sugestao TEXT,
    confirmado_por TEXT,
    criado_em TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS ix_lanc_data ON lancamentos(data);
CREATE INDEX IF NOT EXISTS ix_lanc_conta_valor ON lancamentos(conta, valor);

CREATE TABLE IF NOT EXISTS partes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lancamento_id INTEGER NOT NULL REFERENCES lancamentos(id) ON DELETE CASCADE,
    valor REAL NOT NULL,
    natureza TEXT NOT NULL CHECK (natureza IN ('gasto','renda','transferencia','acerto','poupanca')),
    categoria TEXT REFERENCES categorias(id),
    pessoa TEXT REFERENCES pessoas(id),
    meta INTEGER REFERENCES metas(id),
    obs TEXT NOT NULL DEFAULT '',          -- sua observação
    motivo TEXT NOT NULL DEFAULT ''        -- por que o sistema classificou ou sugeriu assim
);
CREATE INDEX IF NOT EXISTS ix_partes_lanc ON partes(lancamento_id);

-- Regras de classificação: as do sistema e as que você ensina ao classificar.
CREATE TABLE IF NOT EXISTS regras (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    padrao TEXT NOT NULL,
    natureza TEXT NOT NULL,
    categoria TEXT,
    pessoa TEXT,
    origem TEXT NOT NULL DEFAULT 'aprendida',
    criada_em TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    UNIQUE (padrao, origem)
);

-- Parcelas já contratadas que ainda vão cair (vêm das faturas futuras).
CREATE TABLE IF NOT EXISTS parcelas_futuras (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conta TEXT NOT NULL,
    mes TEXT NOT NULL,
    descricao TEXT NOT NULL,
    valor REAL NOT NULL,
    parcela TEXT,
    pessoa TEXT,
    UNIQUE (conta, mes, descricao, parcela)
);

CREATE TABLE IF NOT EXISTS importacoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    arquivo TEXT NOT NULL,
    tipo TEXT NOT NULL,
    quando TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    novos INTEGER NOT NULL,
    casados INTEGER NOT NULL,
    repetidos INTEGER NOT NULL
);

-- Metas de poupança (a tabela "Savings" da planilha): objetivo, prazo e aporte planejado por mês.
CREATE TABLE IF NOT EXISTS metas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    descricao TEXT NOT NULL DEFAULT '',
    alvo REAL,
    data_alvo TEXT,
    aporte_mensal REAL NOT NULL DEFAULT 0,
    onde TEXT NOT NULL DEFAULT '',
    ativa INTEGER NOT NULL DEFAULT 1,
    ordem INTEGER NOT NULL DEFAULT 0,
    criada_em TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

-- Orçamento por mês (o Budget Planning da planilha). Chave = id da categoria ou 'meta:<id>'.
-- Sem linha = vale o padrão (teto da categoria, renda base no salário, aporte mensal da meta).
CREATE TABLE IF NOT EXISTS orcamento (
    chave TEXT NOT NULL,
    mes TEXT NOT NULL,
    valor REAL NOT NULL,
    PRIMARY KEY (chave, mes)
);

-- Despesas fixas (a aba "Despesas Fixas" da planilha): os itens que você planeja gastar em cada categoria.
-- Com categorias.orcar_por_itens, o orçamento padrão da categoria no mês é a soma dos itens válidos nele.
CREATE TABLE IF NOT EXISTS itens_fixos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    categoria TEXT NOT NULL REFERENCES categorias(id),
    nome TEXT NOT NULL,
    valor REAL NOT NULL,
    inicio TEXT,
    fim TEXT,
    ordem INTEGER NOT NULL DEFAULT 0
);

-- Eventos do plano: mudanças de renda ou de custo a partir de um mês, entradas ou saídas únicas.
CREATE TABLE IF NOT EXISTS eventos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    tipo TEXT NOT NULL CHECK (tipo IN ('renda_mensal','gasto_mensal','entrada_unica','saida_unica')),
    inicio TEXT NOT NULL,
    fim TEXT,
    valor REAL NOT NULL,
    ativo INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS parametros (
    chave TEXT PRIMARY KEY,
    valor TEXT NOT NULL
);

-- Caixa de entrada do celular:
-- a notificação é gravada antes do 202, e só vira 'done' com o lançamento salvo.
CREATE TABLE IF NOT EXISTS inbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dedup_hash TEXT NOT NULL,
    package TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    recebido_em TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT
);
CREATE INDEX IF NOT EXISTS ix_inbox_hash ON inbox(dedup_hash, recebido_em);

CREATE TABLE IF NOT EXISTS ignorados (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    inbox_id INTEGER,
    package TEXT, title TEXT, body TEXT,
    motivo TEXT NOT NULL,
    quando TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
"""


def caminho_real() -> Path:
    return Path(settings.DATABASE_PATH)


def banco_demonstracao(real: Path | None = None) -> Path:
    real = real or caminho_real()
    return real.with_name(real.stem + "-demonstracao.db")


def marcador_demonstracao(real: Path | None = None) -> Path:
    real = real or caminho_real()
    return real.with_name(real.name + ".demonstracao")


def demo_ativa() -> bool:
    return marcador_demonstracao().exists()


def caminho() -> Path:
    """O banco da tela: o de verdade, ou o de demonstração enquanto ela estiver ligada (ver app/demo.py)."""
    return banco_demonstracao() if demo_ativa() else caminho_real()


@contextmanager
def conectar(path: str | Path | None = None):
    con = sqlite3.connect(str(path or caminho()), timeout=15)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def conectar_real():
    """O banco de verdade, mesmo com a demonstração ligada: push, webhook e sincronização nunca vão para ela."""
    return conectar(caminho_real())


def iniciar(path: str | Path | None = None) -> None:
    p = Path(path or caminho_real())
    p.parent.mkdir(parents=True, exist_ok=True)
    with conectar(p) as con:
        con.executescript(SCHEMA)
        _migrar(con)
        from app import categorias, sync
        categorias.semear(con)
        sync.preparar(con)          # depois de semear: o vocabulário inicial entra como o mais antigo possível


def _migrar(con: sqlite3.Connection) -> None:
    """Colunas acrescentadas depois da primeira versão do banco."""
    def tem(tabela, coluna):
        return any(r["name"] == coluna for r in con.execute(f"PRAGMA table_info({tabela})"))
    if not tem("categorias", "cor"):
        con.execute("ALTER TABLE categorias ADD COLUMN cor TEXT")
    if not tem("categorias", "orcar_por_itens"):
        con.execute("ALTER TABLE categorias ADD COLUMN orcar_por_itens INTEGER NOT NULL DEFAULT 0")
    if not tem("lancamentos", "sugestao"):
        con.execute("ALTER TABLE lancamentos ADD COLUMN sugestao TEXT")
    for col, padrao in (("apelido_extrato", "''"), ("sugere_entrada", "'acerto'"), ("sugere_saida", "'acerto'")):
        if not tem("pessoas", col):
            con.execute(f"ALTER TABLE pessoas ADD COLUMN {col} TEXT NOT NULL DEFAULT {padrao}")
    # A restrição de natureza das partes ganhou 'poupanca' e a coluna meta: o SQLite não altera CHECK,
    # então a tabela é recriada com os mesmos dados.
    sql = con.execute("SELECT sql FROM sqlite_master WHERE name='partes'").fetchone()["sql"]
    if "poupanca" not in sql:
        con.commit()
        con.execute("PRAGMA foreign_keys=OFF")
        con.executescript("""
            CREATE TABLE partes_nova (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lancamento_id INTEGER NOT NULL REFERENCES lancamentos(id) ON DELETE CASCADE,
                valor REAL NOT NULL,
                natureza TEXT NOT NULL CHECK (natureza IN ('gasto','renda','transferencia','acerto','poupanca')),
                categoria TEXT REFERENCES categorias(id),
                pessoa TEXT REFERENCES pessoas(id),
                meta INTEGER REFERENCES metas(id),
                obs TEXT NOT NULL DEFAULT ''
            );
            INSERT INTO partes_nova (id, lancamento_id, valor, natureza, categoria, pessoa, obs)
                SELECT id, lancamento_id, valor, natureza, categoria, pessoa, obs FROM partes;
            DROP TABLE partes;
            ALTER TABLE partes_nova RENAME TO partes;
            CREATE INDEX IF NOT EXISTS ix_partes_lanc ON partes(lancamento_id);
        """)
        con.execute("PRAGMA foreign_keys=ON")
    if not tem("partes", "motivo"):
        con.execute("ALTER TABLE partes ADD COLUMN motivo TEXT NOT NULL DEFAULT ''")
    _separar_motivos(con)


def _separar_motivos(con: sqlite3.Connection) -> None:
    """A observação é sua. O que o classificador escrevia nela ("sugestão pela pessoa (confira)", "pagamento da
    fatura"...) vai para o motivo, nas partes e nas sugestões guardadas; as notas automáticas de lançamento manual
    ("lançado à mão", "pago por Fulano") saem, porque a origem já diz isso. Pode rodar sempre: só mexe no que falta."""
    from app.classificar import e_motivo
    for r in con.execute("SELECT id, obs FROM partes WHERE obs != '' AND motivo = ''").fetchall():
        if e_motivo(r["obs"]):
            con.execute("UPDATE partes SET motivo = obs, obs = '' WHERE id = ?", (r["id"],))
    for r in con.execute("SELECT id, sugestao FROM lancamentos WHERE sugestao IS NOT NULL").fetchall():
        sug, mudou = json.loads(r["sugestao"]), False
        for p in sug:
            if p.get("obs") and not p.get("motivo") and e_motivo(p["obs"]):
                p["motivo"], p["obs"], mudou = p["obs"], "", True
        if mudou:
            con.execute("UPDATE lancamentos SET sugestao = ? WHERE id = ?", (json.dumps(sug, ensure_ascii=False), r["id"]))
    con.execute("UPDATE lancamentos SET nota = '' WHERE origem = 'manual' AND "
                "(nota = 'lançado à mão' OR nota IN (SELECT 'pago por ' || nome FROM pessoas))")


# ---------------------------------------------------------------------------
# Consultas usadas por vários módulos
# ---------------------------------------------------------------------------

PENDENTE_SQL = """
    NOT EXISTS (SELECT 1 FROM partes p WHERE p.lancamento_id = l.id)
    OR EXISTS (SELECT 1 FROM partes p WHERE p.lancamento_id = l.id AND (
        (p.natureza IN ('gasto','renda') AND p.categoria IS NULL)
        OR (p.natureza = 'acerto' AND p.pessoa IS NULL)
        OR (p.natureza = 'poupanca' AND p.meta IS NULL)))
    OR ABS((SELECT COALESCE(SUM(p.valor),0) FROM partes p WHERE p.lancamento_id = l.id) - l.valor) > 0.005
"""


def gravar_partes(con: sqlite3.Connection, lancamento_id: int, partes: list[dict]) -> None:
    con.execute("DELETE FROM partes WHERE lancamento_id = ?", (lancamento_id,))
    for p in partes:
        con.execute(
            "INSERT INTO partes (lancamento_id, valor, natureza, categoria, pessoa, meta, obs, motivo) VALUES (?,?,?,?,?,?,?,?)",
            (lancamento_id, round(p["valor"], 2), p["natureza"], p.get("categoria"), p.get("pessoa"), p.get("meta"),
             p.get("obs") or "", p.get("motivo") or ""),
        )


def parametro(con: sqlite3.Connection, chave: str, padrao: str | None = None) -> str | None:
    row = con.execute("SELECT valor FROM parametros WHERE chave = ?", (chave,)).fetchone()
    return row["valor"] if row else padrao


def definir_parametro(con: sqlite3.Connection, chave: str, valor) -> None:
    con.execute("INSERT INTO parametros (chave, valor) VALUES (?, ?) ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor",
                (chave, str(valor)))
