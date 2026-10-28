"""O Finanças dentro do celular: o mesmo código do servidor (a pasta app/ do repositório), rodando no aparelho.

O Kotlin chama estas funções pelo Chaquopy:
- iniciar(pasta, fuso): o banco local e a configuração deste aparelho;
- pedir(metodo, caminho, tipo, corpo_b64): uma chamada da tela (o site, empacotado no APK) à API, sem rede;
- notificacao(pacote, titulo, texto, quando_ms): o push do banco vira lançamento local na hora, pelo mesmo
  caminho do webhook (push.receber + push.processar), só que sem fila;
- sincronizar(url, chave): a troca com o servidor (app/sync.py).

O app/config.py lê o .env com pydantic-settings, que não roda no Android: no lugar dele entra um objeto com os
mesmos nomes. O FastAPI roda com pydantic 1 (puro Python; o 2 depende de código nativo sem build para Android).
"""

import asyncio
import base64
import json
import secrets
import sys
import threading
import traceback
import types
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote
from zoneinfo import ZoneInfo

_app = None
_loop: asyncio.AbstractEventLoop | None = None
_trava = threading.Lock()
settings = None


class Configuracao:
    """Os nomes do app/config.py, com os valores do aparelho."""

    def __init__(self, pasta: Path, fuso: str):
        self.API_KEY = secrets.token_hex(32)          # o webhook local não é usado: o push entra direto
        self.WEB_PASSWORD = secrets.token_hex(16)     # nem a senha: no celular a tela não pede login
        self.SESSION_SECRET = secrets.token_hex(32)
        self.DATABASE_PATH = str(pasta / "financas.db")
        self.HOST, self.PORT = "127.0.0.1", 0
        self.TIMEZONE = fuso
        self.AVISOS_FILA = str(pasta / "sem-avisos")  # não existe: o aviso de pendente é coisa do servidor
        self.AVISOS_REMETENTE = "financas"
        self.URL_PUBLICA = ""
        self.TITULAR = ""                             # vem do servidor na sincronização
        self.GEMINI_API_KEY, self.LLM_MODEL, self.LLM_TIMEOUT, self.LLM_MIN_CONFIDENCE = "", "", 8.0, 0.8
        self.PAPEIS_DIR = str(pasta / "papeis")
        self.DEDUP_WINDOW_MINUTES, self.QUEUE_MAXSIZE, self.MAX_ATTEMPTS = 10, 500, 3
        self.tz = ZoneInfo(fuso)
        self.llm_configured = False


def _titular() -> None:
    from app import db, sync
    with db.conectar_real() as con:
        settings.TITULAR = sync._cliente(con, "titular", "") or ""


def iniciar(pasta: str, fuso: str = "America/Sao_Paulo") -> None:
    global _app, _loop, settings
    with _trava:
        if _app is not None:
            return
        pasta_p = Path(pasta)
        pasta_p.mkdir(parents=True, exist_ok=True)
        try:
            ZoneInfo(fuso)
        except Exception:
            fuso = "America/Sao_Paulo"
        settings = Configuracao(pasta_p, fuso)
        modulo = types.ModuleType("app.config")
        modulo.settings, modulo.Settings = settings, Configuracao
        sys.modules["app.config"] = modulo
        import app
        app.config = modulo
        # A tela vem dos assets do APK; a pasta web/ que o main.py monta não existe aqui.
        import starlette.staticfiles as sf
        init = sf.StaticFiles.__init__
        sf.StaticFiles.__init__ = lambda self, *a, **kw: init(self, *a, **{**kw, "check_dir": False})
        import pydantic
        if not hasattr(pydantic.BaseModel, "model_dump"):
            pydantic.BaseModel.model_dump = lambda self, **kw: self.dict(**kw)
        from app import db, main
        db.iniciar()
        if db.demo_ativa():
            db.iniciar(db.caminho())
        main.app.dependency_overrides[main.sessao] = lambda: None
        _titular()
        _loop = asyncio.new_event_loop()
        threading.Thread(target=_loop.run_forever, name="financas-asgi", daemon=True).start()
        _app = main.app
    reprocessar()


# ---------------------------------------------------------------------------
# A tela chamando a API, sem rede
# ---------------------------------------------------------------------------
async def _asgi(metodo: str, caminho: str, tipo: str, corpo: bytes):
    path, _, query = caminho.partition("?")
    cab = [(b"host", b"appassets.androidplatform.net"), (b"content-length", str(len(corpo)).encode())]
    if tipo:
        cab.append((b"content-type", tipo.encode()))
    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": metodo.upper(), "scheme": "https",
             "path": unquote(path), "raw_path": path.encode(), "query_string": query.encode(), "headers": cab,
             "client": ("127.0.0.1", 0), "server": ("appassets.androidplatform.net", 443), "root_path": ""}
    entregue = False

    async def receive():
        nonlocal entregue
        if not entregue:
            entregue = True
            return {"type": "http.request", "body": corpo, "more_body": False}
        await asyncio.Event().wait()             # a resposta nunca é interrompida pelo cliente

    resposta = {"status": 500, "cabecalhos": {}, "partes": []}

    async def send(msg):
        if msg["type"] == "http.response.start":
            resposta["status"] = msg["status"]
            resposta["cabecalhos"] = {k.decode("latin-1"): v.decode("latin-1") for k, v in msg.get("headers", [])}
        elif msg["type"] == "http.response.body":
            resposta["partes"].append(msg.get("body", b""))

    try:
        await _app(scope, receive, send)
    except Exception:
        traceback.print_exc()
        if not resposta["partes"]:
            resposta.update(status=500, cabecalhos={"content-type": "application/json"},
                            partes=[json.dumps({"detail": "Erro interno no app."}).encode()])
    return resposta


def pedir(metodo: str, caminho: str, tipo: str = "", corpo_b64: str = "") -> str:
    corpo = base64.b64decode(corpo_b64) if corpo_b64 else b""
    r = asyncio.run_coroutine_threadsafe(_asgi(metodo, caminho, tipo, corpo), _loop).result()
    return json.dumps({"status": r["status"], "cabecalhos": r["cabecalhos"],
                       "corpo": base64.b64encode(b"".join(r["partes"])).decode()})


# ---------------------------------------------------------------------------
# Push do banco
# ---------------------------------------------------------------------------
def _processar(inbox_id: int) -> dict | None:
    from app import db, push
    try:
        return push.processar(inbox_id)
    except Exception as e:      # como no worker do servidor: o erro fica na inbox e tenta de novo depois
        traceback.print_exc()
        with db.conectar_real() as con:
            con.execute("UPDATE inbox SET attempts=attempts+1, last_error=?, "
                        "state=CASE WHEN attempts+1>=? THEN 'dead' ELSE 'pending' END WHERE id=?",
                        (str(e)[:500], settings.MAX_ATTEMPTS, inbox_id))
        return None


def notificacao(pacote: str, titulo: str, texto: str, quando_ms: int = 0) -> str:
    from app import push
    quando = datetime.fromtimestamp(quando_ms / 1000, settings.tz) if quando_ms else datetime.now(settings.tz)
    estado, inbox_id = push.receber(pacote, titulo, texto, quando)
    if inbox_id is None:
        return json.dumps({"estado": estado})
    lanc = _processar(inbox_id)
    return json.dumps({"estado": "aplicada", "inbox_id": inbox_id,
                       "lancamento": {k: lanc[k] for k in ("id", "descricao", "valor", "pendente")} if lanc else None},
                      ensure_ascii=False)


def reprocessar() -> int:
    """Push que ficou no meio (o app morreu enquanto aplicava): aplica agora, na ordem em que chegou."""
    from app import db
    with db.conectar_real() as con:
        ids = [r[0] for r in con.execute("SELECT id FROM inbox WHERE state='pending' ORDER BY id")]
    for i in ids:
        _processar(i)
    return len(ids)


# ---------------------------------------------------------------------------
# Servidor
# ---------------------------------------------------------------------------
_trava_sync = threading.Lock()


def sincronizar(url: str, chave: str) -> str:
    """Uma troca por vez (o WorkManager e o botão "Sincronizar agora" podem coincidir)."""
    from app import db, sync
    try:
        with _trava_sync:
            r = sync.sincronizar(db.conectar_real, url, chave)     # a demonstração nunca vai para o servidor
    except sync.ErroSync as e:
        return json.dumps({"ok": False, "erro": str(e)}, ensure_ascii=False)
    except Exception as e:
        traceback.print_exc()
        return json.dumps({"ok": False, "erro": f"Falha ao sincronizar: {e}"}, ensure_ascii=False)
    _titular()
    return json.dumps({"ok": True, **r}, ensure_ascii=False)
