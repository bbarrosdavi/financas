"""Confere o Finanças instalado no Windows (roda no CI, depois do instalador silencioso, com o servidor no ar).

    python windows/teste_windows.py --senha SENHA --env %LOCALAPPDATA%\\Financas\\.env

Sem dado real: a fatura do Bradesco é a mesma imagem inventada dos testes (tests/test_bradesco.py).
"""

import argparse
import http.cookiejar
import json
import os
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
BASE = "http://127.0.0.1:8095"


def pedir(abridor, metodo, caminho, corpo=None, tipo="application/json", cabecalhos=None):
    dados = json.dumps(corpo).encode() if tipo == "application/json" and corpo is not None else corpo
    req = urllib.request.Request(BASE + caminho, data=dados, method=metodo, headers={**({"Content-Type": tipo} if dados else {}), **(cabecalhos or {})})
    try:
        with abridor.open(req, timeout=180) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def multipart(nome_arquivo: str, conteudo: bytes) -> tuple[bytes, str]:
    fronteira = uuid.uuid4().hex
    corpo = (f"--{fronteira}\r\nContent-Disposition: form-data; name=\"arquivos\"; filename=\"{nome_arquivo}\"\r\n"
             f"Content-Type: application/pdf\r\n\r\n").encode() + conteudo + f"\r\n--{fronteira}--\r\n".encode()
    return corpo, f"multipart/form-data; boundary={fronteira}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--senha", required=True)
    ap.add_argument("--env", required=True)
    a = ap.parse_args()
    env = dict(l.split("=", 1) for l in Path(a.env).read_text(encoding="utf-8-sig").splitlines() if "=" in l)
    assert env["WEB_PASSWORD"] == a.senha, "o .env não tem a senha escolhida no instalador"
    assert len(env["API_KEY"]) >= 32 and len(env["SESSION_SECRET"]) >= 32, "faltou gerar a chave ou o segredo"
    print("HOST =", env.get("HOST"), "| TITULAR =", env.get("TITULAR"))

    abridor = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    for _ in range(60):
        try:
            if pedir(abridor, "GET", "/health")[0] == 200:
                break
        except OSError:
            pass
        time.sleep(1)
    else:
        sys.exit("o servidor não respondeu em /health")
    print("health ok")

    assert pedir(abridor, "GET", "/api/painel")[0] == 401
    assert pedir(abridor, "POST", "/api/login", {"senha": a.senha})[0] == 200
    s, painel = pedir(abridor, "GET", "/api/painel")
    assert s == 200 and "totais" in json.loads(painel)
    print("login e painel ok")

    # Fatura do Bradesco em PDF só de imagem: pdftotext (vazio), pdftoppm e tesseract com português, todos embutidos.
    os.environ.update({"API_KEY": "x" * 40, "WEB_PASSWORD": "teste-123", "SESSION_SECRET": "y" * 40,
                       "DATABASE_PATH": str(Path(tempfile.mkdtemp()) / "nao-usado.db")})
    sys.path.insert(0, str(RAIZ))
    from tests.test_bradesco import _fatura_pdf
    pdf = _fatura_pdf(arquivo_fonte=r"C:\Windows\Fonts\arial.ttf")
    corpo, tipo = multipart("fatura-bradesco.pdf", pdf)
    t0 = time.time()
    s, r = pedir(abridor, "POST", "/api/importar", corpo, tipo)
    r = json.loads(r)[0]
    print(f"importação ({time.time() - t0:.0f} s):", r)
    assert s == 200 and r.get("tipo") == "fatura_bradesco_pdf" and r.get("novos") == 6, r

    s, xlsx = pedir(abridor, "GET", "/api/exportar.xlsx")
    assert s == 200 and xlsx[:2] == b"PK"
    s, ods = pedir(abridor, "GET", "/api/exportar.ods/estado")
    ods = json.loads(ods)
    assert s == 200 and ods["disponivel"] is False and ods["motivo"], ods
    print("exportar ok (.xlsx sai; .ods avisa:", ods["motivo"] + ")")

    chave = {"Authorization": f"Bearer {env['API_KEY']}"}
    s, r = pedir(abridor, "POST", "/api/v1/transaction/webhook",
                 {"package": "com.nu.production", "title": "Compra aprovada", "text": "Compra de R$ 12,50 aprovada em Mercadinho Exemplo"},
                 cabecalhos=chave)
    assert s == 202, (s, r)
    s, r = pedir(abridor, "POST", "/api/v1/sync", {"protocolo": 1, "cursor": 0, "mudancas": []}, cabecalhos=chave)
    assert s == 200 and json.loads(r)["mudancas"], (s, r[:200])
    print("webhook e sincronização ok")


if __name__ == "__main__":
    main()
