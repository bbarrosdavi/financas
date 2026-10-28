"""Leitura dos arquivos do Nubank (extrato e fatura, em PDF ou CSV) e a escolha do leitor de cada arquivo.
O Bradesco tem leitores próprios em app/bradesco.py.

Cada leitor devolve uma lista de movimentos crus (data, conta, valor com o sinal
da conta, descrição, contraparte, parcela) e, quando o arquivo traz, os totais
impressos pelo banco, que `conferir` compara com a soma lida. Um extrato que
não bate com o próprio total não entra: é sinal de linha perdida no PDF.
"""

import csv
import io
import re
import subprocess
from dataclasses import dataclass, field
from datetime import date

MESES = {"JAN": 1, "FEV": 2, "MAR": 3, "ABR": 4, "MAI": 5, "JUN": 6, "JUL": 7, "AGO": 8,
         "SET": 9, "OUT": 10, "NOV": 11, "DEZ": 12}


def numero(s: str) -> float:
    s = s.replace("R$", "").replace("−", "-").replace(" ", "").strip()
    if "," not in s and re.fullmatch(r"-?\d+\.\d{1,2}", s):
        return float(s)        # CSV da fatura do Nubank: ponto decimal (32.9, -1203.83); milhar sempre tem 3 dígitos
    return float(s.replace(".", "").replace(",", "."))


@dataclass
class Movimento:
    data: str
    conta: str
    valor: float
    descricao: str
    contraparte: str = ""
    parcela: str | None = None


@dataclass
class Leitura:
    tipo: str
    movimentos: list[Movimento] = field(default_factory=list)
    futuras: list[dict] = field(default_factory=list)   # parcelas que ainda vão cair
    totais: dict = field(default_factory=dict)
    avisos: list[str] = field(default_factory=list)

    def conferir(self) -> None:
        if self.tipo == "extrato_pdf" and self.totais:
            ent = round(sum(m.valor for m in self.movimentos if m.valor > 0), 2)
            sai = round(-sum(m.valor for m in self.movimentos if m.valor < 0), 2)
            if abs(ent - self.totais["entradas"]) > 0.005 or abs(sai - self.totais["saidas"]) > 0.005:
                raise ValueError(
                    f"Extrato não fecha: entradas lidas {ent} x banco {self.totais['entradas']}, "
                    f"saídas lidas {sai} x banco {self.totais['saidas']}")


def texto_pdf(conteudo: bytes) -> str:
    try:
        r = subprocess.run(["pdftotext", "-layout", "-", "-"], input=conteudo, capture_output=True, check=True)
    except FileNotFoundError:        # o app do celular não tem o poppler
        raise ValueError("Ler PDF precisa do poppler (pdftotext), que não existe aqui. Importe o CSV ou o Excel, "
                         "ou importe o PDF no computador.") from None
    return r.stdout.decode("utf-8", "replace")


# ---------------------------------------------------------------------------
# Extrato da conta (PDF)
# ---------------------------------------------------------------------------
_CABECALHO = re.compile(
    r"Tem alguma dúvida|metropolitanas|Caso a solução|disponíveis em|Extrato gerado|^\s{60,}[A-Za-zÀ-ÿ]+(?: [A-Za-zÀ-ÿ]+)+\s*$"
    r"|CPF •|^\s*\d{8}-\d\s*$|DE \w+ DE \d{4} a|VALORES EM R|Saldo |Rendimento|Total de entradas|Total de saídas"
    r"|O saldo líquido|Não nos resp|Asseguramos|Nu Financeira|Investimento|CNPJ|Movimentações|^R\$")


def ler_extrato_pdf(texto: str) -> Leitura:
    lt = Leitura("extrato_pdf")
    m = re.search(r"Total de entradas\s+\+([\d.,]+)", texto)
    n = re.search(r"Total de saídas\s+-([\d.,]+)", texto)
    if m and n:
        lt.totais = {"entradas": numero(m[1]), "saidas": numero(n[1])}
    data = sinal = None
    atual = None
    for linha in texto.splitlines():
        l = linha.rstrip().replace("\f", "")
        cab = re.match(r"^(\d\d) (\w{3}) (\d{4})\s+Total de (entradas|saídas)", l)
        if cab:
            data = f"{cab[3]}-{MESES[cab[2]]:02d}-{cab[1]}"
            sinal = 1 if cab[4] == "entradas" else -1
            atual = None
            continue
        tot = re.match(r"^\s+Total de (entradas|saídas)", l)
        if tot:
            sinal = 1 if tot[1] == "entradas" else -1
            atual = None
            continue
        if not l.strip() or data is None or _CABECALHO.search(l):
            continue
        mv = (re.match(r"^ {10,25}(\S.*?)\s{2,}(.*?)\s{2,}([\d.]+,\d\d)\s*$", l)
              or re.match(r"^ {10,25}(\S.*?)()\s{2,}([\d.]+,\d\d)\s*$", l))
        if mv:
            atual = Movimento(data, "nubank_conta", sinal * numero(mv[3]), mv[1].strip(), mv[2].strip())
            lt.movimentos.append(atual)
            continue
        if atual is not None:
            partes = re.split(r"\s{2,}", l.strip())
            if len(l) - len(l.lstrip()) > 40:
                atual.contraparte = (atual.contraparte + " " + l.strip()).strip()
            else:
                atual.descricao += " " + partes[0]
                if len(partes) > 1:
                    atual.contraparte = (atual.contraparte + " " + " ".join(partes[1:])).strip()
    for mv in lt.movimentos:
        mv.contraparte = re.sub(r"\s*\(Transferência\s*enviada\)", "", mv.contraparte).strip()
        # Tira CPF mascarado, CNPJ e dados bancários: sobra o nome.
        mv.contraparte = re.sub(r"\s+-\s+(?:•••|\d{2}\.\d{3}\.\d{3}/|\d{2}\.\d{3}\.\d{3}\s).*$", "", mv.contraparte).strip()
    lt.conferir()
    return lt


# ---------------------------------------------------------------------------
# Fatura do cartão (PDF)
# ---------------------------------------------------------------------------
def ler_fatura_pdf(texto: str) -> Leitura:
    lt = Leitura("fatura_pdf")
    v = re.search(r"Data de vencimento: (\d\d) (\w{3}) (\d{4})", texto)
    if not v:
        raise ValueError("Não parece uma fatura do Nubank (sem data de vencimento).")
    venc_ano, venc_mes = int(v[3]), MESES[v[2]]
    total = re.search(r"no valor de\s*\nR\$ ([\d.,]+)", texto)
    if total:
        lt.totais["total"] = numero(total[1])
    lt.totais["vencimento"] = f"{venc_ano}-{venc_mes:02d}-{v[1]}"
    dentro = False
    for l in texto.splitlines():
        if "TRANSAÇÕES" in l:
            dentro = True
            continue
        if not dentro:
            continue
        m = re.match(r"^\s+(\d\d) (\w{3})\s+(?:•••• (\d{4})\s+)?(.*?)\s{2,}([−-]?)R\$ ([\d.,]+)\s*$", l)
        if not m:
            continue
        mes = MESES[m[2]]
        ano = venc_ano - 1 if mes > venc_mes else venc_ano
        desc = m[4].strip()
        valor = numero(m[6])
        if desc.startswith(("Saldo restante", "Juros de dívida encerrada", "Encerramento de dívida")) and valor == 0:
            continue
        # Na fatura, compra é dívida: sinal negativo na conta do cartão.
        sinal = 1 if m[5] else -1
        if desc.startswith("Pagamento em"):
            sinal = 1
        parc = re.search(r"Parcela (\d+/\d+)", desc)
        lt.movimentos.append(Movimento(f"{ano}-{mes:02d}-{m[1]}", "nubank_cartao", sinal * valor, desc,
                                       parcela=parc[1] if parc else None))
    return lt


# ---------------------------------------------------------------------------
# Fatura do cartão (CSV exportado pelo app: date,title,amount)
# ---------------------------------------------------------------------------
def ler_fatura_csv(conteudo: str, hoje: date | None = None) -> Leitura:
    hoje = hoje or date.today()
    lt = Leitura("fatura_csv")
    linhas = list(csv.DictReader(io.StringIO(conteudo)))
    if not linhas or not {"date", "title", "amount"} <= set(linhas[0]):
        raise ValueError("CSV de fatura esperado com colunas date,title,amount.")
    for r in linhas:
        titulo, valor = r["title"].strip(), numero(r["amount"])
        if titulo.startswith("Valor pendente do mês anterior"):
            lt.avisos.append(f"Fatura com saldo no rotativo: {r['amount']}")
            continue
        parc = re.search(r"Parcela (\d+/\d+)|(\d+/\d+)$", titulo)
        parcela = (parc[1] or parc[2]) if parc else None
        if date.fromisoformat(r["date"]) > hoje:
            lt.futuras.append({"conta": "nubank_cartao", "mes": r["date"][:7], "descricao": titulo,
                               "valor": -valor, "parcela": parcela})
            continue
        # No CSV, compra vem positiva e pagamento/estorno negativo.
        lt.movimentos.append(Movimento(r["date"], "nubank_cartao", -valor, titulo, parcela=parcela))
    return lt


# ---------------------------------------------------------------------------
# Extrato da conta (CSV exportado pelo app: Data,Valor,Identificador,Descrição)
# ---------------------------------------------------------------------------
def ler_extrato_csv(conteudo: str) -> Leitura:
    lt = Leitura("extrato_csv")
    for r in csv.DictReader(io.StringIO(conteudo)):
        d, mth, a = r["Data"].split("/")
        desc = r["Descrição"].strip()
        partes = desc.split(" - ", 1)
        lt.movimentos.append(Movimento(f"{a}-{mth}-{d}", "nubank_conta", float(r["Valor"]), partes[0],
                                       partes[1] if len(partes) > 1 else ""))
    return lt


def ler_arquivo(nome: str, conteudo: bytes, hoje: date | None = None) -> Leitura:
    """Descobre o tipo pelo conteúdo, não pelo nome."""
    from app import bradesco
    if conteudo[:5] == b"%PDF-":
        texto = texto_pdf(conteudo)
        if "Data de vencimento" in texto:
            return ler_fatura_pdf(texto)
        if "Total de entradas" in texto:
            return ler_extrato_pdf(texto)
        if bradesco.eh_extrato_pdf(texto):
            return bradesco.ler_extrato_pdf(texto)
        if not texto.strip():           # PDF só de imagem: a fatura em aberto do aplicativo Bradesco
            return bradesco.ler_fatura_pdf(conteudo, hoje)
        raise ValueError("PDF não reconhecido como extrato ou fatura do Nubank ou do Bradesco.")
    if conteudo[:2] == b"PK":           # Excel (.xlsx)
        linhas = bradesco.linhas_xlsx(conteudo)
        if bradesco.eh_extrato_tabela(linhas):
            return bradesco.ler_extrato_tabela(linhas, "extrato_bradesco_xlsx")
        raise ValueError(f"{nome}: planilha não reconhecida como extrato do Bradesco.")
    texto = conteudo.decode("utf-8-sig", "replace")
    cab = texto.splitlines()[0] if texto else ""
    if cab.startswith("date,title,amount"):
        return ler_fatura_csv(texto, hoje)
    if cab.startswith("Data,Valor,Identificador"):
        return ler_extrato_csv(texto)
    if cab.startswith("Extrato de:"):
        return bradesco.ler_extrato_tabela(bradesco.linhas_csv(texto), "extrato_bradesco_csv")
    raise ValueError(f"{nome}: formato não reconhecido.")
