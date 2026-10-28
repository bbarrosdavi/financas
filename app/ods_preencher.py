"""Preenche o modelo da planilha antiga com os dados do site, pelo LibreOffice.

Roda com o python do sistema (o que tem o módulo uno), fora do app, chamado por app/exportar.py:
    /usr/bin/python3 ods_preencher.py dados.json modelo.ods saida.ods pasta_temporaria

Abas do modelo e o que entra em cada uma:
- Settings: ano inicial, renda que cai a partir do dia de corte conta no mês seguinte (como no site).
- Budget Planning: orçamento de cada mês (Income por categoria, Expenses por grupo, Savings por meta).
- Budget Tracking: renda, gasto e poupança, do mais recente para o mais antigo, com a linha 12 vazia
  para lançar à mão; pendentes em âmbar. Os intervalos das fórmulas (até a linha 1037) crescem se precisar.
- Depesas Fixas: um bloco por mês do ano, com os itens de cada grupo e a soma.
- Budget Dashboard: ano e mês atuais selecionados.
Depois delas, as tabelas do site em abas novas.
"""

import json
import os
import signal
import subprocess
import sys
import time
import uuid
from datetime import date

import uno
from com.sun.star.beans import PropertyValue
from com.sun.star.lang import Locale
from com.sun.star.table import CellAddress

LIMPAR = 1 | 2 | 4 | 16                 # valor, data, texto, fórmula (o formato fica)
LIMPAR_TUDO = LIMPAR | 32 | 64 | 256 | 512
AMBAR, CAB = 0xFFC94D, 0x2F3B4C
MESES = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
# Blocos do Budget Planning: primeira linha (1-based), linhas do bloco e o prefixo dos intervalos nomeados.
# O Dashboard conta os nomes com COUNTA fixo em C10:C16, C23:C35 e C39:C40: por isso Income vai até 7 linhas
# e Savings até 2 (app/exportar.py junta o excedente na última).
BLOCOS = {"renda": (10, 10, "income"), "gastos": (23, 13, "expenses"), "poupanca": (39, 7, "savings")}


def prop(nome, valor):
    p = PropertyValue()
    p.Name, p.Value = nome, valor
    return p


def serial(iso: str) -> float:
    return float((date.fromisoformat(iso) - date(1899, 12, 30)).days)


def letra(col: int) -> str:
    s = ""
    col += 1
    while col:
        col, r = divmod(col - 1, 26)
        s = chr(65 + r) + s
    return s


def abrir_libreoffice(perfil: str):
    nome = "financas_" + uuid.uuid4().hex
    proc = subprocess.Popen(["soffice", "--headless", "--invisible", "--norestore", "--nologo", "--nodefault",
                             f"-env:UserInstallation=file://{perfil}/lo", f"--accept=pipe,name={nome};urp;"],
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    ctx = uno.getComponentContext()
    res = ctx.ServiceManager.createInstanceWithContext("com.sun.star.bridge.UnoUrlResolver", ctx)
    for _ in range(240):
        try:
            remoto = res.resolve(f"uno:pipe,name={nome};urp;StarOffice.ComponentContext")
            return proc, remoto.ServiceManager.createInstanceWithContext("com.sun.star.frame.Desktop", remoto)
        except Exception:
            if proc.poll() is not None:
                break
            time.sleep(0.25)
    fechar(proc, None)
    raise RuntimeError("o LibreOffice não respondeu")


def fechar(proc, desktop) -> None:
    try:
        if desktop is not None:
            desktop.terminate()
        proc.wait(timeout=20)
    except Exception:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except Exception:
            pass


def planning(doc, d: dict) -> None:
    sh = doc.Sheets.getByName("Budget Planning")
    nr = doc.NamedRanges
    # Os totais (linhas 20, 36 e 46) viram somas das linhas do bloco (o modelo já vem sem as matrizes
    # encavaladas: scripts/limpar_modelo_ods.py). A limpeza da linha 20 à 48 leva junto os cabeçalhos
    # 22 e 38, que voltam da linha 9.
    cab = sh.getCellRangeByPosition(4, 8, 142, 8).getFormulaArray()
    sh.getCellRangeByPosition(4, 19, 142, 47).clearContents(LIMPAR)
    for r in (21, 37):
        sh.getCellRangeByPosition(4, r, 142, r).setFormulaArray(cab)
    for chave, (ini, cap, prefixo) in BLOCOS.items():
        itens = d[chave][:cap]
        sh.getCellRangeByPosition(2, ini - 1, 142, ini + cap - 2).clearContents(LIMPAR)
        for i, it in enumerate(itens):
            linha = ini - 1 + i
            sh.getCellByPosition(2, linha).setString(it["nome"])
            for mes, v in it["meses"].items():
                if v is None:
                    continue
                bloco = int(mes[:4]) - d["ano_inicial"]
                if 0 <= bloco < 10:
                    sh.getCellByPosition(4 + 14 * bloco + int(mes[5:7]) - 1, linha).setValue(v)
            for bloco in range(10):                          # coluna "Total" de cada ano
                c = 4 + 14 * bloco
                sh.getCellByPosition(c + 12, linha).setFormula(f"=SUM({letra(c)}{linha + 1}:{letra(c + 11)}{linha + 1})")
        fim = ini + max(len(itens), 1) - 1
        total = tuple(f"=SUM({letra(c)}{ini}:{letra(c)}{fim})" if (c - 4) % 14 <= 12 else "" for c in range(4, 143))
        sh.getCellRangeByPosition(4, ini + cap - 1, 142, ini + cap - 1).setFormulaArray((total,))      # linhas 20, 36, 46
        nr.getByName(f"{prefixo}_min_row").setContent(f"MIN(ROW($'Budget Planning'.$C${ini}:$C${fim}))")
        nr.getByName(f"{prefixo}_max_row").setContent(f"MAX(ROW($'Budget Planning'.$C${ini}:$C${fim}))")


def tracking(doc, d: dict) -> None:
    sh = doc.Sheets.getByName("Budget Tracking")
    linhas = d["tracking"]
    ultima = max(1037, 13 + len(linhas) + 100)
    sh.getCellRangeByPosition(2, 11, 6, 1036).clearContents(LIMPAR)       # C12:G1037, os exemplos do modelo
    # As fórmulas de todas as abas contam até a linha 1037. Linhas inseridas antes dela esticam todas essas
    # referências sozinhas (reescrever o texto das fórmulas quebra as de matriz no LibreOffice 25).
    if ultima > 1037:
        sh.Rows.insertByIndex(1036, ultima - 1037)
    # A linha 13 vira molde (formatos, validação, fórmulas de H e I); dobrando a cópia, cobre até a última.
    fim = 13
    while fim < ultima:
        n = min(fim - 12, ultima - fim)
        sh.copyRange(CellAddress(sh.RangeAddress.Sheet, 2, fim), sh.getCellRangeByPosition(2, 12, 8, 12 + n - 1).getRangeAddress())
        fim += n
    if linhas:
        dados = tuple((serial(l["data"]), l["tipo"], l["categoria"], float(l["valor"]), l["detalhes"]) for l in linhas)
        sh.getCellRangeByPosition(2, 12, 6, 12 + len(linhas) - 1).setDataArray(dados)
    for i, l in enumerate(linhas):
        if l["pendente"]:
            sh.getCellRangeByPosition(2, 12 + i, 8, 12 + i).CellBackColor = AMBAR


def despesas_fixas(doc, d: dict) -> None:
    sh = doc.Sheets.getByName("Depesas Fixas")
    grupos, meses = d["fixas"]["grupos"], d["fixas"]["meses"]
    k = max([6] + [len(g["itens"]) for g in grupos])
    larg = 1 + k
    ult = 5 + 2 * max(len(grupos), 1)                     # última linha (1-based)
    w_cat, w_item = sh.Columns.getByIndex(1).Width, sh.Columns.getByIndex(2).Width
    # Molde: o primeiro bloco do modelo (B3:H25), copiado para longe, esticado em linhas e colunas.
    rascunho = 400
    s_id = sh.RangeAddress.Sheet
    sh.copyRange(CellAddress(s_id, rascunho, 2), sh.getCellRangeByPosition(1, 2, 7, 24).getRangeAddress())
    linha = 25
    while linha < ult:
        sh.copyRange(CellAddress(s_id, rascunho, linha), sh.getCellRangeByPosition(rascunho, 23, rascunho + 6, 24).getRangeAddress())
        linha += 2
    for c in range(7, k + 1):
        sh.copyRange(CellAddress(s_id, rascunho + c, 2), sh.getCellRangeByPosition(rascunho + 6, 2, rascunho + 6, ult - 1).getRangeAddress())
    area = sh.getCellRangeByPosition(1, 2, rascunho - 1, max(ult, 25))
    area.merge(False)
    area.clearContents(LIMPAR_TUDO)
    molde = sh.getCellRangeByPosition(rascunho, 2, rascunho + k, ult - 1).getRangeAddress()
    for b, mes in enumerate(meses):
        c0 = 1 + b * larg
        sh.copyRange(CellAddress(s_id, c0, 2), molde)
        sh.getCellRangeByPosition(c0, 4, c0 + k, ult - 1).clearContents(LIMPAR)
        sh.getCellByPosition(c0, 2).setString(MESES[int(mes[5:7]) - 1])
        sh.getCellByPosition(c0, 4).setString("Categoria")
        sh.getCellByPosition(c0 + 1, 4).setString("Itens")
        sh.Columns.getByIndex(c0).Width = w_cat
        for j in range(k):
            sh.Columns.getByIndex(c0 + 1 + j).Width = w_item
        for i, g in enumerate(grupos):
            rn, rv = 5 + 2 * i, 6 + 2 * i
            sh.getCellByPosition(c0, rn).setString(g["nome"])
            sh.getCellByPosition(c0, rv).setFormula(f"=SUM({letra(c0 + 1)}{rv + 1}:{letra(c0 + k)}{rv + 1})")
            for j, it in enumerate(g["itens"]):
                sh.getCellByPosition(c0 + 1 + j, rn).setString(it["nome"])
                if mes in it["valores"]:
                    sh.getCellByPosition(c0 + 1 + j, rv).setValue(it["valores"][mes])
    sh.getCellRangeByPosition(rascunho, 0, rascunho + k + 1, ult + 2).clearContents(LIMPAR_TUDO)


def abas_extras(doc, abas: list[dict]) -> None:
    formatos = doc.NumberFormats
    local = Locale("en", "US", "")
    codigo = "#,##0.00;[RED]-#,##0.00"
    moeda = formatos.queryKey(codigo, local, False)
    if moeda == -1:
        moeda = formatos.addNew(codigo, local)
    ctrl = doc.getCurrentController()
    for a in abas:
        nome = a["nome"]
        if doc.Sheets.hasByName(nome):
            nome += " (site)"
        doc.Sheets.insertNewByName(nome, doc.Sheets.getCount())
        sh = doc.Sheets.getByName(nome)
        ncol = len(a["cab"])
        linhas = [tuple(a["cab"])] + [tuple("" if v is None else (float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else str(v))
                                            for v in l) for l in a["linhas"]]
        sh.getCellRangeByPosition(0, 0, ncol - 1, len(linhas) - 1).setDataArray(tuple(linhas))
        cab = sh.getCellRangeByPosition(0, 0, ncol - 1, 0)
        cab.CellBackColor, cab.CharColor, cab.CharWeight = CAB, 0xFFFFFF, 150.0
        if len(linhas) > 1:
            for col in a["moeda"]:
                sh.getCellRangeByPosition(col - 1, 1, col - 1, len(linhas) - 1).NumberFormat = moeda
        for i, w in enumerate(a["larg"]):
            sh.Columns.getByIndex(i).Width = int(w * 200)
        for i in a.get("destaque", []):
            sh.getCellByPosition(6, i + 1).CellBackColor = AMBAR
        try:
            ctrl.setActiveSheet(sh)
            ctrl.freezeAtPosition(0, 1)
        except Exception:
            pass
    try:
        ctrl.setActiveSheet(doc.Sheets.getByName("Budget Dashboard"))
    except Exception:
        pass


# Caixas de indicador do modelo: no Excel eram ligadas a células da aba Calculations; no LibreOffice viram
# texto parado. O rótulo (primeiro texto do grupo) diz qual caixa é; o valor vem da célula, na exportação.
CAIXAS = {
    "Selected Year & Period": {2: "E19", 3: "E21"},
    "Period Compl.": {3: "E24"},
    "Period Tracking Balance": {2: "E25", 3: "E26"},
    "Period Savings Rate": {2: "E27"},
    "Date of Today": {2: "E8"},
    "Date of Last Record": {2: "E9", 3: "E10"},
    "N° of Tracked Records": {2: "E11", 3: "E12"},
    "Total Tracking Balance": {2: "E13", 3: "E14"},
}


def atualizar_caixas(doc) -> None:
    calc = doc.Sheets.getByName("Calculations")
    for nome in ("Budget Dashboard", "Budget Tracking"):
        dp = doc.Sheets.getByName(nome).DrawPage
        for i in range(dp.Count):
            g = dp.getByIndex(i)
            if not g.ShapeType.endswith("GroupShape") or g.Count < 2:
                continue
            for idx, celula in CAIXAS.get(g.getByIndex(1).getString(), {}).items():
                if idx < g.Count:
                    g.getByIndex(idx).setString(calc.getCellRangeByName(celula).getString())


def preencher(doc, d: dict) -> None:
    st = doc.Sheets.getByName("Settings")
    st.getCellRangeByName("E8").setValue(d["ano_inicial"])
    st.getCellRangeByName("E16").setString("Active")
    st.getCellRangeByName("E18").setValue(d["dia_corte"])
    doc.CharLocale = Locale("pt", "BR", "")          # datas e números em português, seja qual for o sistema
    planning(doc, d)
    tracking(doc, d)
    despesas_fixas(doc, d)
    db = doc.Sheets.getByName("Budget Dashboard")
    db.getCellRangeByName("AQ6").setValue(d["ano"])
    db.getCellRangeByName("AQ9").setValue(serial(f"2000-{d['mes']:02d}-01"))
    abas_extras(doc, d["abas"])
    doc.calculateAll()
    atualizar_caixas(doc)


def main() -> None:
    entrada, modelo, saida, tmp = sys.argv[1:5]
    d = json.loads(open(entrada, encoding="utf-8").read())
    proc, desktop = abrir_libreoffice(tmp)
    doc = None
    try:
        doc = desktop.loadComponentFromURL(uno.systemPathToFileUrl(os.path.abspath(modelo)), "_blank", 0, (prop("Hidden", True),))
        preencher(doc, d)
        doc.storeToURL(uno.systemPathToFileUrl(os.path.abspath(saida)), (prop("FilterName", "calc8"),))
    finally:
        if doc is not None:
            doc.close(True)
        fechar(proc, desktop)


if __name__ == "__main__":
    main()
