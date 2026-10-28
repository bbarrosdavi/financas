"""A observação é sua; o porquê da classificação fica no motivo."""

import json

from app import db, servicos


def test_classificador_escreve_o_motivo_e_deixa_a_obs_vazia(con):
    lid = servicos.inserir(con, "nubank_conta", "2026-10-05", -500.0, "Pagamento de fatura", "", "extrato_pdf")
    p = servicos.lancamentos(con)[0]["partes"][0]
    assert p["id"] and p["obs"] == "" and p["motivo"] == "pagamento da fatura do cartão" and lid


def test_migracao_separa_textos_automaticos(con):
    lid = servicos.inserir(con, "nubank_conta", "2026-10-05", -50.0, "Transferência enviada", "Fulano", "manual",
                           nota="lançado à mão", partes=[{"valor": -50.0, "natureza": "gasto", "categoria": "outros",
                                                          "obs": "Pix pequeno (confira)"}])
    lid2 = servicos.inserir(con, "nubank_conta", "2026-10-06", -80.0, "Transferência enviada", "Ciclano", "extrato_pdf",
                            partes=[{"valor": -80.0, "natureza": "gasto", "categoria": "outros", "obs": "presente da mãe"}])
    con.execute("UPDATE partes SET motivo=''")
    con.execute("UPDATE lancamentos SET sugestao=? WHERE id=?",
                (json.dumps([{"valor": -80.0, "natureza": "gasto", "categoria": "outros", "obs": "como da última vez"}]), lid2))
    db._separar_motivos(con)
    l1, l2 = (next(x for x in servicos.lancamentos(con) if x["id"] == i) for i in (lid, lid2))
    assert l1["nota"] == "" and l1["partes"][0]["obs"] == "" and l1["partes"][0]["motivo"] == "Pix pequeno (confira)"
    assert l2["partes"][0]["obs"] == "presente da mãe" and l2["partes"][0]["motivo"] == ""            # a sua fica
    assert l2["sugestao"][0]["motivo"] == "como da última vez" and l2["sugestao"][0]["obs"] == ""


def test_salvar_partes_grava_a_obs_do_lancamento(con):
    lid = servicos.inserir(con, "nubank_conta", "2026-10-05", -30.0, "Compra", "Loja", "manual")
    servicos.definir_partes(con, lid, [{"valor": -30.0, "natureza": "gasto", "categoria": "outros", "obs": "", "motivo": ""}],
                            False, nota="  presente de aniversário ")
    assert next(x for x in servicos.lancamentos(con) if x["id"] == lid)["nota"] == "presente de aniversário"
