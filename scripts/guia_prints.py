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
import random
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

from app import bradesco, db, exportar, importadores, main, servicos  # noqa: E402


class _Hoje(_dt.date):
    @classmethod
    def today(cls):
        return HOJE


for _m in (servicos, main, exportar, importadores, bradesco):
    _m.date = _Hoje


# ---------------------------------------------------------------------------
# Banco de demonstração: seis meses (maio a 20 de outubro de 2026) de alguém inventado
# ---------------------------------------------------------------------------
def gasto(v, cat):
    return [{"valor": v, "natureza": "gasto", "categoria": cat}]


def semear() -> None:
    db.iniciar()
    sorte = random.Random(2026)
    with db.conectar() as c:
        c.executemany("INSERT INTO pessoas (id, nome, tipo, apelido_extrato, sugere_entrada, sugere_saida) VALUES (?,?,?,?,?,?)",
                      [("marina", "Marina", "colega", "MARINA EXEMPLO", "acerto", "acerto"),
                       ("teo", "Téo", "colega", "TEO FICTICIO", "acerto", "acerto"),
                       ("mae", "Mãe", "familia", "ROSA EXEMPLO", "renda:pais", "acerto")])
        for cid, teto in {"mercado": 600, "delivery": 250, "app-transporte": 150, "lazer": 200, "conveniencia": 100,
                          "vestuario": 150, "eletronicos": 150, "remedios": 80, "academia": 90, "assinaturas": 60,
                          "contas-casa": 150, "onibus": 80}.items():
            c.execute("UPDATE categorias SET teto = ? WHERE id = ?", (teto, cid))
        c.execute("UPDATE categorias SET orcar_por_itens = 1 WHERE id = 'aluguel-condominio'")
        c.executemany("INSERT INTO itens_fixos (categoria, nome, valor, ordem) VALUES (?,?,?,?)",
                      [("aluguel-condominio", "Aluguel (minha metade)", 600, 1), ("aluguel-condominio", "Condomínio (minha metade)", 50, 2)])
        c.execute("UPDATE contas SET saldo_inicial = 300, data_saldo_inicial = '2026-05-01' WHERE id = 'nubank_conta'")
        c.execute("UPDATE contas SET saldo_inicial = 0, data_saldo_inicial = '2026-05-01', limite = 3000 WHERE id = 'nubank_cartao'")
        c.execute("UPDATE contas SET data_saldo_inicial = '2026-05-01' WHERE id = 'picpay'")
        for k, v in {"salario_mensal": "2600", "horizonte": "2027-03", "aluguel_rateio": '{"eu": 0.5, "marina": 0.5}'}.items():
            db.definir_parametro(c, k, v)
        c.execute("INSERT INTO metas (nome, descricao, alvo, aporte_mensal, onde, ordem) VALUES "
                  "('Reserva de emergência', 'Seis meses de custo fixo', 6000, 300, 'Caixinha do Nubank', 1)")
        c.execute("INSERT INTO metas (nome, alvo, data_alvo, aporte_mensal, onde, ordem) VALUES "
                  "('Notebook novo', 4500, '2027-06', 250, 'Caixinha do Nubank', 2)")
        c.executemany("INSERT INTO eventos (nome, tipo, inicio, fim, valor) VALUES (?,?,?,?,?)",
                      [("13º salário", "entrada_unica", "2026-12", None, 2600), ("Viagem de janeiro", "saida_unica", "2027-01", None, 1800)])

        def lanc(conta, d, valor, desc, contra="", origem=None, partes=None, parcela=None):
            if d > HOJE:
                return
            origem = origem or ("fatura_csv" if conta == "nubank_cartao" else "extrato_csv")
            servicos.inserir(c, conta, d.isoformat(), round(valor, 2), desc, contra, origem, partes=partes, parcela=parcela)

        fatura_anterior = 0.0
        for mes in range(5, 11):
            d = lambda dia: _dt.date(2026, mes, dia)
            sigla = ["MAI", "JUN", "JUL", "AGO", "SET", "OUT"][mes - 5]
            lanc("nubank_conta", d(5), 2600, "Transferência recebida pelo Pix", "EMPRESA EXEMPLO LTDA", partes=[
                {"valor": 2600, "natureza": "renda", "categoria": "salario"}])
            lanc("nubank_conta", d(6), -1300, "Pagamento de boleto efetuado", "IMOBILIARIA EXEMPLO LTDA", partes=[
                {"valor": -650, "natureza": "gasto", "categoria": "aluguel-condominio"},
                {"valor": -650, "natureza": "acerto", "pessoa": "marina"}])
            lanc("nubank_conta", d(6), -300, "Aplicação RDB", partes=[{"valor": -300, "natureza": "poupanca", "meta": 1}])
            if fatura_anterior:
                lanc("nubank_conta", d(7), -fatura_anterior, "Pagamento de fatura")
                lanc("nubank_cartao", d(7), fatura_anterior, f"Pagamento em 07 {sigla}")
            if mes < 10:
                lanc("nubank_conta", d(10), 650, "Transferência recebida pelo Pix", "MARINA EXEMPLO", partes=[
                    {"valor": 650, "natureza": "acerto", "pessoa": "marina"}])
            luz = -sorte.choice([78.4, 85.1, 91.7])
            lanc("nubank_conta", d(12), luz, "Pagamento de boleto efetuado", "LUZ DISTRIBUIDORA EXEMPLO", partes=gasto(luz, "contas-casa"))
            lanc("nubank_conta", d(14), 200, "Transferência recebida pelo Pix", "ROSA EXEMPLO", partes=[
                {"valor": 200, "natureza": "renda", "categoria": "pais"}])
            # Cartão
            cartao = [(3, -90, "Academia Movimento Exemplo", "academia"), (9, -39.9, "Streaming Exemplo", "assinaturas"), (15, -19.9, "Música Exemplo", "assinaturas")]
            cartao += [(dia, -round(sorte.uniform(110, 190), 2), "Supermercado Exemplo", "mercado") for dia in (4, 13, 24)]
            cartao += [(dia, -round(sorte.uniform(35, 65), 2), "Delivery Cozinha Exemplo", "delivery") for dia in (8, 17, 27)]
            cartao += [(dia, -round(sorte.uniform(14, 28), 2), "Uber *Trip", "app-transporte") for dia in (2, 9, 16, 22, 29)]
            cartao += [(11, -round(sorte.uniform(35, 60), 2), "Cinema Exemplo", "lazer"), (25, -round(sorte.uniform(60, 95), 2), "Bar do Exemplo", "lazer")]
            cartao += [(19, -round(sorte.uniform(30, 60), 2), "Drogaria Exemplo", "remedios")]
            cartao += [(dia, -round(sorte.uniform(9, 20), 2), "Conveniencia Posto Exemplo", "conveniencia") for dia in (6, 21)]
            if mes in (6, 8):
                cartao.append((18, -round(sorte.uniform(80, 140), 2), "Loja Roupa Exemplo", "vestuario"))
            for dia, v, desc, cat in cartao:
                lanc("nubank_cartao", d(dia), v, desc, partes=gasto(v, cat))
            if mes >= 8:
                n = mes - 7
                lanc("nubank_cartao", d(11), -250, f"Loja Eletro Exemplo - Parcela {n}/6", partes=gasto(-250, "eletronicos"), parcela=f"{n}/6")
            if mes == 9:
                lanc("nubank_cartao", d(19), -120, "Restaurante Exemplo", partes=[
                    {"valor": -60, "natureza": "gasto", "categoria": "delivery"}, {"valor": -60, "natureza": "acerto", "pessoa": "teo"}])
            fatura_anterior = -round(sum(r[0] for r in c.execute(
                "SELECT valor FROM lancamentos WHERE conta = 'nubank_cartao' AND valor < 0 AND substr(data, 1, 7) = ?",
                (f"2026-{mes:02d}",))), 2)
        # Outubro: o que ainda espera você
        servicos.inserir(c, "nubank_conta", "2026-10-17", -18.5, "Padaria Pão Quente", origem="push", ref="inbox:1")
        servicos.inserir(c, "nubank_cartao", "2026-10-15", -104.9, "Picpay*Recarga Exemplo", origem="fatura_csv")
        servicos.inserir(c, "nubank_conta", "2026-10-16", -30.0, "Transferência enviada pelo Pix", "TEO FICTICIO", "extrato_csv")
        servicos.inserir(c, "nubank_cartao", "2026-10-18", -89.9, "Loja Nova Exemplo", origem="push", ref="inbox:2")
        db.definir_parametro(c, "pessoas_ajuste", json.dumps({"data": "2026-04-30", "saldos": {}}))


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
