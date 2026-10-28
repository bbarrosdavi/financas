"""Sincronização celular <-> servidor: dois bancos trocando pelo endpoint de verdade (sem rede)."""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app import db, servicos, sync
from app.config import settings
from app.main import app


@pytest.fixture
def par(con, tmp_path, monkeypatch):
    """Servidor = o banco do fixture `con`; celular = um banco novo, sem o vocabulário de teste."""
    cel = tmp_path / "celular.db"
    db.iniciar(cel)
    with db.conectar() as s:       # a pessoa inventada dos testes, mesmo onde o vocabulário de teste é outro
        s.execute("INSERT OR IGNORE INTO pessoas (id, nome, tipo, apelido_extrato) VALUES ('ana', 'Ana', 'colega', 'ANA EXEMPLO DA SILVA')")
    cliente = TestClient(app)
    respostas = {}

    def post(url, chave, corpo, timeout):
        caminho = "/" + url.split("://", 1)[1].split("/", 1)[1]
        if caminho in respostas:
            return respostas[caminho], {}
        r = cliente.post(caminho, json=corpo, headers={"Authorization": f"Bearer {chave}"})
        return r.status_code, (r.json() if r.content else {})

    monkeypatch.setattr(sync, "_post", post)
    return SimpleNamespace(
        cel=lambda: db.conectar(cel), srv=db.conectar, respostas=respostas,
        trocar=lambda chave=settings.API_KEY: sync.sincronizar(lambda: db.conectar(cel), "http://pc:8095", chave))


def _um(conectar, sql, args=()):
    with conectar() as c:
        return c.execute(sql, args).fetchone()


def _partes(conectar, descricao):
    with conectar() as c:
        lid = c.execute("SELECT id FROM lancamentos WHERE descricao = ?", (descricao,)).fetchone()[0]
        return [dict(p) for p in c.execute("SELECT valor, natureza, categoria, pessoa, meta FROM partes WHERE lancamento_id = ?", (lid,))]


def test_primeira_troca_traz_o_servidor_sem_trocar_dado_pelo_padrao(par):
    with par.srv() as s:
        servicos.inserir(s, "nubank_conta", "2026-10-05", -40.0, "Compra no débito", "PADARIA EXEMPLO", "extrato_pdf")
    r = par.trocar()
    assert r["modo"] == "sync" and r["enviadas"] == 0
    # O teto que o servidor tem (500) chega; o padrão de fábrica do celular (sem teto) não vai para o servidor.
    assert _um(par.cel, "SELECT teto FROM categorias WHERE id = 'mercado'")[0] == 500
    assert _um(par.srv, "SELECT teto FROM categorias WHERE id = 'mercado'")[0] == 500
    assert _um(par.cel, "SELECT nome FROM pessoas WHERE id = 'ana'")[0] == "Ana"
    assert _partes(par.cel, "Compra no débito")[0]["categoria"] == "delivery"
    assert par.trocar()["enviadas"] == 0     # nada mudou: nada vai


def test_lancamento_do_celular_e_a_classificacao_chegam_ao_servidor_e_voltam(par):
    par.trocar()
    with par.cel() as c:
        lid = servicos.inserir(c, "nubank_cartao", "2026-10-06", -18.0, "Lugar Novo Exemplo", origem="push", ref="inbox:1")
        assert not c.execute("SELECT 1 FROM partes WHERE lancamento_id = ?", (lid,)).fetchone()     # pendente
        servicos.definir_partes(c, lid, [{"valor": -18.0, "natureza": "gasto", "categoria": "lazer"}], False)
    assert par.trocar()["enviadas"] == 1
    assert _partes(par.srv, "Lugar Novo Exemplo") == [{"valor": -18.0, "natureza": "gasto", "categoria": "lazer", "pessoa": None, "meta": None}]
    # No PC, muda para dividido com a Ana; o celular recebe.
    with par.srv() as s:
        lid_s = s.execute("SELECT id FROM lancamentos WHERE descricao = 'Lugar Novo Exemplo'").fetchone()[0]
        servicos.definir_partes(s, lid_s, [{"valor": -9.0, "natureza": "gasto", "categoria": "lazer"},
                                           {"valor": -9.0, "natureza": "acerto", "pessoa": "ana"}], False)
    par.trocar()
    assert [p["natureza"] for p in _partes(par.cel, "Lugar Novo Exemplo")] == ["gasto", "acerto"]


def test_conflito_fica_com_a_alteracao_mais_recente(par):
    with par.srv() as s:
        servicos.inserir(s, "nubank_conta", "2026-10-07", -60.0, "Loja Exemplo", origem="manual")
    par.trocar()
    lid_c = _um(par.cel, "SELECT id FROM lancamentos WHERE descricao = 'Loja Exemplo'")[0]
    lid_s = _um(par.srv, "SELECT id FROM lancamentos WHERE descricao = 'Loja Exemplo'")[0]
    with par.srv() as s:          # o PC classifica primeiro...
        servicos.definir_partes(s, lid_s, [{"valor": -60.0, "natureza": "gasto", "categoria": "vestuario"}], False)
    with par.cel() as c:          # ...e o celular depois: vence o celular
        servicos.definir_partes(c, lid_c, [{"valor": -60.0, "natureza": "gasto", "categoria": "eletronicos"}], False)
    par.trocar()
    assert _partes(par.srv, "Loja Exemplo")[0]["categoria"] == "eletronicos"
    assert _partes(par.cel, "Loja Exemplo")[0]["categoria"] == "eletronicos"


def test_apagar_no_celular_apaga_no_servidor(par):
    par.trocar()
    with par.cel() as c:
        lid = servicos.inserir(c, "nubank_conta", "2026-10-08", -5.0, "Café Exemplo", origem="manual")
    par.trocar()
    assert _um(par.srv, "SELECT COUNT(*) FROM lancamentos WHERE descricao = 'Café Exemplo'")[0] == 1
    with par.cel() as c:
        c.execute("DELETE FROM lancamentos WHERE id = ?", (lid,))
    par.trocar()
    assert _um(par.srv, "SELECT COUNT(*) FROM lancamentos WHERE descricao = 'Café Exemplo'")[0] == 0


def test_mesma_linha_de_extrato_importada_nos_dois_lados_fica_uma(par):
    par.trocar()
    for conectar in (par.srv, par.cel):
        with conectar() as c:
            servicos.inserir(c, "nubank_conta", "2026-10-09", -33.0, "Compra no débito", "MERCADINHO EXEMPLO", "extrato_csv",
                             chave="mesma-linha-do-extrato")
    par.trocar()
    par.trocar()
    for conectar in (par.srv, par.cel):
        assert _um(conectar, "SELECT COUNT(*) FROM lancamentos WHERE chave = 'mesma-linha-do-extrato'")[0] == 1
    assert par.trocar()["enviadas"] == 0


def test_push_que_chega_depois_do_extrato_casa_com_ele(par):
    par.trocar()
    with par.srv() as s:          # o extrato foi importado no PC antes de o celular sincronizar
        servicos.inserir(s, "nubank_conta", "2026-10-10", -27.0, "Compra no débito", "LOJA SEM REGRA EXEMPLO", "extrato_pdf",
                         ref="extrato.pdf")
    with par.cel() as c:          # e o celular viu a compra pelo push, e classificou
        lid = servicos.inserir(c, "nubank_conta", "2026-10-09", -27.0, "Loja Sem Regra Exemplo", origem="push", ref="inbox:3")
        servicos.definir_partes(c, lid, [{"valor": -27.0, "natureza": "gasto", "categoria": "hobbies"}], False)
    par.trocar()
    par.trocar()
    for conectar in (par.srv, par.cel):
        rows = _um(conectar, "SELECT COUNT(*), MAX(origem), MAX(confirmado_por), MAX(data) FROM lancamentos WHERE ABS(valor + 27) < 0.005")
        assert tuple(rows) == (1, "push", "extrato_pdf:extrato.pdf", "2026-10-10")
    assert _partes(par.srv, "Loja Sem Regra Exemplo")[0]["categoria"] == "hobbies"


def test_meta_e_orcamento_viajam_pelo_uid(par):
    with par.srv() as s:          # o servidor já tem uma meta: os ids locais não coincidem
        s.execute("INSERT INTO metas (nome, aporte_mensal) VALUES ('Meta do PC', 50)")
    with par.cel() as c:
        mid = c.execute("INSERT INTO metas (nome, aporte_mensal) VALUES ('Reserva', 100)").lastrowid
        servicos.definir_orcamento(c, f"meta:{mid}", "2026-11", 150.0)
        lid = servicos.inserir(c, "nubank_conta", "2026-10-11", -100.0, "Dinheiro guardado", origem="manual",
                               partes=[{"valor": -100.0, "natureza": "poupanca", "meta": mid}])
    par.trocar()
    mid_s = _um(par.srv, "SELECT id FROM metas WHERE nome = 'Reserva'")[0]
    assert mid_s != mid
    assert _partes(par.srv, "Dinheiro guardado")[0]["meta"] == mid_s
    assert _um(par.srv, "SELECT valor FROM orcamento WHERE chave = ? AND mes = '2026-11'", (f"meta:{mid_s}",))[0] == 150.0
    assert lid


def test_parametro_local_nao_viaja_e_titular_vem_do_servidor(par, monkeypatch):
    monkeypatch.setattr(settings, "TITULAR", "FULANO DE TAL")
    with par.srv() as s:
        db.definir_parametro(s, "papel_de_parede", "do-pc.jpg")
        db.definir_parametro(s, "salario_mensal", "4200")
    par.trocar()
    assert _um(par.cel, "SELECT valor FROM parametros WHERE chave = 'salario_mensal'")[0] == "4200"
    assert _um(par.cel, "SELECT valor FROM parametros WHERE chave = 'papel_de_parede'") is None
    assert _um(par.cel, "SELECT valor FROM sync_cliente WHERE chave = 'titular'")[0] == "FULANO DE TAL"


def test_chave_errada_e_recusada(par):
    with pytest.raises(sync.ErroSync, match="Chave recusada"):
        par.trocar("chave-errada-mas-comprida-o-suficiente-000000")


def test_servidor_antigo_recebe_os_pushes_pelo_webhook(par):
    par.respostas["/api/v1/sync"] = 404
    with par.cel() as c:
        c.execute("INSERT INTO inbox (dedup_hash, package, title, body, recebido_em) VALUES "
                  "('h1', 'com.nu.production', 'Compra aprovada', 'Compra de R$ 12,50 aprovada em Mercadinho Exemplo', '2026-10-12 10:00:00')")
    r = par.trocar()
    assert r == {"modo": "webhook", "enviadas": 1, "recebidas": 0, "aceitas": 1, "recusadas": 0}
    assert _um(par.srv, "SELECT title FROM inbox")[0] == "Compra aprovada"
    assert par.trocar()["enviadas"] == 0


def test_servidor_sabe_quais_lancamentos_o_celular_mudou(par):
    par.trocar()
    with par.cel() as c:
        servicos.inserir(c, "nubank_conta", "2026-10-13", -12.0, "Banca Exemplo", origem="manual")
        envio = sync.mudancas(c)
    with par.srv() as s:
        r = sync.servir(s, 0, envio)
        lid = s.execute("SELECT id FROM lancamentos WHERE descricao = 'Banca Exemplo'").fetchone()[0]
    assert lid in r["lancamentos"]
