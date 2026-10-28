"""Modelos e vocabulário de status."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from datetime import datetime as _dt
now = _dt.now

# Status possíveis de uma notificação já interpretada.
APPROVED = "APPROVED"  # compra que entra no total
DECLINED = "DECLINED"  # recusada/negada: registra, não soma
REFUND = "REFUND"      # estorno: subtrai do total
IGNORED = "IGNORED"    # marketing, aviso de fatura
UNPARSED = "UNPARSED"  # não deu para ler valor/estabelecimento

SOMAM = (APPROVED, REFUND)


class NotificationPayload(BaseModel):
    package: str = Field(..., max_length=200, description="Pacote Android de origem")
    title: str = Field(..., max_length=500)
    text: str = Field(..., max_length=4000)
    timestamp: Optional[int] = Field(
        default=None, description="Epoch ms do celular; ausente = hora do servidor"
    )


class ParsedTransaction(BaseModel):
    bank: str
    amount: float
    merchant: str
    card_last_4: Optional[str] = None
    payment_method: str = "Crédito"
    category: str = "⚙️ Outros"
    status: str = APPROVED
    installments: Optional[int] = None
    monthly_installment: Optional[float] = None
    # Por que o push não é compra ('entrada', 'fatura', 'marketing', …). Só é
    # preenchido em IGNORED/UNPARSED; não vai para `transactions`, vai para
    # `ignorados`, que é o que o /ruido lê.
    motivo: Optional[str] = None
    raw_text: str


class TransactionRecord(ParsedTransaction):
    id: Optional[int] = None
    inbox_id: Optional[int] = None
    dedup_hash: str
    created_at: datetime = Field(default_factory=now)


class CallbackPayload(BaseModel):
    transaction_id: int
    category: str = Field(..., min_length=1, max_length=60)
    user_action: Optional[str] = None
