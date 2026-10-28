"""Finanças no Windows: o servidor roda nesta máquina e o site abre no navegador.

    Financas.exe                  garante o servidor de pé e abre http://localhost:8095 (atalhos)
    Financas.exe --servidor       só o servidor, sem janela (inicialização do Windows); log em logs\\servidor.log
    Financas.exe --configurar A   grava no .env o que o instalador perguntou (arquivo A: senha, host, titular)

Os dados ficam em %LOCALAPPDATA%\\Financas (banco, papéis de parede, .env e logs). O poppler e o tesseract com
português vêm junto, nas pastas poppler\\ e tesseract\\ ao lado do executável.
"""

import os
import secrets
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

CONGELADO = getattr(sys, "frozen", False)
PASTA_APP = Path(sys.executable).resolve().parent if CONGELADO else Path(__file__).resolve().parent
DADOS = Path(os.environ.get("FINANCAS_DADOS") or Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Financas")
ENV = DADOS / ".env"
LOG = DADOS / "logs" / "servidor.log"
if not CONGELADO:
    sys.path.insert(0, str(PASTA_APP.parent))      # rodando do repositório: o pacote app fica na raiz


# ---------------------------------------------------------------------------
# .env
# ---------------------------------------------------------------------------
def ler_env() -> dict[str, str]:
    if not ENV.exists():
        return {}
    out = {}
    for linha in ENV.read_text(encoding="utf-8-sig").splitlines():
        linha = linha.strip()
        if linha and not linha.startswith("#") and "=" in linha:
            k, v = linha.split("=", 1)
            out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def gravar_env(env: dict[str, str]) -> None:
    DADOS.mkdir(parents=True, exist_ok=True)
    tmp = ENV.with_suffix(".tmp")
    tmp.write_text("".join(f"{k}={v}\n" for k, v in env.items()), encoding="utf-8")
    tmp.replace(ENV)


def preparar_env() -> tuple[dict[str, str], str | None]:
    """Completa o .env: chave do celular e segredo da sessão aleatórios. Devolve a senha se teve de inventar uma."""
    env = ler_env()
    nova_senha = None
    mudou = ENV.exists() and ENV.read_bytes().startswith(b"\xef\xbb\xbf")     # sem BOM, para o pydantic ler
    for k in ("API_KEY", "SESSION_SECRET"):
        if len(env.get(k, "")) < 32:
            env[k], mudou = secrets.token_hex(32), True
    if len(env.get("WEB_PASSWORD", "")) < 8:
        env["WEB_PASSWORD"] = nova_senha = secrets.token_urlsafe(9)
        mudou = True
    env.setdefault("HOST", "127.0.0.1")
    if mudou or not ENV.exists():
        gravar_env(env)
    return env, nova_senha


def configurar(arquivo: str) -> None:
    """Chamado pelo instalador com um arquivo temporário (chave=valor): senha, host e titular."""
    pedido = {}
    for linha in Path(arquivo).read_text(encoding="utf-8-sig").splitlines():
        if "=" in linha:
            k, v = linha.split("=", 1)
            pedido[k.strip()] = v.strip()
    env = ler_env()
    if pedido.get("senha"):
        env["WEB_PASSWORD"] = pedido["senha"]
    if pedido.get("host"):
        env["HOST"] = pedido["host"]
    if "titular" in pedido:
        env["TITULAR"] = pedido["titular"].upper()
    gravar_env(env)
    preparar_env()


# ---------------------------------------------------------------------------
# Ambiente do servidor
# ---------------------------------------------------------------------------
def ip_da_rede() -> str:
    """O IP desta máquina na rede de casa (o que o celular usa). Não manda nada: só escolhe a rota."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
    except OSError:
        return "localhost"


def preparar_ambiente(env: dict[str, str]) -> None:
    os.environ.update(env)
    os.environ.setdefault("DATABASE_PATH", str(DADOS / "financas.db"))
    os.environ.setdefault("PAPEIS_DIR", str(DADOS / "papeis"))
    os.environ.setdefault("AVISOS_FILA", str(DADOS / "avisos-so-no-linux"))   # não existe: avisos desligados
    porta = os.environ.setdefault("PORT", "8095")
    if "URL_PUBLICA" not in env:
        os.environ["URL_PUBLICA"] = f"http://{ip_da_rede() if env.get('HOST') == '0.0.0.0' else 'localhost'}:{porta}"
    # poppler (pdftotext, pdftoppm) e tesseract embutidos vêm antes de qualquer outro no PATH
    os.environ["PATH"] = os.pathsep.join([str(PASTA_APP / "poppler"), str(PASTA_APP / "tesseract"), os.environ.get("PATH", "")])
    os.environ["TESSDATA_PREFIX"] = str(PASTA_APP / "tesseract" / "tessdata")
    os.chdir(DADOS)
    if os.name == "nt":
        # Programa de console chamado por um executável sem janela abre uma janela preta por um instante: não abre.
        original = subprocess.Popen

        class SemJanela(original):
            def __init__(self, *a, **kw):
                kw["creationflags"] = kw.get("creationflags", 0) | subprocess.CREATE_NO_WINDOW
                super().__init__(*a, **kw)
        subprocess.Popen = SemJanela


def porta() -> int:
    return int(os.environ.get("PORT") or ler_env().get("PORT") or 8095)


def no_ar() -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{porta()}/health", timeout=1.5) as r:
            return r.status == 200
    except OSError:
        return False


def aviso(texto: str, titulo: str = "Finanças") -> None:
    if os.name == "nt":
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, texto, titulo, 0x40)
    else:
        print(texto)


# ---------------------------------------------------------------------------
# Modos
# ---------------------------------------------------------------------------
def servidor() -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    if LOG.exists() and LOG.stat().st_size > 5 * 1024 * 1024:
        LOG.replace(LOG.with_suffix(".log.1"))
    sys.stdout = sys.stderr = open(LOG, "a", buffering=1, encoding="utf-8")
    env, nova = preparar_env()
    if nova:
        print(f"Senha do site criada agora (está no {ENV}): {nova}")
    preparar_ambiente(env)
    if no_ar():
        print("Servidor já estava no ar.")
        return
    import uvicorn
    from app.main import app
    print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} Finanças em {os.environ['HOST']}:{porta()}, dados em {DADOS}")
    uvicorn.run(app, host=os.environ["HOST"], port=porta(), log_level="info", access_log=False)


def abrir() -> None:
    env, nova = preparar_env()
    if not no_ar():
        cmd = [sys.executable, "--servidor"] if CONGELADO else [sys.executable, __file__, "--servidor"]
        flags = (subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW) if os.name == "nt" else 0
        subprocess.Popen(cmd, creationflags=flags, close_fds=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
        for _ in range(60):
            time.sleep(0.5)
            if no_ar():
                break
        else:
            aviso(f"O servidor do Finanças não subiu. O motivo fica no log:\n{LOG}")
            return
    if nova:
        aviso(f"A senha do site é:\n\n{nova}\n\nEla fica guardada em {ENV} (WEB_PASSWORD).")
    webbrowser.open(f"http://localhost:{porta()}")


def main() -> None:
    args = sys.argv[1:]
    if args[:1] == ["--servidor"]:
        servidor()
    elif args[:1] == ["--configurar"] and len(args) > 1:
        configurar(args[1])
    else:
        abrir()


if __name__ == "__main__":
    main()
