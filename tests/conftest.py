"""O Settings lê o ambiente no import: as variáveis entram antes de qualquer `app.*`."""

import os
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="financas-teste-"))
os.environ.update({
    "API_KEY": "chave-de-teste-com-tamanho-suficiente-000000",
    "WEB_PASSWORD": "senha-de-teste",
    "SESSION_SECRET": "segredo-de-sessao-de-teste-000000000000",
    "DATABASE_PATH": str(_TMP / "base.db"),
    "AVISOS_FILA": "/nao/existe",
})

import pytest  # noqa: E402

from app import db  # noqa: E402
from app.config import settings  # noqa: E402


def _vocabulario_de_teste(c) -> None:
    """Pessoas, tetos e regras inventados: o banco novo não traz nenhum."""
    c.executemany("INSERT INTO pessoas (id, nome, tipo, apelido_extrato, sugere_entrada, sugere_saida) VALUES (?,?,?,?,?,?)",
                  [("ana", "Ana", "colega", "ANA EXEMPLO DA SILVA", "acerto", "acerto"),
                   ("bruno", "Bruno", "colega", "BRUNO EXEMPLO", "acerto", "acerto"),
                   ("mae", "Mãe", "familia", "MARIA EXEMPLO", "renda:pais", "acerto")])
    c.execute("UPDATE categorias SET teto=84 WHERE id='conveniencia'")
    c.execute("UPDATE categorias SET teto=500 WHERE id='mercado'")
    c.execute("UPDATE categorias SET teto=900 WHERE id='aluguel-condominio'")
    c.execute("INSERT INTO regras (padrao, natureza, categoria, pessoa, origem) VALUES ('EMPRESA EXEMPLO', 'renda', 'salario', NULL, 'sistema')")
    db.definir_parametro(c, "salario_mensal", "3000")


@pytest.fixture
def con(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "DATABASE_PATH", str(tmp_path / "t.db"))
    db.iniciar()
    with db.conectar() as c:
        _vocabulario_de_teste(c)
        c.commit()
        yield c
