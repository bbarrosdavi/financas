"""Bradesco: extrato (PDF, CSV, Excel) e fatura em aberto (PDF de imagem, lida por OCR).

Os arquivos daqui são inventados no formato do banco; nenhum dado real.
"""

import io
import shutil
import subprocess

import pytest

from app import bradesco, importadores, servicos

EXTRATO_PDF = """\
                                              Bradesco Celular
                                              Data: 26/10/2026 - 21h06
                                              Nome: FULANO DE TAL


Extrato de: Agência: 1234 | Conta: 98765-4                                                                     Folha: 1/1


Data               Histórico                                             Docto.    Crédito (R$)   Débito (R$)   Saldo (R$)


                   PIX RECEBIDO
19/10/2026                                                               1000001        500,00                   1.500,00
                   REM: Ciclano da Silva 18/10

                   PIX QR CODE DINAMICO
                                                                         1000002                       64,00     1.436,00
                   DES: TELEFONIA EXEMPLO 22/10


                   PIX QR CODE ESTATICO
26/10/2026                                                               1000003                      236,00     1.200,00
                   DES: LUZ DISTRIBUIDORA S. 24/10


Total                                                                                    500,00       300,00     1.200,00
"""

EXTRATO_CSV = ("﻿Extrato de: Ag: 1234 | Conta: 98765-4;;;;;\n"
               "Data;Histórico;Docto.;Crédito (R$);Débito (R$);Saldo (R$)\n"
               "19/10/2026;PIX RECEBIDO;1000001;500,00; ;1.500,00\n"
               "22/10/2026;PIX QR CODE DINAMICO;1000002; ;64,00;1.436,00\n"
               "26/10/2026;PIX QR CODE ESTATICO;1000003; ;236,00;1.200,00\n"
               ";;;;;\n"
               "Os dados acima tem como base 26/10/2026 às 21:02 e estão sujeitos a alterações.;;;;;\n"
               "Lançamentos periódicos;;;;;\n"
               "Data;Histórico;Docto.;Crédito (R$);Débito (R$);\n"
               ";;;;Não há lançamentos disponíveis;;;;\n"
               ";;Total;0,00;0,00;0,00;\n")


def _valores(lt):
    return [(m.data, m.conta, m.valor, m.descricao, m.contraparte) for m in lt.movimentos]


def test_extrato_pdf_com_data_herdada_e_contraparte():
    assert bradesco.eh_extrato_pdf(EXTRATO_PDF)
    lt = bradesco.ler_extrato_pdf(EXTRATO_PDF)
    assert _valores(lt) == [
        ("2026-10-19", "bradesco_conta", 500.0, "PIX RECEBIDO", "Ciclano da Silva"),
        ("2026-10-19", "bradesco_conta", -64.0, "PIX QR CODE DINAMICO", "TELEFONIA EXEMPLO"),
        ("2026-10-26", "bradesco_conta", -236.0, "PIX QR CODE ESTATICO", "LUZ DISTRIBUIDORA S.")]
    assert lt.totais["saldo_inicial"] == 1000.0 and lt.totais["data_saldo_inicial"] == "2026-10-19"


def test_extrato_que_nao_fecha_e_recusado():
    with pytest.raises(ValueError, match="não fecha"):
        bradesco.ler_extrato_pdf(EXTRATO_PDF.replace("1.436,00", "1.437,00"))
    with pytest.raises(ValueError, match="não fecha"):
        importadores.ler_arquivo("x.csv", EXTRATO_CSV.replace("1.436,00", "1.430,00").encode())


def test_extrato_csv_e_excel():
    lt = importadores.ler_arquivo("extrato.csv", EXTRATO_CSV.encode())
    assert lt.tipo == "extrato_bradesco_csv"
    assert [(m.data, m.valor) for m in lt.movimentos] == [("2026-10-19", 500.0), ("2026-10-22", -64.0), ("2026-10-26", -236.0)]
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.create_sheet("Extrato", 0)
    for linha in EXTRATO_CSV.lstrip("﻿").splitlines():
        ws.append([float(c.replace(".", "").replace(",", ".")) if c.strip().replace(".", "").replace(",", "").isdigit() and "," in c
                   else c for c in linha.split(";")])
    buf = io.BytesIO()
    wb.save(buf)
    lx = importadores.ler_arquivo("extrato.xlsx", buf.getvalue())
    assert lx.tipo == "extrato_bradesco_xlsx"
    assert [(m.data, m.valor) for m in lx.movimentos] == [(m.data, m.valor) for m in lt.movimentos]


def test_importar_cria_a_conta_com_o_saldo_do_extrato(con):
    r = servicos.importar(con, "extrato.csv", EXTRATO_CSV.encode())
    assert r["novos"] == 3
    c = con.execute("SELECT * FROM contas WHERE id='bradesco_conta'").fetchone()
    assert (c["nome"], c["tipo"], c["saldo_inicial"], c["data_saldo_inicial"]) == ("Bradesco", "corrente", 1000.0, "2026-10-19")
    assert servicos.importar(con, "extrato.csv", EXTRATO_CSV.encode())["repetidos"] == 3
    saldo = next(s for s in servicos.saldo_contas(con) if s["id"] == "bradesco_conta")["saldo"]
    assert saldo == 1200.0


# ---------------------------------------------------------------------------
# Fatura em aberto: um PDF só de imagem, como o que o aplicativo gera
# ---------------------------------------------------------------------------
LINHAS_CARTAO_1 = [("25/10", "SALDO ANTERIOR", "R$ 300,00"), ("22/10", "PADARIA EXEMPLO", "R$ 18,90"),
                   ("21/10", "MERCADO DO BAIRRO", "R$ 127,45"), ("18/10", "IOF S/ TRANS INTER REAIS", "R$ 10,50"),
                   ("12/10", "PAGTO ANTECIPADO PIX", "R$ -300,00")]
LINHAS_CARTAO_2 = [("19/08", "LOJA ONLINE", "R$ 59,90"), ("14/10", "APP DE TRANSPORTE", "R$ 23,75")]


def _fatura_pdf(total_1="R$ 156,85", total_2="R$ 83,65") -> bytes:
    from PIL import Image, ImageDraw, ImageFont
    fonte = ImageFont.truetype(subprocess.run(["fc-match", "-f", "%{file}", "DejaVu Sans"], capture_output=True,
                                              text=True).stdout, 30)
    img = Image.new("RGB", (1980, 2600), "white")
    d = ImageDraw.Draw(img)
    d.text((300, 80), "Aplicativo Bradesco", fill="black", font=fonte)
    d.text((300, 160), "Data: 26/10/2026 - 21:04", fill="black", font=fonte)
    d.text((80, 280), "Situação do Extrato: Em Aberto", fill="black", font=fonte)
    y = 380
    for nome, final, linhas, total in (("FULANO DE TAL", "1234", LINHAS_CARTAO_1, total_1),
                                       ("FULANO DE TAL", "5678", LINHAS_CARTAO_2, total_2)):
        # como no aplicativo: o quadro com o cartão encosta nos títulos das colunas
        d.rectangle((80, y, 1900, y + 90), outline="black", width=3)
        d.text((140, y + 30), f"{nome} - VISA SIGNATURE", fill="black", font=fonte)
        d.text((1480, y + 30), f"XXXX.XXXX.XXXX.{final}", fill="black", font=fonte)
        y += 105
        d.text((100, y), "Data   Histórico", fill="black", font=fonte)
        d.text((1000, y), "US$   Cotação US$   R$", fill="black", font=fonte)
        y += 110
        for data, desc, valor in linhas:
            d.text((120, y), data, fill="black", font=fonte)
            d.text((260, y), desc, fill="black", font=fonte)
            d.text((1150, y), "USD 0,00", fill="black", font=fonte)
            d.text((1450, y), "R$ 0,00", fill="black", font=fonte)
            d.text((1680, y), valor, fill="black", font=fonte)
            d.line((80, y + 70, 1900, y + 70), fill="gray", width=2)
            y += 120
        d.text((80, y), f"Total para: {nome}", fill="black", font=fonte)
        d.text((1680, y), total, fill="black", font=fonte)
        y += 140
    buf = io.BytesIO()
    img.save(buf, format="PDF")
    return buf.getvalue()


precisa_ocr = pytest.mark.skipif(not (bradesco.tem_ocr() and shutil.which("fc-match")), reason="sem tesseract/pdftoppm/fontes")


@precisa_ocr
def test_fatura_em_aberto_lida_por_ocr():
    lt = importadores.ler_arquivo("fatura.pdf", _fatura_pdf())
    assert lt.tipo == "fatura_bradesco_pdf"
    # data e valor exatos; a descrição vem do OCR e pode variar nos espaços
    assert [(m.data, m.valor, m.descricao.replace(" ", "")) for m in lt.movimentos] == [
        ("2026-10-22", -18.9, "PADARIAEXEMPLO"),
        ("2026-10-21", -127.45, "MERCADODOBAIRRO"),
        ("2026-10-18", -10.5, "IOFS/TRANSINTERREAIS"),
        ("2026-10-12", 300.0, "PAGTOANTECIPADOPIX"),
        ("2026-08-19", -59.9, "LOJAONLINE"),
        ("2026-10-14", -23.75, "APPDETRANSPORTE")]


@precisa_ocr
def test_cartao_novo_comeca_devendo_o_saldo_anterior(con):
    servicos.importar(con, "fatura.pdf", _fatura_pdf())
    c = con.execute("SELECT * FROM contas WHERE id='bradesco_cartao'").fetchone()
    assert (c["tipo"], c["saldo_inicial"], c["data_saldo_inicial"]) == ("cartao", -300.0, "2026-08-19")
    saldo = next(s for s in servicos.saldo_contas(con) if s["id"] == "bradesco_cartao")["saldo"]
    assert saldo == -240.5             # a dívida em aberto: a soma dos "Total para" (156,85 + 83,65)


@precisa_ocr
def test_fatura_que_nao_fecha_com_o_total_e_recusada():
    with pytest.raises(ValueError, match="não fecha no cartão final 1234"):
        importadores.ler_arquivo("fatura.pdf", _fatura_pdf(total_1="R$ 999,99"))
