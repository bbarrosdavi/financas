"""Poupança em metas, migração do banco antigo e eventos do plano."""

import sqlite3
from datetime import date

from app import db, servicos
from app.config import settings


def test_migracao_mantem_partes_e_aceita_poupanca(tmp_path, monkeypatch):
    caminho = tmp_path / "antigo.db"
    velho = sqlite3.connect(caminho)
    velho.executescript("""
        CREATE TABLE contas (id TEXT PRIMARY KEY, nome TEXT NOT NULL, tipo TEXT NOT NULL, saldo_inicial REAL NOT NULL DEFAULT 0,
            data_saldo_inicial TEXT NOT NULL DEFAULT '2026-01-01', limite REAL);
        INSERT INTO contas VALUES ('nubank_conta', 'Nubank conta', 'corrente', 0, '2026-01-01', NULL);
        CREATE TABLE lancamentos (id INTEGER PRIMARY KEY AUTOINCREMENT, data TEXT NOT NULL, conta TEXT NOT NULL, valor REAL NOT NULL,
            descricao TEXT NOT NULL, contraparte TEXT NOT NULL DEFAULT '', origem TEXT NOT NULL, ref TEXT NOT NULL DEFAULT '',
            chave TEXT UNIQUE, parcela TEXT, nota TEXT NOT NULL DEFAULT '', confirmado_por TEXT, criado_em TEXT);
        INSERT INTO lancamentos (data, conta, valor, descricao, origem) VALUES ('2026-10-01', 'nubank_conta', -10, 'x', 'manual');
        CREATE TABLE partes (id INTEGER PRIMARY KEY AUTOINCREMENT, lancamento_id INTEGER NOT NULL, valor REAL NOT NULL,
            natureza TEXT NOT NULL CHECK (natureza IN ('gasto','renda','transferencia','acerto')), categoria TEXT, pessoa TEXT,
            obs TEXT NOT NULL DEFAULT '');
        INSERT INTO partes (lancamento_id, valor, natureza, categoria) VALUES (1, -10, 'gasto', 'outros');
    """)
    velho.commit(); velho.close()
    monkeypatch.setattr(settings, "DATABASE_PATH", str(caminho))
    db.iniciar()
    with db.conectar() as con:
        assert con.execute("SELECT categoria FROM partes").fetchone()[0] == "outros"
        mid = con.execute("INSERT INTO metas (nome, alvo, aporte_mensal) VALUES ('Reserva', 2500, 300)").lastrowid
        lid = servicos.inserir(con, "nubank_conta", "2026-10-05", -300.0, "Aplicação RDB", "", "extrato_pdf")
        l = next(x for x in servicos.lancamentos(con) if x["id"] == lid)
        assert l["partes"][0]["natureza"] == "poupanca" and l["partes"][0]["meta"] == mid   # única meta ativa


def test_metas_somam_aportes_e_resgates(con):
    mid = con.execute("INSERT INTO metas (nome, alvo, aporte_mensal) VALUES ('Notebook novo', 4000, 500)").lastrowid
    servicos.inserir(con, "nubank_conta", "2026-10-05", -500.0, "Dinheiro guardado", "", "manual",
                     partes=[{"valor": -500.0, "natureza": "poupanca", "meta": mid}])
    servicos.inserir(con, "nubank_conta", "2026-11-05", -500.0, "Dinheiro guardado", "", "manual",
                     partes=[{"valor": -500.0, "natureza": "poupanca", "meta": mid}])
    servicos.inserir(con, "nubank_conta", "2026-11-20", 200.0, "Dinheiro resgatado", "", "manual",
                     partes=[{"valor": 200.0, "natureza": "poupanca", "meta": mid}])
    m = servicos.metas(con, "2026-11-01", "2026-11-30", 1.0, date(2026, 11, 25))[0]
    assert m["guardado_total"] == 800.0 and m["guardado_periodo"] == 300.0
    assert m["planejado_periodo"] == 500.0 and m["falta_periodo"] == 200.0 and m["completude_alvo"] == 0.2


def test_eventos_mudam_a_projecao(con):
    db.definir_parametro(con, "salario_mensal", "3000")
    db.definir_parametro(con, "horizonte", "2027-08")
    con.execute("DELETE FROM eventos")
    con.execute("INSERT INTO eventos (nome, tipo, inicio, valor) VALUES ('Fim do contrato', 'renda_mensal', '2027-07', -3000)")
    con.execute("INSERT INTO eventos (nome, tipo, inicio, valor) VALUES ('Viagem', 'saida_unica', '2027-01', 800)")
    pl = servicos.plano(con, date(2026, 10, 26))
    por = {l["mes"]: l for l in pl["linhas"]}
    assert por["2027-06"]["renda"] == 3000 and por["2027-07"]["renda"] == 0
    assert por["2027-01"]["unicos"] == -800
    assert pl["linhas"][-1]["mes"] == "2027-08"


def test_apagar_categoria_em_uso_move_os_lancamentos(con):
    from fastapi.testclient import TestClient
    from app.main import app
    servicos.inserir(con, "nubank_conta", "2026-10-01", -10.0, "x", "", "manual",
                     partes=[{"valor": -10.0, "natureza": "gasto", "categoria": "viagem"}])
    con.commit()
    with TestClient(app) as c:
        c.post("/api/login", json={"senha": settings.WEB_PASSWORD})
        assert c.delete("/api/categorias/viagem").status_code == 400
        assert c.delete("/api/categorias/viagem?mover_para=salario").status_code == 400   # tipo diferente
        r = c.delete("/api/categorias/viagem?mover_para=lazer")
        assert r.status_code == 200 and r.json()["movidos"] == 1
    with db.conectar() as c2:
        assert c2.execute("SELECT categoria FROM partes WHERE valor=-10").fetchone()[0] == "lazer"
