"""Modelo de partes, importação e saldos: os casos que a planilha antiga não sabia representar."""

import json
from datetime import date

from app import db, importadores, servicos

EXTRATO = """\
                                                                                  Total de entradas                           +1.000,00
                                                                                  Total de saídas                              -2.000,00
01 OUT 2026       Total de entradas                                                                                            + 1.000,00
                  Transferência recebida pelo Pix          ANA EXEMPLO DA SILVA - •••.123.456-•• - BCO                             600,00
                  Transferência recebida pelo Pix          EMPRESA EXEMPLO LTDA - 00.000.000                                       400,00
                  Total de saídas                                                                                              - 2.000,00
                  Pagamento de boleto efetuado             IMOBILIARIA EXEMPLO LTDA                                               1.850,00
                  Compra no débito                         MERCADINHO EXEMPLO                                                        150,00
"""

FATURA = """\
Data de vencimento: 08 NOV 2026
no valor de
R$ 500,00
TRANSAÇÕES      DE 01 OUT A 01 NOV
              03 OUT       •••• 1111   Uber - NuPay                                                           R$ 12,00
              05 OUT       •••• 2222   Shopee *Loja - Parcela 2/10                                           R$ 120,00
              06 OUT       •••• 2222   Picpay*Fulano                                                         R$ 104,90
              07 OUT           Pagamento em 07 OUT                                                          −R$ 400,00
"""


def lancs(con):
    return servicos.lancamentos(con, limite=1000)


def test_extrato_que_nao_fecha_e_recusado():
    ruim = EXTRATO.replace("+1.000,00", "+1.000,01", 1)
    try:
        importadores.ler_extrato_pdf(ruim)
    except ValueError as e:
        assert "não fecha" in str(e)
    else:
        raise AssertionError("extrato inconsistente passou")


def test_contraparte_sem_cpf_nem_banco():
    lt = importadores.ler_extrato_pdf(EXTRATO)
    assert lt.movimentos[0].contraparte == "ANA EXEMPLO DA SILVA"


def test_boleto_do_aluguel_vira_parte_sua_mais_acertos(con):
    lt = importadores.ler_extrato_pdf(EXTRATO)
    for m in lt.movimentos:
        servicos.inserir(con, m.conta, m.data, m.valor, m.descricao, m.contraparte, "extrato_pdf")
    boleto = next(l for l in lancs(con) if "boleto" in l["descricao"])
    assert boleto["pendente"] and not boleto["partes"]        # o rateio pode mudar: só sugere
    por = {(p["natureza"], p["categoria"] or p["pessoa"]): p["valor"] for p in boleto["sugestao"]}
    assert por[("gasto", "aluguel-condominio")] == -629.0
    assert por[("acerto", "ana")] == -555.0
    assert por[("acerto", "bruno")] == -666.0
    assert round(sum(por.values()), 2) == -1850.0
    ana = next(l for l in lancs(con) if "ANA" in l["contraparte"])
    assert ana["pendente"] and ana["sugestao"][0]["natureza"] == "acerto"   # Pix com pessoa: só sugestão
    salario = next(l for l in lancs(con) if "EMPRESA" in l["contraparte"])
    assert not salario["pendente"] and salario["partes"][0]["categoria"] == "salario"


def test_recarga_picpay_separa_taxa_e_pede_o_principal(con):
    servicos.inserir(con, "nubank_cartao", "2026-10-06", -104.90, "Picpay*Fulano", origem="fatura_pdf")
    l = lancs(con)[0]
    taxa = next(p for p in l["partes"] if p["categoria"] == "juros")
    assert abs(taxa["valor"] + 4.90) < 0.01
    assert l["pendente"]


def test_pix_do_titular_e_transferencia(con, monkeypatch):
    from app.config import settings
    a = servicos.inserir(con, "nubank_conta", "2026-10-02", 300.0, "Transferência recebida pelo Pix", "FULANO DE TAL - BCO X", "extrato_pdf")
    monkeypatch.setattr(settings, "TITULAR", "Fulano de Tal")
    b = servicos.inserir(con, "nubank_conta", "2026-10-03", 300.0, "Transferência recebida pelo Pix", "FULANO DE TAL - BCO X", "extrato_pdf")
    por_id = {l["id"]: l for l in lancs(con)}
    assert por_id[a]["pendente"]                                       # sem titular, é Pix de alguém
    assert por_id[b]["partes"][0]["natureza"] == "transferencia"


def test_reimportar_nao_duplica_e_push_casa_com_fatura(con, monkeypatch):
    monkeypatch.setattr(importadores, "texto_pdf", lambda b: FATURA)
    # O celular viu a corrida antes do PDF.
    servicos.inserir(con, "nubank_cartao", "2026-10-04", -12.00, "Uber", origem="push")
    r1 = servicos.importar(con, "fatura.pdf", b"%PDF-x", date(2026, 10, 26))
    r2 = servicos.importar(con, "fatura.pdf", b"%PDF-x", date(2026, 10, 26))
    assert (r1["novos"], r1["casados"]) == (3, 1)
    assert (r2["novos"], r2["casados"], r2["repetidos"]) == (0, 0, 4)
    assert len([l for l in lancs(con) if abs(l["valor"] + 12) < 0.01]) == 1


def test_parcelas_futuras_projetadas(con):
    servicos.inserir(con, "nubank_cartao", "2026-10-05", -120.00, "Shopee *Loja - Parcela 2/10", origem="fatura_pdf", parcela="2/10")
    comp = servicos.compromissos(con, date(2026, 10, 26))
    assert [c["parcela"] for c in comp] == [f"{n}/10" for n in range(3, 11)]
    assert comp[0]["mes"] == "2026-11"


def test_colega_pagou_por_voce_e_saldo_da_pessoa(con):
    db.definir_parametro(con, "pessoas_ajuste", json.dumps({"data": "2026-10-26", "saldos": {"ana": -100.0}}))
    servicos.inserir(con, "nubank_conta", "2026-11-03", 0.0, "Conta de luz", "Ana", origem="manual",
                     partes=[{"valor": -150.0, "natureza": "gasto", "categoria": "contas-casa"},
                             {"valor": 150.0, "natureza": "acerto", "pessoa": "ana"}])
    servicos.inserir(con, "nubank_conta", "2026-11-05", -250.0, "Transferência enviada pelo Pix", "Ana", origem="manual",
                     partes=[{"valor": -250.0, "natureza": "acerto", "pessoa": "ana"}])
    ana = next(p for p in servicos.saldo_pessoas(con) if p["id"] == "ana")
    assert ana["saldo"] == 0.0          # devia 100 + 150 da luz, pagou 250


def test_lembrar_vira_sugestao_nunca_classifica_sozinho(con):
    a = servicos.inserir(con, "nubank_conta", "2026-10-01", -40.0, "Transferência enviada pelo Pix", "Fulano de Tal", "manual")
    b = servicos.inserir(con, "nubank_conta", "2026-10-09", -45.0, "Transferência enviada pelo Pix", "Fulano de Tal", "manual")
    servicos.definir_partes(con, a, [{"valor": -40.0, "natureza": "gasto", "categoria": "consultas"}], lembrar=True)
    outro = next(l for l in lancs(con) if l["id"] == b)
    assert outro["pendente"] and outro["sugestao"][0]["categoria"] == "consultas" and outro["sugestao"][0]["valor"] == -45.0
    c = servicos.inserir(con, "nubank_conta", "2026-11-09", -50.0, "Transferência enviada pelo Pix", "Fulano de Tal", "manual")
    novo = next(l for l in lancs(con) if l["id"] == c)
    assert novo["pendente"] and novo["sugestao"][0]["categoria"] == "consultas"


def test_pagamento_no_cartao_sem_par_na_conta_pergunta_quem_pagou(con):
    servicos.inserir(con, "nubank_conta", "2026-10-04", -500.0, "Pagamento de fatura", "", "extrato_pdf")
    com_par = servicos.inserir(con, "nubank_cartao", "2026-10-04", 500.0, "Pagamento em 04 OUT", "", "fatura_pdf")
    sem_par = servicos.inserir(con, "nubank_cartao", "2026-10-10", 300.0, "Pagamento em 10 OUT", "", "fatura_pdf")
    por_id = {l["id"]: l for l in lancs(con)}
    assert por_id[com_par]["partes"][0]["natureza"] == "transferencia"
    assert por_id[sem_par]["pendente"]          # alguém pagou a fatura por você? você diz


def test_parcela_seguinte_herda_a_classificacao(con):
    p1 = servicos.inserir(con, "nubank_cartao", "2026-10-09", -530.00, "Pix no Crédito - LOJA EXEMPLO - 1/4", origem="fatura_csv", parcela="1/4",
                          partes=[{"valor": -480.00, "natureza": "transferencia"}, {"valor": -50.00, "natureza": "acerto", "pessoa": "mae"}])
    p2 = servicos.inserir(con, "nubank_cartao", "2026-11-09", -530.00, "Pix no Crédito - LOJA EXEMPLO - 2/4", origem="fatura_csv", parcela="2/4")
    l2 = next(l for l in lancs(con) if l["id"] == p2)
    assert not l2["pendente"] and {p["natureza"] for p in l2["partes"]} == {"transferencia", "acerto"}
    # as que faltam são de quem está no acerto: entram como reembolso na projeção
    comp = servicos.compromissos(con, date(2026, 11, 20))
    assert [(c["parcela"], c["pessoa"]) for c in comp] == [("3/4", "mae"), ("4/4", "mae")]


def test_saldo_informado_mostra_o_que_falta_lancar(con):
    servicos.inserir(con, "nubank_conta", "2026-10-25", -27.0, "Compra no débito", "MERCADINHO EXEMPLO", "extrato_pdf")
    servicos.informar_saldo(con, "nubank_conta", 150.0, "2026-10-26")
    c = next(x for x in servicos.saldo_contas(con) if x["id"] == "nubank_conta")
    assert c["saldo_real"] == 150.0 and c["diferenca"] == round(150.0 - (0.0 - 27.0), 2)


def test_partes_que_nao_somam_sao_recusadas(con):
    a = servicos.inserir(con, "nubank_conta", "2026-10-01", -40.0, "X", "", "manual")
    try:
        servicos.definir_partes(con, a, [{"valor": -30.0, "natureza": "gasto", "categoria": "outros"}], False)
    except ValueError as e:
        assert "somam" in str(e)
    else:
        raise AssertionError


def test_fatura_csv_com_ponto_decimal():
    lt = importadores.ler_fatura_csv("date,title,amount\n2026-10-03,Netflix.com,32.9\n2026-10-04,Uber *Trip,23.10\n"
                                     "2026-10-07,Pagamento recebido,-1203.83\n", date(2026, 10, 26))
    assert [m.valor for m in lt.movimentos] == [-32.9, -23.1, 1203.83]
    assert importadores.numero("1.234") == 1234 and importadores.numero("R$ 1.250,90") == 1250.9


def test_pdf_sem_poppler_explica_o_que_fazer(monkeypatch):
    import pytest
    monkeypatch.setenv("PATH", "/nao/existe")
    with pytest.raises(ValueError, match="Importe o .csv ou o .xlsx"):
        importadores.ler_arquivo("extrato.pdf", b"%PDF-1.4 qualquer coisa")
