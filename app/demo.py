"""Dados de demonstração: seis meses inventados de alguém que divide o apartamento, para o tour e para explorar.

Ficam num banco à parte (`<banco>-demonstracao.db`), ligado por um marcador ao lado do banco de verdade (ver
db.caminho): enquanto ele existe, a tela lê e escreve na demonstração; remover apaga o banco dela e o marcador.
O push do celular, o webhook e a sincronização usam sempre o banco de verdade (db.conectar_real): nada real se
perde e nada inventado sai daqui. Só liga num banco sem lançamentos.

Pessoas, lugares e valores são inventados. O guia (scripts/guia_prints.py) usa este mesmo conjunto, com hoje fixo.
"""

import calendar
import json
import random
from datetime import date, timedelta

from app import db, servicos

SIGLAS = ["JAN", "FEV", "MAR", "ABR", "MAI", "JUN", "JUL", "AGO", "SET", "OUT", "NOV", "DEZ"]


def _gasto(v, cat):
    return [{"valor": v, "natureza": "gasto", "categoria": cat}]


def _mes(hoje: date, k: int) -> tuple[int, int]:
    """Ano e mês k meses depois de hoje (k negativo: antes)."""
    m = hoje.year * 12 + hoje.month - 1 + k
    return m // 12, m % 12 + 1


def semear(c, hoje: date) -> None:
    """Preenche um banco novo com os seis meses que terminam hoje."""
    sorte = random.Random(2026)
    inicio = date(*_mes(hoje, -5), 1)
    aaaamm = lambda k: "%d-%02d" % _mes(hoje, k)
    c.executemany("INSERT INTO pessoas (id, nome, tipo, apelido_extrato, sugere_entrada, sugere_saida) VALUES (?,?,?,?,?,?)",
                  [("marina", "Marina", "colega", "MARINA EXEMPLO", "acerto", "acerto"),
                   ("teo", "Téo", "colega", "TEO FICTICIO", "acerto", "acerto"),
                   ("mae", "Mãe", "familia", "ROSA EXEMPLO", "renda:pais", "acerto")])
    for cid, teto in {"mercado": 600, "delivery": 250, "app-transporte": 150, "lazer": 200, "conveniencia": 100,
                      "vestuario": 150, "eletronicos": 150, "remedios": 80, "academia": 90, "assinaturas": 60,
                      "contas-casa": 150, "onibus": 80}.items():
        c.execute("UPDATE categorias SET teto = ? WHERE id = ?", (teto, cid))
    c.execute("UPDATE categorias SET orcar_por_itens = 1 WHERE id = 'aluguel-condominio'")
    c.executemany("INSERT INTO itens_fixos (categoria, nome, valor, ordem) VALUES (?,?,?,?)",
                  [("aluguel-condominio", "Aluguel (minha metade)", 600, 1), ("aluguel-condominio", "Condomínio (minha metade)", 50, 2)])
    c.execute("UPDATE contas SET saldo_inicial = 300, data_saldo_inicial = ? WHERE id = 'nubank_conta'", (inicio.isoformat(),))
    c.execute("UPDATE contas SET saldo_inicial = 0, data_saldo_inicial = ?, limite = 3000 WHERE id = 'nubank_cartao'", (inicio.isoformat(),))
    c.execute("UPDATE contas SET data_saldo_inicial = ? WHERE id = 'picpay'", (inicio.isoformat(),))
    for k, v in {"salario_mensal": "2600", "horizonte": aaaamm(5), "aluguel_rateio": '{"eu": 0.5, "marina": 0.5}'}.items():
        db.definir_parametro(c, k, v)
    reserva = c.execute("INSERT INTO metas (nome, descricao, alvo, aporte_mensal, onde, ordem) VALUES "
                        "('Reserva de emergência', 'Seis meses de custo fixo', 6000, 300, 'Caixinha do Nubank', 1)").lastrowid
    c.execute("INSERT INTO metas (nome, alvo, data_alvo, aporte_mensal, onde, ordem) VALUES ('Notebook novo', 4500, ?, 250, "
              "'Caixinha do Nubank', 2)", (aaaamm(8),))
    dezembro = f"{hoje.year if hoje.month < 12 else hoje.year + 1}-12"
    c.executemany("INSERT INTO eventos (nome, tipo, inicio, fim, valor) VALUES (?,?,?,?,?)",
                  [("13º salário", "entrada_unica", dezembro, None, 2600),
                   ("Viagem de janeiro", "saida_unica", f"{hoje.year + 1}-01", None, 1800)])

    def lanc(conta, d, valor, desc, contra="", origem=None, partes=None, parcela=None):
        if d > hoje:
            return
        origem = origem or ("fatura_csv" if conta == "nubank_cartao" else "extrato_csv")
        servicos.inserir(c, conta, d.isoformat(), round(valor, 2), desc, contra, origem, partes=partes, parcela=parcela)

    fatura_anterior = 0.0
    for i in range(6):                        # 0 = cinco meses atrás, 5 = este mês
        ano, mes = _mes(hoje, i - 5)
        ultimo = calendar.monthrange(ano, mes)[1]
        d = lambda dia: date(ano, mes, min(dia, ultimo))
        lanc("nubank_conta", d(5), 2600, "Transferência recebida pelo Pix", "EMPRESA EXEMPLO LTDA", partes=[
            {"valor": 2600, "natureza": "renda", "categoria": "salario"}])
        lanc("nubank_conta", d(6), -1300, "Pagamento de boleto efetuado", "IMOBILIARIA EXEMPLO LTDA", partes=[
            {"valor": -650, "natureza": "gasto", "categoria": "aluguel-condominio"},
            {"valor": -650, "natureza": "acerto", "pessoa": "marina"}])
        lanc("nubank_conta", d(6), -300, "Aplicação RDB", partes=[{"valor": -300, "natureza": "poupanca", "meta": reserva}])
        if fatura_anterior:
            lanc("nubank_conta", d(7), -fatura_anterior, "Pagamento de fatura")
            lanc("nubank_cartao", d(7), fatura_anterior, f"Pagamento em 07 {SIGLAS[mes - 1]}")
        if i < 5:                             # a metade da Marina deste mês ainda não chegou
            lanc("nubank_conta", d(10), 650, "Transferência recebida pelo Pix", "MARINA EXEMPLO", partes=[
                {"valor": 650, "natureza": "acerto", "pessoa": "marina"}])
        luz = -sorte.choice([78.4, 85.1, 91.7])
        lanc("nubank_conta", d(12), luz, "Pagamento de boleto efetuado", "LUZ DISTRIBUIDORA EXEMPLO", partes=_gasto(luz, "contas-casa"))
        lanc("nubank_conta", d(14), 200, "Transferência recebida pelo Pix", "ROSA EXEMPLO", partes=[
            {"valor": 200, "natureza": "renda", "categoria": "pais"}])
        cartao = [(3, -90, "Academia Movimento Exemplo", "academia"), (9, -39.9, "Streaming Exemplo", "assinaturas"),
                  (15, -19.9, "Música Exemplo", "assinaturas")]
        cartao += [(dia, -round(sorte.uniform(110, 190), 2), "Supermercado Exemplo", "mercado") for dia in (4, 13, 24)]
        cartao += [(dia, -round(sorte.uniform(35, 65), 2), "Delivery Cozinha Exemplo", "delivery") for dia in (8, 17, 27)]
        cartao += [(dia, -round(sorte.uniform(14, 28), 2), "Uber *Trip", "app-transporte") for dia in (2, 9, 16, 22, 29)]
        cartao += [(11, -round(sorte.uniform(35, 60), 2), "Cinema Exemplo", "lazer"), (25, -round(sorte.uniform(60, 95), 2), "Bar do Exemplo", "lazer")]
        cartao += [(19, -round(sorte.uniform(30, 60), 2), "Drogaria Exemplo", "remedios")]
        cartao += [(dia, -round(sorte.uniform(9, 20), 2), "Conveniencia Posto Exemplo", "conveniencia") for dia in (6, 21)]
        if i in (1, 3):
            cartao.append((18, -round(sorte.uniform(80, 140), 2), "Loja Roupa Exemplo", "vestuario"))
        for dia, v, desc, cat in cartao:
            lanc("nubank_cartao", d(dia), v, desc, partes=_gasto(v, cat))
        if i >= 3:                            # uma compra em 6 parcelas, a 1ª há dois meses
            lanc("nubank_cartao", d(11), -250, f"Loja Eletro Exemplo - Parcela {i - 2}/6", partes=_gasto(-250, "eletronicos"),
                 parcela=f"{i - 2}/6")
        if i == 4:
            lanc("nubank_cartao", d(19), -120, "Restaurante Exemplo", partes=[
                {"valor": -60, "natureza": "gasto", "categoria": "delivery"}, {"valor": -60, "natureza": "acerto", "pessoa": "teo"}])
        fatura_anterior = -round(sum(r[0] for r in c.execute(
            "SELECT valor FROM lancamentos WHERE conta = 'nubank_cartao' AND valor < 0 AND substr(data, 1, 7) = ?",
            (f"{ano}-{mes:02d}",))), 2)
    # Deste mês, o que ainda espera classificação
    dia = lambda menos: date(hoje.year, hoje.month, max(1, hoje.day - menos)).isoformat()
    servicos.inserir(c, "nubank_conta", dia(3), -18.5, "Padaria Pão Quente", origem="push", ref="inbox:1")
    servicos.inserir(c, "nubank_cartao", dia(5), -104.9, "Picpay*Recarga Exemplo", origem="fatura_csv")
    servicos.inserir(c, "nubank_conta", dia(4), -30.0, "Transferência enviada pelo Pix", "TEO FICTICIO", "extrato_csv")
    servicos.inserir(c, "nubank_cartao", dia(2), -89.9, "Loja Nova Exemplo", origem="push", ref="inbox:2")
    db.definir_parametro(c, "pessoas_ajuste", json.dumps({"data": (inicio - timedelta(days=1)).isoformat(), "saldos": {}}))


def _apagar_banco() -> None:
    demo = db.banco_demonstracao()
    for f in (demo, demo.with_name(demo.name + "-wal"), demo.with_name(demo.name + "-shm")):
        f.unlink(missing_ok=True)


def ligar(hoje: date | None = None) -> None:
    """Cria a demonstração e passa a tela para ela. Recusa se o banco de verdade já tem lançamentos."""
    with db.conectar_real() as con:
        if con.execute("SELECT 1 FROM lancamentos LIMIT 1").fetchone():
            raise ValueError("A demonstração só liga num Finanças sem lançamentos: aqui já há dados de verdade.")
    db.marcador_demonstracao().unlink(missing_ok=True)
    _apagar_banco()
    db.iniciar(db.banco_demonstracao())
    with db.conectar(db.banco_demonstracao()) as con:
        semear(con, hoje or date.today())
    db.marcador_demonstracao().touch()


def desligar() -> None:
    """Volta a tela para o banco de verdade e apaga a demonstração (e o que foi mexido nela)."""
    db.marcador_demonstracao().unlink(missing_ok=True)
    _apagar_banco()
