"""Formatação de moeda pt-BR.

Estava copiada e colada em três arquivos, com o mesmo truque do separador
temporário. Uma implementação só.
"""

_SENTINELA = "\x00"


def fmt_brl(valor: float) -> str:
    """1234.5 -> 'R$ 1.234,50'. Negativo vira '-R$ 10,00'."""
    corpo = f"{abs(valor):,.2f}"
    corpo = corpo.replace(",", _SENTINELA).replace(".", ",").replace(_SENTINELA, ".")
    sinal = "-" if valor < 0 else ""
    return f"{sinal}R$ {corpo}"
