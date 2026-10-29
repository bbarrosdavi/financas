"""Dados de demonstração: num banco à parte, só num Finanças vazio, e o push nunca cai neles."""

from datetime import date, datetime

import pytest
from fastapi.testclient import TestClient

from app import db, demo, push
from app.config import settings
from app.main import app


def _conta(conectar, sql="SELECT COUNT(*) FROM lancamentos"):
    with conectar() as c:
        return c.execute(sql).fetchone()[0]


def test_liga_num_banco_a_parte_e_desliga_sem_deixar_nada(con):
    con.execute("DELETE FROM lancamentos")
    con.commit()
    demo.ligar(date(2026, 10, 20))
    assert db.demo_ativa() and db.caminho() == db.banco_demonstracao()
    assert _conta(db.conectar) > 100                       # a tela vê seis meses inventados
    assert _conta(db.conectar_real) == 0                   # o banco de verdade continua vazio
    demo.desligar()
    assert not db.demo_ativa() and db.caminho() == db.caminho_real()
    assert not db.banco_demonstracao().exists()


def test_push_com_a_demonstracao_ligada_vai_para_o_banco_de_verdade(con):
    con.execute("DELETE FROM lancamentos")
    con.commit()
    demo.ligar(date(2026, 10, 20))
    estado, inbox_id = push.receber("com.nu.production", "Compra aprovada", "Compra de R$ 12,50 aprovada em Mercadinho Exemplo",
                                    datetime(2026, 10, 20, 10, 0, tzinfo=settings.tz))
    push.processar(inbox_id)
    assert _conta(db.conectar_real) == 1
    assert _conta(db.conectar, "SELECT COUNT(*) FROM lancamentos WHERE descricao = 'Mercadinho Exemplo'") == 0
    demo.desligar()
    assert _conta(db.conectar, "SELECT COUNT(*) FROM lancamentos WHERE descricao = 'Mercadinho Exemplo'") == 1


def test_nao_liga_com_dados_de_verdade(con):
    from app import servicos
    servicos.inserir(con, "nubank_conta", "2026-10-05", -10.0, "Compra de verdade", origem="manual")
    con.commit()
    with pytest.raises(ValueError, match="já há dados de verdade"):
        demo.ligar()
    with TestClient(app) as c:
        c.post("/api/login", json={"senha": settings.WEB_PASSWORD})
        assert c.get("/api/demo").json() == {"ativo": False, "vazio": False}
        assert c.put("/api/demo", json={"ativo": True}).status_code == 409
    assert not db.demo_ativa()
