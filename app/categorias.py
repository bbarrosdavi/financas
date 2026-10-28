"""Vocabulário inicial: contas, categorias, regras e parâmetros que todo banco novo recebe.

Só o ponto de partida. Pessoas, tetos, metas e eventos você cadastra no site. Alimentação vem
separada em mercado, conveniência, RU e delivery; moradia em fixo e contas; juros e taxas são gasto
próprio, para que o custo do crédito apareça. Pagamento de dívida não é categoria, é acerto ou
transferência (ver app/db.py).
"""

import sqlite3

CONTAS = [
    # id, nome, tipo, saldo inicial, limite (o saldo e a data dele você ajusta no site)
    ("nubank_conta", "Nubank conta", "corrente", 0.0, None),
    ("nubank_cartao", "Nubank cartão", "cartao", 0.0, None),
    ("picpay", "PicPay", "carteira", 0.0, None),
]

# id, nome, tipo, como aparece no extrato, sugestão quando entra, sugestão quando sai
PESSOAS: list[tuple] = []

# id, grupo, nome, tipo, teto mensal (None = sem teto), fixa
CATEGORIAS = [
    ("aluguel-condominio", "Moradia", "Aluguel e condomínio", "gasto", None, 1),
    ("contas-casa", "Moradia", "Contas da casa (luz, gás, internet)", "gasto", None, 1),
    ("casa-moveis", "Moradia", "Casa e móveis", "gasto", None, 0),
    ("mercado", "Alimentação", "Mercado planejado", "gasto", None, 0),
    ("ru", "Alimentação", "RU (dias de aula)", "gasto", None, 0),
    ("conveniencia", "Alimentação", "Conveniência e lanches", "gasto", None, 0),
    ("delivery", "Alimentação", "Delivery e restaurante", "gasto", None, 0),
    ("remedios", "Saúde", "Remédios", "gasto", None, 1),
    ("consultas", "Saúde", "Consultas e terapia", "gasto", None, 1),
    ("academia", "Saúde", "Academia", "gasto", None, 1),
    ("saude-outros", "Saúde", "Saúde (outros)", "gasto", None, 0),
    ("app-transporte", "Transporte", "App (Uber/99)", "gasto", None, 0),
    ("onibus", "Transporte", "Ônibus e combustível", "gasto", None, 0),
    ("assinaturas", "Assinaturas", "Assinaturas e celular", "gasto", None, 1),
    ("ferramentas", "Trabalho", "Ferramentas de trabalho", "gasto", None, 0),
    ("eletronicos", "Compras", "Eletrônicos", "gasto", None, 0),
    ("vestuario", "Compras", "Vestuário e imagem", "gasto", None, 0),
    ("lazer", "Lazer", "Lazer e rolê", "gasto", None, 0),
    ("viagem", "Lazer", "Viagem", "gasto", None, 0),
    ("hobbies", "Lazer", "Hobbies", "gasto", None, 0),
    ("pets", "Casa", "Pets", "gasto", None, 0),
    ("familia", "Família", "Família e presentes", "gasto", None, 0),
    ("juros", "Financeiro", "Juros e taxas", "gasto", None, 0),
    ("outros", "Outros", "Outros", "gasto", None, 0),
    ("salario", "Renda", "Salário", "renda", None, 1),
    ("pais", "Renda", "Ajuda dos pais", "renda", None, 0),
    ("extras", "Renda", "Extras", "renda", None, 0),
    ("outras-entradas", "Renda", "Outras entradas", "renda", None, 0),
]

# Regras do sistema: regex sobre "DESCRICAO | CONTRAPARTE" em maiúsculas.
# A primeira que casa vence; casos que dividem o valor ficam em app/classificar.py.
REGRAS = [
    (r"DL\*GOOGLE|GOOGLE ONE|GOOGLE GOOGLE|TIM\*|\bTIM\b", "gasto", "assinaturas", None),
    (r"SMART FIT", "gasto", "academia", None),
    (r"RAIA|DROGASIL|PANVEL|NISSEI|FARMAIS|DRUGSTORE|FARMACIA", "gasto", "remedios", None),
    (r"CONVENIENCIA", "gasto", "conveniencia", None),
    (r"ASSAI|ATACAD|SUPERMERCADO|SUPERMECADO", "gasto", "mercado", None),
    (r"IFOOD|ANOTA AI|99 FOOD|RESTAURANTE|ESPETARIA|SUBWAY|ACAI|CHURRASCARIA|PIZZA|HAMBURG|PADARI|LANCHONETE", "gasto", "delivery", None),
    (r"\bPUB\b|ZIG\*|TABACARIA", "gasto", "lazer", None),
    (r"POUSADA", "gasto", "viagem", None),
    (r"^UBER|\bUBER\b|99 NUPAY|^99\b|NUPAY 99$|99 TECNOLOGIA", "gasto", "app-transporte", None),
    (r"TRANSP COLET|AUTO POSTO|LAVA JATO", "gasto", "onibus", None),
    (r"FISIA|NIKE", "gasto", "vestuario", None),
    (r"ALIEXPRESS|KALUNGA|AMERICANAS", "gasto", "eletronicos", None),
]

PARAMETROS = {
    "salario_mensal": "0",
    "dia_renda_mes_seguinte": "25",
    # Rateio do boleto da imobiliária entre os moradores: {"eu": 0.5, "<id da pessoa>": 0.5}. Vazio = não sugere.
    "aluguel_rateio": "{}",
    "taxa_ponte_picpay": "0.049",
}

# Eventos do plano (renda que acaba, compra grande): você cadastra no site.
EVENTOS: list[tuple] = []


def semear(con: sqlite3.Connection) -> None:
    for c in CONTAS:
        con.execute("INSERT OR IGNORE INTO contas (id, nome, tipo, saldo_inicial, limite) VALUES (?,?,?,?,?)", c)
    for p in PESSOAS:
        con.execute("INSERT OR IGNORE INTO pessoas (id, nome, tipo, apelido_extrato, sugere_entrada, sugere_saida) "
                    "VALUES (?,?,?,?,?,?)", p)
    for ordem, (cid, grupo, nome, tipo, teto, fixa) in enumerate(CATEGORIAS):
        con.execute(
            "INSERT OR IGNORE INTO categorias (id, grupo, nome, tipo, teto, fixa, ordem) VALUES (?,?,?,?,?,?,?)",
            (cid, grupo, nome, tipo, teto, fixa, ordem),
        )
    for padrao, natureza, categoria, pessoa in REGRAS:
        con.execute(
            "INSERT OR IGNORE INTO regras (padrao, natureza, categoria, pessoa, origem) VALUES (?,?,?,?, 'sistema')",
            (padrao, natureza, categoria, pessoa),
        )
    for k, v in PARAMETROS.items():
        con.execute("INSERT OR IGNORE INTO parametros (chave, valor) VALUES (?, ?)", (k, v))
    if not con.execute("SELECT 1 FROM parametros WHERE chave='eventos_semeados'").fetchone():
        for nome, tipo, inicio, fim, valor in EVENTOS:
            con.execute("INSERT INTO eventos (nome, tipo, inicio, fim, valor) VALUES (?,?,?,?,?)", (nome, tipo, inicio, fim, valor))
        con.execute("INSERT INTO parametros (chave, valor) VALUES ('eventos_semeados', '1')")
