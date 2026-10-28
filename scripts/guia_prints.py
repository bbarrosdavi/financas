"""Prints e números do guia de uso (docs/GUIA.md), com um banco de demonstração inventado.

    python scripts/guia_prints.py

Sobe o site num banco novo, preenche seis meses de uma pessoa inventada, faz cada passo do guia pela API (como a
tela faz) e guarda os prints em docs/prints/guia/ e os números de antes e depois de cada passo em
docs/prints/guia/numeros.json. Pessoas, lugares e valores são inventados. "Hoje" é fixo em 20/10/2026, no
servidor e no navegador, para os prints saírem iguais a cada vez. Precisa do playwright com o Chromium e, para o
passo da fatura do Bradesco, do tesseract com português e do pdftoppm.
"""

import datetime as _dt
import json
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PRINTS = RAIZ / "docs" / "prints" / "guia"
HOJE = _dt.date(2026, 10, 20)
PORTA = 18765
BASE = f"http://127.0.0.1:{PORTA}"
TMP = Path(tempfile.mkdtemp(prefix="financas-guia-"))
os.environ.update({
    "API_KEY": "chave-da-demonstracao-0000000000000000000000",
    "WEB_PASSWORD": "senha-da-demo",
    "SESSION_SECRET": "segredo-da-demonstracao-000000000000000000",
    "DATABASE_PATH": str(TMP / "demo.db"),
    "PAPEIS_DIR": str(TMP / "papeis"),
    "AVISOS_FILA": "/nao/existe",
    "URL_PUBLICA": "http://192.168.0.10:8095",
})
sys.path.insert(0, str(RAIZ))

from app import bradesco, db, demo, exportar, importadores, main, servicos  # noqa: E402


class _Hoje(_dt.date):
    @classmethod
    def today(cls):
        return HOJE


for _m in (servicos, main, exportar, importadores, bradesco, demo):
    _m.date = _Hoje


# ---------------------------------------------------------------------------
# Banco de demonstração: seis meses (maio a 20 de outubro de 2026) de alguém inventado
# ---------------------------------------------------------------------------
def semear() -> None:
    """O mesmo conjunto inventado da demonstração do app (app/demo.py), com hoje fixo."""
    db.iniciar()
    with db.conectar() as c:
        demo.semear(c, HOJE)


# ---------------------------------------------------------------------------
# Servidor e navegador
# ---------------------------------------------------------------------------
def subir_servidor() -> None:
    import uvicorn
    servidor = uvicorn.Server(uvicorn.Config(main.app, host="127.0.0.1", port=PORTA, log_level="warning"))
    threading.Thread(target=servidor.run, daemon=True).start()
    import urllib.request
    for _ in range(100):
        try:
            urllib.request.urlopen(f"{BASE}/health", timeout=1)
            return
        except OSError:
            time.sleep(0.1)
    raise SystemExit("o servidor da demonstração não subiu")


NUMEROS: dict = {}


def painel(pg, periodo=None) -> dict:
    return pg.request.get(f"{BASE}/api/painel" + (f"?periodo={periodo}" if periodo else "")).json()


def resumo(P: dict) -> dict:
    """Os números que o guia cita, tirados do mesmo JSON que a tela usa."""
    cats = {c["id"]: {k: c[k] for k in ("nome", "gasto", "parcelas", "teto", "acima", "n")} for c in P["categorias"]}
    conta = next(c for c in P["contas"] if c["id"] == "nubank_conta")
    return {
        "periodo": P["periodo"], "totais": P["totais"], "pode_gastar": P["pode_gastar"], "teto_variavel": P["teto_variavel"],
        "gasto_variavel": P["gasto_variavel"], "ritmo": P["ritmo"], "pendentes": P["pendentes"],
        "conta": {k: conta.get(k) for k in ("saldo", "saldo_real", "diferenca", "cobertura")}, "cartao": P["cartao"],
        "pessoas": {p["id"]: {"saldo": p["saldo"], "a_vencer": p["a_vencer"]} for p in P["pessoas"]},
        "metas": {m["nome"]: {k: m[k] for k in ("planejado_periodo", "guardado_periodo", "guardado_total", "falta_periodo",
                                                 "completude_alvo", "por_mes_ate_prazo") if k in m} for m in P["metas"]},
        "categorias": cats, "grupos": P["grupos"], "top": P["top"][:5], "compromissos": P["compromissos"],
        "plano": P["plano"]["linhas"][:5], "plano_falta": P["plano"]["falta_total"],
        "entradas": {e["id"]: e["valor"] for e in P["entradas"] if e["valor"]},
    }


def esperar(pg, seletor="#tela > *", ms=900) -> None:
    pg.wait_for_selector(seletor, timeout=20000)
    pg.wait_for_timeout(ms)


def ir(pg, rota, seletor="#tela > *") -> None:
    pg.evaluate(f"location.hash = '{rota}'")
    pg.wait_for_timeout(200)
    esperar(pg, seletor)


def foto(pg, nome, seletor=None, inteira=False) -> None:
    alvo = PRINTS / f"{nome}.png"
    if seletor:
        pg.locator(seletor).first.screenshot(path=str(alvo))
    else:
        pg.screenshot(path=str(alvo), full_page=inteira)
    print("  print:", alvo.relative_to(RAIZ))


def cartao(pg, cid, nome) -> None:
    foto(pg, nome, f'#mosaico .cartao[data-id="{cid}"]')


def passo(nome: str, pg, acao, rota="#painel", periodo=None, extra=None) -> None:
    antes = resumo(painel(pg, periodo))
    detalhe = acao()
    depois = resumo(painel(pg, periodo))
    NUMEROS[nome] = {"antes": antes, "depois": depois, "detalhe": detalhe, **(extra() if extra else {})}
    print(f"passo {nome}: pode gastar {antes['pode_gastar']} -> {depois['pode_gastar']}, pendentes {antes['pendentes']} -> {depois['pendentes']}")
    ir(pg, rota)


def csv_bytes(linhas: list[str]) -> bytes:
    return ("\n".join(linhas) + "\n").encode()


def importar(pg, nome: str, conteudo: bytes, tipo: str) -> list:
    r = pg.request.post(f"{BASE}/api/importar", multipart={"arquivos": {"name": nome, "mimeType": tipo, "buffer": conteudo}}).json()
    with db.conectar() as c:          # o banco anota a hora do relógio de verdade; a demonstração vive em 20/10
        c.execute("UPDATE importacoes SET quando = '2026-10-20 10:05:00'")
    return r


def main_() -> None:
    from playwright.sync_api import sync_playwright
    PRINTS.mkdir(parents=True, exist_ok=True)
    for f in PRINTS.glob("*.png"):
        if not f.name.startswith("app-"):     # os do app vêm do emulador (ver docs/GUIA.md)
            f.unlink()
    semear()
    subir_servidor()
    with sync_playwright() as p:
        nav = p.chromium.launch(channel="chromium")     # o Chromium completo (headless novo), já baixado pelo playwright
        ctx = nav.new_context(viewport={"width": 1440, "height": 900}, locale="pt-BR", timezone_id="America/Sao_Paulo")
        ctx.add_init_script("localStorage.setItem('tour', 'visto')")     # o tour abre só quando o script pede
        pg = ctx.new_page()
        pg.clock.set_fixed_time(_dt.datetime(2026, 10, 20, 10, 0))
        pg.goto(BASE + "/#painel")
        pg.fill("#senha", os.environ["WEB_PASSWORD"])
        pg.click("#f-login button")
        esperar(pg, "#mosaico .cartao", 1500)

        def tour(pagina, passo_titulo, nome):
            pagina.evaluate("iniciarTour()")
            for _ in range(40):
                pagina.wait_for_timeout(1100)
                if pagina.inner_text(".tour-topo b") == passo_titulo:
                    break
                pagina.click('[data-tour="proximo"]')
            pagina.wait_for_timeout(600)
            foto(pagina, nome)
            pagina.click('[data-tour="sair"]')
            ir(pagina, "#painel", "#mosaico .cartao")
        tour(pg, "Ainda pode gastar", "tour-pc")

        # 1. As telas e os cartões, no estado inicial da demonstração
        NUMEROS["inicio"] = resumo(painel(pg))
        foto(pg, "painel", inteira=True)
        foto(pg, "painel-periodo", ".periodo")
        for cid in ("resumo", "categorias", "grafico", "composicao", "entradas", "metas", "cobrancas", "destinos", "plano"):
            cartao(pg, cid, f"cartao-{cid}")
        pg.locator('[data-evol-grupo="Alimentação"]').first.click()
        esperar(pg, "#editor[open] svg", 700)
        foto(pg, "evolucao-alimentacao", "#editor")
        pg.click("#ev-x")
        for rota, nome, inteira in (("#pendentes", "pendentes", True), ("#lancamentos", "lancamentos", False), ("#orcamento", "orcamento", False),
                                    ("#importar", "importar", True), ("#pessoas", "pessoas", True), ("#projecao", "projecao", False),
                                    ("#ajustes", "ajustes", False)):
            ir(pg, rota)
            foto(pg, nome, inteira=inteira)

        # 2. Passo a passo: cada ação e os números que ela muda
        ir(pg, "#painel", "#mosaico .cartao")
        lid_manual = {}

        def manual():
            r = pg.request.post(f"{BASE}/api/lancamentos", data={"data": "2026-10-20", "conta": "nubank_conta", "valor": -45.0,
                                                                "descricao": "Feira do bairro", "partes": [
                                                                    {"valor": -45.0, "natureza": "gasto", "categoria": "mercado"}]}).json()
            lid_manual.update(r)
            return r
        cartao(pg, "resumo", "passo-manual-antes")
        passo("manual", pg, manual)
        cartao(pg, "resumo", "passo-manual-depois")
        ir(pg, "#lancamentos")
        foto(pg, "passo-manual-lancamentos")

        ir(pg, "#pendentes")
        foto(pg, "passo-pendente-antes", inteira=True)
        loja = next(l for l in pg.request.get(f"{BASE}/api/lancamentos?pendentes=true").json() if l["descricao"] == "Loja Nova Exemplo")
        passo("pendente", pg, lambda: pg.request.put(f"{BASE}/api/lancamentos/{loja['id']}/partes", data={
            "partes": [{"valor": loja["valor"], "natureza": "gasto", "categoria": "vestuario"}], "lembrar": True}).json(), rota="#pendentes")
        foto(pg, "passo-pendente-depois", inteira=True)

        extrato = csv_bytes([
            "Data,Valor,Identificador,Descrição",
            "17/10/2026,-18.50,00000000-0000-0000-0000-000000000001,Compra no débito - PADARIA PAO QUENTE",
            "18/10/2026,-62.30,00000000-0000-0000-0000-000000000002,Compra no débito - SUPERMERCADO EXEMPLO",
            "19/10/2026,650.00,00000000-0000-0000-0000-000000000003,Transferência recebida pelo Pix - MARINA EXEMPLO - •••.111.222-•• - BCO EXEMPLO",
        ])
        imp = {}
        passo("extrato", pg, lambda: imp.setdefault("r", importar(pg, "extrato-outubro.csv", extrato, "text/csv")), rota="#importar")
        foto(pg, "passo-extrato-importar", inteira=True)

        pend_marina = next(l for l in pg.request.get(f"{BASE}/api/lancamentos?pendentes=true").json() if "MARINA" in l["contraparte"])
        NUMEROS["marina_sugestao"] = pend_marina["sugestao"]
        ir(pg, "#pessoas")
        foto(pg, "passo-acerto-antes", inteira=True)
        passo("acerto", pg, lambda: pg.request.put(f"{BASE}/api/lancamentos/{pend_marina['id']}/partes", data={
            "partes": [{"valor": 650.0, "natureza": "acerto", "pessoa": "marina"}], "lembrar": False}).json(), rota="#pessoas")
        foto(pg, "passo-acerto-depois", inteira=True)

        fatura = csv_bytes([
            "date,title,amount",
            "2026-10-19,Uber *Trip,23.10",
            "2026-10-19,Loja Casa Exemplo - Parcela 1/3,120.00",
            "2026-11-19,Loja Casa Exemplo - Parcela 2/3,120.00",
            "2026-12-19,Loja Casa Exemplo - Parcela 3/3,120.00",
        ])
        passo("fatura", pg, lambda: importar(pg, "fatura-novembro.csv", fatura, "text/csv"))
        cartao(pg, "cobrancas", "passo-fatura-cobrancas")

        push = {"package": "com.nu.production", "title": "Compra no crédito aprovada",
                "text": "Compra de R$ 32,40 aprovada em Drogasil no cartão final 1234", "timestamp": 1792501200000}

        def celular():
            r = pg.request.post(f"{BASE}/api/v1/transaction/webhook", data=push, headers={"Authorization": f"Bearer {os.environ['API_KEY']}"})
            time.sleep(1.5)       # o servidor aplica numa fila; o app do celular aplica na hora
            return {"status": r.status, **r.json()}
        passo("push", pg, celular, rota="#lancamentos")
        foto(pg, "passo-push-lancamentos")


        passo("orcamento", pg, lambda: pg.request.put(f"{BASE}/api/orcamento", data={"chave": "mercado", "mes": "2026-10", "valor": 700.0,
                                                                                    "ate_dezembro": False}).json())
        cartao(pg, "categorias", "passo-orcamento-categorias")
        ir(pg, "#orcamento")
        foto(pg, "passo-orcamento-grade")

        passo("meta", pg, lambda: pg.request.post(f"{BASE}/api/lancamentos", data={"data": "2026-10-20", "conta": "nubank_conta", "valor": -250.0,
                                                                                 "descricao": "Dinheiro guardado", "partes": [
                                                                                     {"valor": -250.0, "natureza": "poupanca", "meta": 2}]}).json())
        cartao(pg, "metas", "passo-meta-metas")

        # O app do banco mostra R$ 27,90 a menos: um café no débito que ainda não chegou em lugar nenhum.
        calculado = resumo(painel(pg))["conta"]["saldo"]
        NUMEROS["saldo_informado"] = round(calculado - 27.9, 2)
        passo("saldo", pg, lambda: pg.request.put(f"{BASE}/api/contas/nubank_conta/saldo", data={
            "valor": NUMEROS["saldo_informado"], "data": "2026-10-20"}).json())
        cartao(pg, "resumo", "passo-saldo-resumo")

        ev = {}
        passo("evento", pg, lambda: ev.setdefault("r", pg.request.post(f"{BASE}/api/eventos", data={
            "nome": "Freela de dezembro", "tipo": "entrada_unica", "inicio": "2026-12", "valor": 800, "ativo": True}).json()), rota="#projecao")
        foto(pg, "passo-evento-projecao")

        # 3. Tema escuro e o tamanho de celular (o app Android mostra este mesmo site)
        pg.evaluate("localStorage.setItem('tema', 'dark')")
        ir(pg, "#painel", "#mosaico .cartao")
        pg.reload()
        esperar(pg, "#mosaico .cartao", 1500)
        foto(pg, "painel-escuro")
        cel = nav.new_context(viewport={"width": 412, "height": 915}, device_scale_factor=2, locale="pt-BR",
                              timezone_id="America/Sao_Paulo", is_mobile=True, has_touch=True, storage_state=ctx.storage_state())
        pc = cel.new_page()
        pc.clock.set_fixed_time(_dt.datetime(2026, 10, 20, 10, 0))
        pc.goto(BASE + "/#painel")
        esperar(pc, "#mosaico .cartao", 1500)
        foto(pc, "celular-painel")
        ir(pc, "#pendentes")
        foto(pc, "celular-pendentes")
        tour(pc, "Categorias", "tour-celular")
        NUMEROS["final"] = resumo(painel(pg))
        nav.close()
    (PRINTS / "numeros.json").write_text(json.dumps(NUMEROS, ensure_ascii=False, indent=1))
    print("números em", (PRINTS / "numeros.json").relative_to(RAIZ))


if __name__ == "__main__":
    main_()
