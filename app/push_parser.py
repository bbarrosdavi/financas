"""Leitura de push de banco brasileiro.

Três regras de ouro, todas aprendidas em bug:

1. **Recusa e estorno vêm antes de aprovação.** O regex genérico casa
   "R$ 89,90 em Mercado Livre" com igual prazer dentro de "Compra NÃO
   aprovada". Testar aprovação primeiro fazia compra negada entrar como
   aprovada e inflar o total do mês.

2. **Ruído é decidido pelo assunto, não pela ausência de valor.** O banco manda
   muito mais coisa do que compra: fatura fechada, Pix recebido, saldo, limite
   novo, propaganda. Quase toda essas mensagens carregam um "R$ x" — e o padrão
   genérico as promovia a compra aprovada. "Sua fatura de R$ 2.340,00 fechou"
   entrava no mês como gasto de R$ 2.340; "Você recebeu um Pix de R$ 500,00"
   entrava como despesa. A conta do mês ficava ficção. Agora `classificar_ruido`
   roda **antes** da aprovação, e devolve o motivo.

3. **Sinal forte de compra vence o ruído.** É o outro lado do mesmo erro: um
   filtro de propaganda que rodava primeiro descartava "Compra de R$ 89,90
   aprovada em Drogasil com cashback" por causa do "cashback". Por isso o ruído
   só é considerado quando `_COMPRA_FORTE` não casa.

Entrada de dinheiro (Pix recebido, salário, rendimento) é ignorada de
propósito, não esquecida: o dossiê tira a renda da planilha, e somar crédito à
tabela de despesas é justamente o que tornava o total errado.

Todo casamento de palavra usa fronteira (\b). Sem isso "99" casava dentro de
"Drogaria 99" e, como Transporte era testado antes de Saúde, a farmácia virava
corrida de app.
"""

import re
from typing import Optional

from app.push_models import (
    APPROVED,
    DECLINED,
    IGNORED,
    REFUND,
    UNPARSED,
    ParsedTransaction,
)

# Acima disto é quase certamente erro de leitura, não compra.
TETO_SANIDADE = 1_000_000.0


def parse_currency_ptbr(amount_str: str) -> float:
    """'1.250,90' -> 1250.90. Aceita 'R$ ' na frente e '45' sem centavos."""
    limpo = amount_str.replace("R$", "").strip()
    limpo = limpo.replace(".", "").replace(",", ".")
    return float(limpo)


# --------------------------------------------------------------------------
# Categorias
# --------------------------------------------------------------------------
# A ordem decide o empate: "Mercado Livre" precisa cair em Compras Online antes
# de Mercado ver o "mercado".
_CATEGORIAS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("💊 Saúde", (
        r"drogasil", r"droga\s*raia", r"drogaria", r"pague\s*menos", r"panvel",
        r"farm[áa]cia", r"pharmacy", r"hospital", r"laborat[óo]rio", r"cl[íi]nica",
        r"unimed", r"odonto",
    )),
    ("📦 Compras Online", (
        r"mercado\s*livre", r"mercadolivre", r"mercado\s*pago", r"amazon",
        r"magalu", r"magazine\s*luiza", r"shopee", r"aliexpress", r"ali\s*express",
        r"kabum", r"americanas", r"shein", r"temu",
    )),
    ("🍔 Alimentação", (
        r"mc\s*donalds?", r"burger\s*king", r"\bbk\b", r"ifood", r"rappi",
        r"restaurante", r"pizzaria", r"outback", r"padaria", r"lanchonete",
        r"cafeteria", r"starbucks", r"subway", r"habibs", r"china\s*in\s*box",
        r"carrefour", r"p[ãa]o\s*de\s*a[çc][úu]car", r"extrabom", r"supermercado",
        r"hortifruti", r"atacad[ãa]o", r"assa[íi]", r"sams\s*club", r"big\s*bom",
        r"condor", r"muffato", r"angeloni", r"mercado", r"italo", r"market",
        r"mercadinho", r"emp[óo]rio", r"conveni[êe]ncia", r"feira",
    )),
    ("🚗 Transporte", (
        r"uber", r"99\s*(?:app|pop|taxi|pay)", r"cabify", r"shell", r"ipiranga",
        r"petrobras", r"posto", r"combust[íi]vel", r"estapar", r"estacionamento",
        r"ped[áa]gio", r"sem\s*parar", r"localiza", r"movida",
    )),
    ("🎬 Entretenimento", (
        r"netflix", r"spotify", r"steam", r"playstation", r"xbox", r"nintendo",
        r"cinema", r"cinemark", r"ingresso", r"disney", r"hbo", r"max\s*stream",
        r"crunchyroll", r"youtube\s*premium",
    )),
    ("💡 Contas & Serviços", (
        r"copel", r"sanepar", r"vivo", r"claro", r"\btim\b", r"oi\s*fibra",
        r"energia", r"internet", r"seguro", r"google\s*(?:one|storage)",
        r"icloud", r"microsoft", r"openai", r"anthropic",
    )),
)

_CATEGORIAS_COMPILADAS = tuple(
    (nome, re.compile("|".join(rf"\b(?:{p})\b" for p in padroes), re.IGNORECASE))
    for nome, padroes in _CATEGORIAS
)

PADRAO = "⚙️ Outros"

# Vocabulário fechado de categorias. O bot monta os botões de recategorização a
# partir daqui, e o importador da planilha mapeia para estes mesmos nomes — se
# as duas pontas divergirem, planejado e realizado nunca se encontram.
CATEGORIAS = tuple(nome for nome, _ in _CATEGORIAS) + (PADRAO,)


def auto_categorize(merchant: str) -> str:
    """Categoria pelo nome do estabelecimento, por palavra inteira."""
    for nome, rx in _CATEGORIAS_COMPILADAS:
        if rx.search(merchant):
            return nome
    return PADRAO


# --------------------------------------------------------------------------
# Banco
# --------------------------------------------------------------------------
# (nome, regex do pacote, regex do texto). O texto usa \b porque "bb" e "inter"
# casam dentro de palavra comum.
_BANCOS: tuple[tuple[str, str, str], ...] = (
    ("Nubank", r"com\.nu\.production|nubank", r"\bnubank\b|\bnu\s*bank\b"),
    ("Mercado Pago", r"com\.mercadopago|mercadopago", r"\bmercado\s*pago\b"),
    ("Itaú", r"com\.itau", r"\bita[uú]\b"),
    ("C6 Bank", r"com\.c6bank", r"\bc6\s*bank\b"),
    ("Bradesco", r"com\.bradesco", r"\bbradesco\b"),
    ("Santander", r"santander", r"\bsantander\b"),
    ("Banco do Brasil", r"\bbb\.|com\.bb\b", r"\bbanco\s+do\s+brasil\b|\bbb\b"),
    ("Inter", r"com\.(?:bancointer|inter)\b", r"\bbanco\s+inter\b|\binter\b"),
    ("Caixa", r"caixa", r"\bcaixa\s*(?:econ[ôo]mica)?\b"),
    ("PicPay", r"picpay", r"\bpicpay\b"),
)

_BANCOS_COMPILADOS = tuple(
    (nome, re.compile(pkg, re.IGNORECASE), re.compile(txt, re.IGNORECASE))
    for nome, pkg, txt in _BANCOS
)


def detect_bank(package: str, blob: str) -> str:
    """Pacote manda; o texto é desempate. 'Banco' quando nada bate."""
    for nome, rx_pkg, _ in _BANCOS_COMPILADOS:
        if rx_pkg.search(package):
            return nome
    for nome, _, rx_txt in _BANCOS_COMPILADOS:
        if rx_txt.search(blob):
            return nome
    return "Banco"


# --------------------------------------------------------------------------
# Natureza da notificação
# --------------------------------------------------------------------------
_RECUSA = re.compile(
    r"\b(?:"
    r"n[ãa]o\s+(?:foi\s+)?(?:aprovad|autorizad|reconhecid|conclu[íi]d)[ao]"
    r"|negad[ao]|recusad[ao]|reprovad[ao]|bloquead[ao]"
    r"|saldo\s+insuficiente|limite\s+insuficiente|sem\s+limite"
    r"|(?:compra|transa[çc][ãa]o|pagamento)\s+cancelad[ao]"
    r")\b",
    re.IGNORECASE,
)

_ESTORNO = re.compile(
    r"\b(?:estorn(?:o|ad[ao])|reembols(?:o|ad[ao])"
    r"|devolu[çc][ãa]o|cr[ée]dito\s+de\s+estorno)\b",
    re.IGNORECASE,
)

# Sinal inequívoco de transação no cartão. Enquanto isto casa, nenhum padrão de
# ruído tem voz — é o que impede "cashback", "promoção" ou "fatura" citados de
# passagem de engolirem uma compra de verdade.
_COMPRA_FORTE = re.compile(
    r"(?:"
    r"\bcompra\s+(?:de\s+)?R\$"
    r"|\bcompra\s+(?:aprovada|autorizada|realizada|efetuada|internacional)"
    r"|\bcompra\s+(?:em|no|na)\s+\w"
    r"|\btransa[çc][ãa]o\s+(?:aprovada|autorizada|de\s+R\$)"
    r"|\bpagamento\s+(?:aprovado|autorizado|realizado)"
    r"|\bvoc[êe]\s+(?:fez|realizou)\s+uma\s+compra"
    r"|\bgastou\s+R\$"
    r"|\bpix\s+(?:enviado|realizado|efetuado|conclu[íi]do)"
    r"|\bn[oa]\s+cart[ãa]o\s+(?:final|de\s+cr[ée]dito|de\s+d[ée]bito|virtual)"
    r")",
    re.IGNORECASE,
)

# Motivos de descarte, do mais específico ao mais genérico. A ordem só decide
# qual rótulo aparece no /ruido — todos levam ao mesmo IGNORED.
_RUIDO: tuple[tuple[str, str], ...] = (
    # Dinheiro entrando. Sem isto, cada Pix recebido virava despesa.
    ("entrada", (
        r"\b(?:voc[êe]|vc)\s+recebeu"
        r"|\brecebeu\s+(?:um|uma)\s+(?:pix|transfer[êe]ncia|dep[óo]sito|ted|doc)"
        # "Pix de R$ 500,00 recebido" — o verbo vem depois do valor, e cada
        # banco escolhe uma ordem diferente. O `[^|]` não deixa a busca cruzar
        # a barra que separa título de corpo.
        r"|\b(?:pix|transfer[êe]ncia|dep[óo]sito|ted|doc)\b[^|]{0,40}\brecebid[oa]\b"
        r"|\bdep[óo]sito\s+(?:identificado|em\s+conta)"
        r"|\b(?:entrou|caiu)\s+na\s+(?:sua\s+)?conta"
        r"|\bsal[áa]rio\s+(?:caiu|creditado|dispon[íi]vel)"
        r"|\brend(?:eu|eram|imentos?)\b|\bcr[ée]dito\s+em\s+conta"
        r"|\bcreditad[oa]\s+na\s+(?:sua\s+)?conta"
    )),
    # Fatura e cobrança. O pagamento da fatura é um `fixo` do orçamento — se
    # entrasse aqui como compra, seria contado duas vezes.
    ("fatura", (
        r"\bfatura\s+(?:fechada|fechou|dispon[íi]vel|paga|vence|venceu|em\s+aberto)"
        r"|\bsua\s+fatura\b|\bfechamento\s+da\s+fatura"
        r"|\bboleto\s+(?:dispon[íi]vel|gerado)"
        r"|\blembrete\s+de\s+pagamento"
        r"|\b(?:vence|venceu)\s+(?:hoje|amanh[ãa]|em\s+\d+)"
        r"|\bpagamento\s+agendado|\bd[ée]bito\s+autom[áa]tico\s+agendado"
    )),
    # Informativo de posição: não move dinheiro nenhum.
    ("saldo", (
        r"\bsaldo\s+(?:dispon[íi]vel|atual|em\s+conta|da\s+conta)|\bseu\s+saldo\b"
        r"|\bextrato\s+(?:dispon[íi]vel|do\s+m[êe]s|atualizado)"
        r"|\blimite\s+(?:dispon[íi]vel|liberado|aumentou|aumentado|pr[ée]-?aprovado)"
        r"|\bnovo\s+limite\b"
    )),
    ("marketing", (
        r"\bdesconto\s+especial|\bpromo[çc][ãa]o|\boferta\s+exclusiva"
        r"|\bempr[ée]stimo|\bconvide\s+(?:seus\s+)?amigos|\bindique\s+e\s+ganhe"
        r"|\baproveite|\bnovidade|\batualize\s+o\s+app|\bcupom"
        r"|\binvista\b|\bcaixinha\b|\b[úu]ltim[oa]s?\s+dias\b"
    )),
    # Operacional e segurança. Chega muito, e nunca é gasto.
    ("aviso", (
        r"\bc[óo]digo\s+de\s+(?:verifica[çc][ãa]o|seguran[çc]a)"
        r"|\bnovo\s+(?:acesso|login|dispositivo)"
        r"|\bsenha\s+(?:alterada|atualizada|cadastrada)"
        r"|\bchave\s+pix\s+(?:cadastrada|registrada|exclu[íi]da)"
        r"|\bcart[ãa]o\s+(?:foi\s+)?(?:desbloqueado|bloqueado|chegou|a\s+caminho|entregue)"
        r"|\batualiza[çc][ãa]o\s+de\s+cadastro|\btermos\s+de\s+uso"
    )),
)

_RUIDO_COMPILADO = tuple(
    (motivo, re.compile(padrao, re.IGNORECASE)) for motivo, padrao in _RUIDO
)

# Rótulo humano de cada motivo: é o que o /ruido mostra e o que fica gravado.
MOTIVOS: dict[str, str] = {
    "entrada": "💸 Entrada de dinheiro",
    "fatura": "🧾 Aviso de fatura",
    "saldo": "📊 Saldo, extrato ou limite",
    "marketing": "📣 Publicidade",
    "aviso": "🔔 Aviso operacional",
    "sem_valor": "❓ Sem valor no texto",
}


def classificar_ruido(blob: str) -> Optional[str]:
    """Motivo pelo qual o push não é compra, ou None se pode ser.

    Recebe o texto já em minúsculas (título + corpo). Não decide sozinho: quem
    chama tem de checar `_COMPRA_FORTE` antes — ver regra 3 do módulo.
    """
    for motivo, rx in _RUIDO_COMPILADO:
        if rx.search(blob):
            return motivo
    return None

_PIX = re.compile(r"\bpix\b", re.IGNORECASE)
_DEBITO = re.compile(r"\bd[ée]bito\b", re.IGNORECASE)
_CARTAO_FINAL = re.compile(r"\bfinal\s*(?:n[º°o]\s*)?(\d{4})\b", re.IGNORECASE)
_PARCELAS = re.compile(
    r"\b(?:em|parcelad[ao]\s+em)\s+(?P<n>\d{1,2})\s*x"
    r"(?:\s+de\s+R\$\s*(?P<valor>[\d.,]+))?",
    re.IGNORECASE,
)

# Ruído comum no fim do nome do estabelecimento.
_SUFIXO_LIXO = re.compile(
    r"\s*(?:"
    r"n[oa]\s+cart[ãa]o.*|no\s+d[ée]bito.*|no\s+cr[ée]dito.*"
    r"|em\s+\d{1,2}\s*x.*|[-–]\s*parcela.*|\bàs\b.*"
    r"|com\s+cashback.*|\bsaldo\s+dispon[íi]vel.*"
    r"|\bfoi\s+(?:processad|conclu[íi]d|aprovad|efetuad|realizad)[ao]\b.*"
    r")$",
    re.IGNORECASE,
)


def _limpa_merchant(bruto: str) -> str:
    nome = _SUFIXO_LIXO.sub("", bruto)
    nome = nome.strip(" .,;:-–\t\n")
    nome = re.sub(r"\s{2,}", " ", nome)
    return nome or "Desconhecido"


def _metodo(blob: str) -> str:
    if _PIX.search(blob):
        return "PIX"
    if _DEBITO.search(blob):
        return "Débito"
    return "Crédito"


def _parcelas(blob: str, total: float) -> tuple[Optional[int], Optional[float]]:
    m = _PARCELAS.search(blob)
    if not m:
        return None, None
    n = int(m.group("n"))
    if n < 2:
        return None, None
    if m.group("valor"):
        try:
            return n, parse_currency_ptbr(m.group("valor"))
        except ValueError:
            pass
    return n, round(total / n, 2)


# --------------------------------------------------------------------------
# Valor + estabelecimento
# --------------------------------------------------------------------------
# Ordem: específico do banco primeiro, genérico por último.
_PADROES_VALOR: tuple[re.Pattern, ...] = (
    # Nubank: "Compra de R$ 45,90 aprovada em Mercado Livre no cartão virtual"
    re.compile(
        r"compra\s+(?:de\s+)?R\$\s*(?P<amount>[\d.,]+)\s+"
        r"(?:aprovada\s+)?(?:em|no|na)\s+(?P<merchant>.+?)"
        r"(?=\s+n[oa]\s+cart[ãa]o|\.|$)",
        re.IGNORECASE,
    ),
    # Itaú: "Compra aprovada R$ 120,00 no Cartão final 1234, em 26/07 14:30 no Mcdonalds."
    re.compile(
        r"compra\s+aprovada\s+R\$\s*(?P<amount>[\d.,]+).*?"
        r"\bno\s+(?P<merchant>[^.,]+?)(?:\.|$)",
        re.IGNORECASE,
    ),
    # Mercado Pago: "Você pagou R$ 9,79 a ITALO SUPERMERCADOS"
    re.compile(
        r"(?:voc[eê]\s+)?pagou\s+R\$\s*(?P<amount>[\d.,]+)\s+(?:a|em|no|na)\s+(?P<merchant>[^.,;]+)",
        re.IGNORECASE,
    ),
    # Genérico: qualquer "R$ x em/no/na Estabelecimento".
    re.compile(
        r"R\$\s*(?P<amount>[\d.,]+)\s+(?:em|no|na)\s+(?P<merchant>[^.,;]+)",
        re.IGNORECASE,
    ),
    # Último recurso: só o valor, sem estabelecimento legível.
    re.compile(r"R\$\s*(?P<amount>[\d.,]+)", re.IGNORECASE),
)


def _extrai_valor_merchant(texto: str) -> Optional[tuple[float, str]]:
    for rx in _PADROES_VALOR:
        m = rx.search(texto)
        if not m:
            continue
        try:
            valor = parse_currency_ptbr(m.group("amount"))
        except ValueError:
            continue
        if valor <= 0 or valor > TETO_SANIDADE:
            continue
        try:
            bruto = m.group("merchant")
        except IndexError:
            bruto = ""
        return valor, _limpa_merchant(bruto) if bruto else "Não informado"
    return None


def _montar(
    bank: str, raw: str, blob: str, valor: float, merchant: str, status: str
) -> ParsedTransaction:
    parcelas, mensal = _parcelas(blob, valor)
    card = _CARTAO_FINAL.search(raw)
    return ParsedTransaction(
        bank=bank,
        amount=valor,
        merchant=merchant,
        card_last_4=card.group(1) if card else None,
        payment_method=_metodo(blob),
        category=auto_categorize(merchant),
        status=status,
        installments=parcelas,
        monthly_installment=mensal,
        raw_text=raw,
    )


def parse_notification(package: str, title: str, text: str) -> ParsedTransaction:
    raw = f"{title} | {text}"
    blob = raw.lower()
    bank = detect_bank(package, blob)

    def montar(valor: float, merchant: str, status: str) -> ParsedTransaction:
        return _montar(bank, raw, blob, valor, merchant, status)

    def ignorada(motivo: str) -> ParsedTransaction:
        return ParsedTransaction(
            bank=bank,
            amount=0.0,
            merchant=MOTIVOS.get(motivo, motivo),
            category="Ignorado",
            status=IGNORED,
            motivo=motivo,
            raw_text=raw,
        )

    achado = _extrai_valor_merchant(text) or _extrai_valor_merchant(raw)

    # 1. Recusa antes de tudo: senão o padrão genérico a promove a aprovada.
    #    Exige valor — "seu cartão foi bloqueado" casa `bloquead[ao]` e não é
    #    compra nenhuma; sem esta condição virava uma recusa de R$ 0,00 no
    #    Telegram a cada aviso de segurança.
    if achado and _RECUSA.search(blob):
        return montar(*achado, DECLINED)

    # 2. Estorno: entra com valor positivo e status próprio; o total subtrai.
    if achado and _ESTORNO.search(blob):
        return montar(*achado, REFUND)

    # 3. Ruído — antes da aprovação, porque quase todo aviso do banco carrega um
    #    "R$ x" que o padrão genérico promoveria a compra. Só vale quando não há
    #    sinal forte de transação.
    if not _COMPRA_FORTE.search(blob):
        if motivo := classificar_ruido(blob):
            return ignorada(motivo)

    # 4. Compra.
    if achado:
        return montar(*achado, APPROVED)

    # 5. Sem valor e sem assunto reconhecido. Push de compra brasileiro sempre
    #    traz o valor, então isto não é compra perdida — é ruído sem rótulo.
    #    Fica gravado como UNPARSED para virar regex depois, mas não alerta.
    return ParsedTransaction(
        bank=bank,
        amount=0.0,
        merchant="Pendente de Classificação",
        category=PADRAO,
        status=UNPARSED,
        motivo="sem_valor",
        raw_text=raw,
    )


def forcar_compra(package: str, title: str, text: str) -> Optional[ParsedTransaction]:
    """Relê um push descartado como compra, sem passar pelo filtro de ruído.

    É o desfazer do filtro: nenhuma regra que decide sozinha o que some pode
    ficar sem uma. Devolve None quando não há valor legível no texto — aí não é
    questão de classificação, é que não há compra a reconstruir.
    """
    raw = f"{title} | {text}"
    blob = raw.lower()
    achado = _extrai_valor_merchant(text) or _extrai_valor_merchant(raw)
    if not achado:
        return None
    return _montar(detect_bank(package, blob), raw, blob, *achado, APPROVED)
