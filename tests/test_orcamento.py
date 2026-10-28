"""Orçamento por mês (Budget Planning) e despesas fixas por item."""

from datetime import date

from fastapi.testclient import TestClient

from app import servicos
from app.config import settings
from app.main import app


def test_padrao_e_valor_do_mes(con):
    o = servicos.orcado(con, ["2026-11", "2026-12"])
    assert o["ru"]["2026-11"] == 84.0 and o["salario"]["2026-11"] == 3000.0
    servicos.definir_orcamento(con, "ru", "2026-12", 42.0)
    o = servicos.orcado(con, ["2026-11", "2026-12"])
    assert o["ru"] == {"2026-11": 84.0, "2026-12": 42.0}
    servicos.definir_orcamento(con, "ru", "2026-12", None)       # limpar volta ao padrão
    assert servicos.orcado(con, ["2026-12"])["ru"]["2026-12"] == 84.0


def test_categoria_orcada_pela_soma_dos_itens(con):
    con.execute("INSERT INTO itens_fixos (categoria, nome, valor) VALUES ('aluguel-condominio', 'Aluguel', 700.0)")
    con.execute("INSERT INTO itens_fixos (categoria, nome, valor, inicio) VALUES ('aluguel-condominio', 'Condomínio', 250, '2026-12')")
    teto = con.execute("SELECT teto FROM categorias WHERE id='aluguel-condominio'").fetchone()[0]
    assert servicos.orcado(con, ["2026-11"])["aluguel-condominio"]["2026-11"] == teto     # sem a opção, vale o teto
    con.execute("UPDATE categorias SET orcar_por_itens=1 WHERE id='aluguel-condominio'")
    o = servicos.orcado(con, ["2026-11", "2026-12"])["aluguel-condominio"]
    assert o == {"2026-11": 700.0, "2026-12": 950.0}
    servicos.definir_orcamento(con, "aluguel-condominio", "2026-12", 900.0)                # o valor do mês ainda manda
    assert servicos.orcado(con, ["2026-12"])["aluguel-condominio"]["2026-12"] == 900.0


def test_periodos_somam_o_orcamento_dos_meses(con):
    servicos.definir_orcamento(con, "ru", "2026-02", 0.0)
    ano = {c["id"]: c for c in servicos.gastos_por_categoria(con, "2026-01-01", "2026-03-31", ["2026-01", "2026-02", "2026-03"])}
    assert ano["ru"]["teto"] == 168.0
    semana = {c["id"]: c for c in servicos.gastos_por_categoria(con, "2026-01-05", "2026-01-11", ["2026-01"], 0.25)}
    assert semana["ru"]["teto"] == 21.0


def test_projecao_usa_o_orcamento(con):
    hoje = date(2026, 10, 26)
    antes = servicos.plano(con, hoje)["linhas"][0]
    servicos.definir_orcamento(con, "ru", "2026-11", 184.0)
    depois = servicos.plano(con, hoje)["linhas"][0]
    assert depois["mes"] == "2026-11" and round(depois["custo"] - antes["custo"], 2) == 100.0


def test_grade_separa_parcelas_antigas(con):
    servicos.inserir(con, "nubank_cartao", "2026-10-03", -30.0, "Lanchonete Exemplo", "", "manual",
                     partes=[{"valor": -30.0, "natureza": "gasto", "categoria": "ru"}])
    lid = servicos.inserir(con, "nubank_cartao", "2026-10-04", -50.0, "Loja - Parcela 3/10", "", "manual",
                           partes=[{"valor": -50.0, "natureza": "gasto", "categoria": "ru"}])
    con.execute("UPDATE lancamentos SET parcela='3/10' WHERE id=?", (lid,))
    g = servicos.grade_orcamento(con, 2026)
    ru = next(l for l in g["linhas"] if l["chave"] == "ru")
    assert ru["realizado"]["2026-10"] == 30.0 and g["parcelas"]["2026-10"] == 50.0
    assert ru["orcado"]["2026-10"] == 84.0 and ru["definido"] == []


def test_api_orcamento_e_itens(con):
    with TestClient(app) as c:
        c.post("/api/login", json={"senha": settings.WEB_PASSWORD})
        assert c.put("/api/orcamento", json={"chave": "nao-existe", "mes": "2026-11", "valor": 1}).status_code == 404
        assert c.put("/api/orcamento", json={"chave": "ru", "mes": "2026-10", "valor": 70, "ate_dezembro": True}).status_code == 200
        ru = next(l for l in c.get("/api/orcamento?ano=2026").json()["linhas"] if l["chave"] == "ru")
        assert ru["definido"] == ["2026-10", "2026-11", "2026-12"] and ru["orcado"]["2026-09"] == 84.0
        assert c.post("/api/itens-fixos", json={"categoria": "salario", "nome": "x", "valor": 1}).status_code == 400
        iid = c.post("/api/itens-fixos", json={"categoria": "ru", "nome": "Almoço e janta", "valor": 84}).json()["id"]
        assert c.put(f"/api/itens-fixos/{iid}", json={"categoria": "ru", "nome": "Almoço e janta", "valor": 63}).status_code == 200
        assert c.put("/api/categorias/ru", json={"orcar_por_itens": True}).status_code == 200
        ru = next(l for l in c.get("/api/orcamento?ano=2026").json()["linhas"] if l["chave"] == "ru")
        assert ru["por_itens"] and ru["orcado"]["2026-09"] == 63.0 and ru["orcado"]["2026-10"] == 70.0
        # apagar a categoria leva os itens junto para a que recebe os lançamentos (ou os apaga se não houver)
        assert c.delete("/api/categorias/ru").status_code == 200
        assert con.execute("SELECT COUNT(*) FROM itens_fixos").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM orcamento WHERE chave='ru'").fetchone()[0] == 0


def test_dados_do_modelo_antigo(con):
    from app import exportar
    servicos.inserir(con, "nubank_cartao", "2026-10-03", -30.0, "Lanchonete Exemplo", "", "manual",
                     partes=[{"valor": -30.0, "natureza": "gasto", "categoria": "ru"}])
    servicos.inserir(con, "nubank_conta", "2026-10-04", -12.0, "Transferência enviada", "Fulano", "manual")
    con.execute("INSERT INTO itens_fixos (categoria, nome, valor, inicio) VALUES ('ru', 'Almoço e janta', 84, '2026-03')")
    d = exportar.dados_modelo(con, date(2026, 10, 26))
    assert d["ano_inicial"] == 2026 and d["mes"] == 10
    assert [t["tipo"] for t in d["tracking"]] == ["Expenses", "Expenses"]                # mais recente primeiro
    pend, ru = d["tracking"]
    assert pend["pendente"] and pend["valor"] == 12.0 and pend["categoria"] == ""
    assert ru["categoria"] == "Alimentação" and ru["valor"] == 30.0 and ru["detalhes"].startswith("RU (dias de aula)")
    alim = next(g for g in d["gastos"] if g["nome"] == "Alimentação")
    assert alim["meses"]["2026-10"] > 84                                                   # soma do grupo
    fixa = next(g for g in d["fixas"]["grupos"] if g["nome"] == "Alimentação")["itens"][0]
    assert "2026-02" not in fixa["valores"] and fixa["valores"]["2026-03"] == 84
    assert len(d["gastos"]) <= exportar.CAPACIDADE["gasto"]


def test_grafico_traz_orcado_e_poupanca(con):
    mid = con.execute("INSERT INTO metas (nome, alvo, aporte_mensal) VALUES ('Reserva', 2500, 300)").lastrowid
    servicos.inserir(con, "nubank_conta", "2026-10-05", -200.0, "Dinheiro guardado", "", "manual",
                     partes=[{"valor": -200.0, "natureza": "poupanca", "meta": mid}])
    P = servicos.painel(con, date(2026, 10, 26), "2026")
    assert [s["mes"] for s in P["serie"]] == [f"2026-{m:02d}" for m in range(1, 13)]      # o ano inteiro
    out, dez = P["serie"][9], P["serie"][11]
    assert out["poupanca"] == 200.0 and out["orc_poupanca"] == 300.0 and out["orc_renda"] == 3000.0
    assert dez["renda"] == 0 and dez["orc_gasto"] > 0                                     # futuro: só o orçado
    sem = servicos.painel(con, date(2026, 10, 26), "2026-W41")["serie"][-1]
    assert sem["orc_renda"] == 750.0
