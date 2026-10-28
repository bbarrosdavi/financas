"""Testes do parser de push (um por bug que já custou dado errado)."""

import pytest

from app.push_models import APPROVED, DECLINED, IGNORED, REFUND, UNPARSED
from app.push_parser import (
    auto_categorize,
    detect_bank,
    forcar_compra,
    parse_currency_ptbr,
    parse_notification,
)


# --------------------------------------------------------------------------
# Moeda
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "entrada,esperado",
    [("1.250,90", 1250.90), ("R$ 45,00", 45.00), ("0,50", 0.50), ("12.345,67", 12345.67)],
)
def test_moeda_ptbr(entrada, esperado):
    assert parse_currency_ptbr(entrada) == esperado


# --------------------------------------------------------------------------
# Categoria — o bug do "99" e do "Mercado Livre"
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "merchant,categoria",
    [
        ("Mcdonalds Comercio", "🍔 Alimentação"),
        ("Uber *Trip", "🚗 Transporte"),
        ("Supermercado Carrefour", "🍔 Alimentação"),
        ("Loja Desconhecida XYZ", "⚙️ Outros"),
        # Compras Online tem de vencer Mercado, senão "Mercado Livre" vira feira.
        ("Mercado Livre", "📦 Compras Online"),
        ("MercadoPago", "📦 Compras Online"),
        # Netflix não pode cair em Outros.
        ("NETFLIX.COM", "🎬 Entretenimento"),
    ],
)
def test_categoria(merchant, categoria):
    assert auto_categorize(merchant) == categoria


def test_numero_solto_nao_arrasta_para_transporte():
    """'99' casava dentro de qualquer nome e Transporte era testado antes de
    Saúde, então 'Drogaria 99' virava corrida de aplicativo."""
    assert auto_categorize("Drogaria 99") == "💊 Saúde"
    assert auto_categorize("Padaria 99") == "🍔 Alimentação"
    # E o app de corrida de verdade continua funcionando.
    assert auto_categorize("99app Tecnologia") == "🚗 Transporte"


def test_bk_so_como_palavra():
    assert auto_categorize("BK Shopping Centro") == "🍔 Alimentação"
    assert auto_categorize("Blackbird Studio") == "⚙️ Outros"


# --------------------------------------------------------------------------
# Banco
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "package,texto,banco",
    [
        ("com.nu.production", "", "Nubank"),
        ("br.com.itau", "", "Itaú"),
        ("com.c6bank.app", "", "C6 Bank"),
        ("com.qualquer.app", "compra no nubank", "Nubank"),
        ("com.desconhecido", "sem pista alguma", "Banco"),
    ],
)
def test_deteccao_de_banco(package, texto, banco):
    assert detect_bank(package, texto) == banco


# --------------------------------------------------------------------------
# Transações
# --------------------------------------------------------------------------
def test_nubank_aprovada():
    tx = parse_notification(
        "com.nu.production",
        "Nubank",
        "Compra de R$ 45,90 aprovada em Mercado Livre no cartão virtual",
    )
    assert (tx.bank, tx.amount, tx.merchant, tx.status) == (
        "Nubank", 45.90, "Mercado Livre", APPROVED,
    )
    assert tx.category == "📦 Compras Online"


def test_itau_aprovada_com_final_do_cartao():
    tx = parse_notification(
        "br.com.itau",
        "Itaú Cartões",
        "Compra aprovada R$ 120,00 no Cartão final 4321, em 26/07 14:30 no Mcdonalds.",
    )
    assert tx.amount == 120.00
    assert tx.merchant == "Mcdonalds"
    assert tx.card_last_4 == "4321"
    assert tx.category == "🍔 Alimentação"
    assert tx.status == APPROVED


def test_compra_recusada_nao_vira_aprovada():
    """O regex genérico casa 'R$ x em Y' dentro de 'não aprovada'. Se recusa
    não for testada primeiro, a compra negada infla o total do mês."""
    tx = parse_notification(
        "com.nu.production",
        "Nubank",
        "Compra de R$ 890,00 não aprovada em Loja Cara por limite insuficiente",
    )
    assert tx.status == DECLINED
    assert tx.amount == 890.00


@pytest.mark.parametrize(
    "texto",
    [
        "Compra negada de R$ 50,00 em Posto Shell",
        "Transação cancelada: R$ 30,00 no Assai",
        "Sua compra de R$ 12,00 não foi autorizada em Padaria Central",
    ],
)
def test_variantes_de_recusa(texto):
    assert parse_notification("com.nu.production", "Nubank", texto).status == DECLINED


def test_estorno_tem_status_proprio():
    tx = parse_notification(
        "com.nu.production", "Nubank", "Estorno de R$ 75,50 em Amazon recebido"
    )
    assert tx.status == REFUND
    assert tx.amount == 75.50


def test_compra_com_cashback_nao_e_marketing():
    """O filtro de marketing rodava antes do parsing e casava substring solta,
    então esta compra legítima era descartada como propaganda."""
    tx = parse_notification(
        "com.nu.production",
        "Nubank",
        "Compra de R$ 89,90 aprovada em Drogasil com cashback de R$ 2,00",
    )
    assert tx.status == APPROVED
    assert tx.amount == 89.90
    assert tx.category == "💊 Saúde"


def test_marketing_de_verdade_e_ignorado():
    tx = parse_notification(
        "com.nu.production", "Nubank", "Sua fatura fechada já está disponível"
    )
    assert tx.status == IGNORED


def test_parcelamento_e_extraido():
    """installments e monthly_installment existiam no modelo e na tabela, mas
    nenhum parser os preenchia: compra em 10x entrava com o valor cheio."""
    tx = parse_notification(
        "br.com.itau",
        "Itaú",
        "Compra aprovada R$ 1.200,00 em 10x de R$ 120,00 no Kabum.",
    )
    assert tx.installments == 10
    assert tx.monthly_installment == 120.00


def test_parcelamento_calcula_quando_nao_informado():
    tx = parse_notification(
        "com.nu.production", "Nubank", "Compra de R$ 300,00 aprovada em Loja em 3x"
    )
    assert tx.installments == 3
    assert tx.monthly_installment == 100.00


@pytest.mark.parametrize(
    "texto,metodo",
    [
        ("Compra de R$ 10,00 aprovada em Loja no débito", "Débito"),
        ("Pix de R$ 25,00 enviado para Fulano", "PIX"),
        ("Compra de R$ 10,00 aprovada em Loja", "Crédito"),
    ],
)
def test_metodo_de_pagamento(texto, metodo):
    assert parse_notification("com.nu.production", "Nubank", texto).payment_method == metodo


# --------------------------------------------------------------------------
# Ruído — o push do banco que não é compra
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "texto,motivo",
    [
        # O caso caro: o valor da fatura entrava no mês inteiro como gasto.
        ("Sua fatura de R$ 2.340,00 fechou. Vence em 05/08.", "fatura"),
        ("Fatura disponível: R$ 1.120,45", "fatura"),
        ("Pagamento da sua fatura de R$ 1.000,00 recebido", "fatura"),
        ("Lembrete de pagamento: boleto de R$ 89,00", "fatura"),
        # Dinheiro entrando virava despesa.
        ("Você recebeu um Pix de R$ 500,00 de Fulano", "entrada"),
        ("Pix de R$ 1.200,00 recebido", "entrada"),
        ("Transferência recebida: R$ 300,00", "entrada"),
        ("Seu salário caiu: R$ 4.500,00 na conta", "entrada"),
        ("Seus investimentos renderam R$ 12,30 hoje", "entrada"),
        # Informativo puro.
        ("Saldo disponível: R$ 812,45", "saldo"),
        ("Seu limite aumentou para R$ 3.000,00", "saldo"),
        ("Extrato do mês atualizado", "saldo"),
        ("Empréstimo pré-aprovado de R$ 10.000,00 para você", "marketing"),
        ("Promoção: R$ 50,00 de desconto especial no seu app", "marketing"),
        ("Código de verificação: 4821", "aviso"),
        ("Seu cartão foi bloqueado por segurança", "aviso"),
        ("Novo acesso detectado na sua conta", "aviso"),
    ],
)
def test_push_que_nao_e_compra_nao_vira_gasto(texto, motivo):
    """Sem esta camada, o padrão genérico 'R$ x' promovia todos estes a compra
    aprovada — e o total do mês virava ficção."""
    tx = parse_notification("com.nu.production", "Nubank", texto)
    assert tx.status == IGNORED, f"{texto!r} passou como {tx.status}"
    assert tx.amount == 0.0
    assert tx.motivo == motivo


def test_cartao_bloqueado_nao_e_compra_recusada():
    """`bloquead[ao]` está no regex de recusa. Sem exigir valor, todo aviso de
    segurança virava '🚫 Compra recusada de R$ 0,00' no Telegram."""
    tx = parse_notification("com.nu.production", "Nubank", "Seu cartão foi bloqueado")
    assert tx.status != DECLINED


@pytest.mark.parametrize(
    "texto",
    [
        # Ruído citado de passagem não pode derrubar a compra.
        "Compra de R$ 60,00 aprovada em Posto Shell. Aproveite: cashback em dobro!",
        "Compra aprovada R$ 30,00 no Mcdonalds — saldo disponível: R$ 200,00",
        "Compra de R$ 89,90 aprovada em Drogasil, parcelada na sua fatura",
        "Pix enviado: R$ 45,00 para Fulano",
    ],
)
def test_sinal_forte_de_compra_vence_o_ruido(texto):
    assert parse_notification("com.nu.production", "Nubank", texto).status == APPROVED


def test_sem_valor_e_sem_assunto_fica_unparsed():
    """Push de compra brasileiro sempre traz o valor. Sem valor e sem assunto
    reconhecido não é compra perdida — é ruído que ainda não tem rótulo."""
    tx = parse_notification("com.nu.production", "Nubank", "Boa tarde, tudo bem?")
    assert tx.status == UNPARSED
    assert tx.motivo == "sem_valor"


def test_forcar_compra_ignora_o_filtro():
    """O desfazer do /resgatar: se o filtro errou, o valor volta a ser compra."""
    tx = forcar_compra("com.nu.production", "Nubank", "Sua fatura de R$ 120,00 fechou")
    assert tx is not None
    assert (tx.status, tx.amount) == (APPROVED, 120.00)
    assert forcar_compra("com.nu.production", "Nubank", "sem valor nenhum") is None


def test_valor_absurdo_nao_passa():
    tx = parse_notification("com.x", "X", "Promoção R$ 99.999.999,00 em prêmios")
    assert tx.amount == 0.0
    assert tx.status != APPROVED


def test_sufixo_de_confirmacao_sai_do_estabelecimento():
    """'LANCHONETE EXEMPLO foi processado' virava o nome do estabelecimento."""
    tx = parse_notification(
        "com.nu.production", "Nubank", "Seu débito de R$ 45,00 em LANCHONETE EXEMPLO foi processado"
    )
    assert tx.merchant == "LANCHONETE EXEMPLO"
