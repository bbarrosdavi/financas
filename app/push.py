"""Notificações do celular (MacroDroid) viram lançamentos.

A notificação é gravada na inbox antes de responder 202, a fila carrega só o
id, e o item só vira 'done' com o lançamento salvo. Pix e transferência
recebidos não são ruído, são entrada (reembolso de colega, ajuda dos pais), e
entram na conta.
"""

import asyncio
import hashlib
import re
from datetime import datetime

from app import avisos, db, servicos
from app.config import settings
from app.push_models import APPROVED, DECLINED, IGNORED, REFUND, UNPARSED
from app.push_parser import parse_currency_ptbr, parse_notification

fila: asyncio.Queue[int] = asyncio.Queue(maxsize=settings.QUEUE_MAXSIZE)

_ENTRADA = re.compile(
    r"(?:recebeu|recebid[oa])[^|]*?R\$\s*(?P<v>[\d.,]+)(?:\s+de\s+(?P<de>[^.|\n]+))?"
    r"|R\$\s*(?P<v2>[\d.,]+)[^|]{0,40}?\brecebid[oa]\b(?:\s+de\s+(?P<de2>[^.|\n]+))?",
    re.IGNORECASE)


def hash_push(package: str, title: str, text: str) -> str:
    return hashlib.sha256(f"{package}:{title}:{text}".encode()).hexdigest()


def receber(package: str, title: str, text: str, quando: datetime) -> tuple[str, int | None]:
    """Grava na inbox. Devolve ('duplicate', None) se o mesmo push chegou há pouco."""
    h = hash_push(package, title, text)
    with db.conectar() as con:
        dup = con.execute("SELECT id FROM inbox WHERE dedup_hash=? AND recebido_em >= datetime(?, ?)",
                          (h, quando.strftime("%Y-%m-%d %H:%M:%S"), f"-{settings.DEDUP_WINDOW_MINUTES} minutes")).fetchone()
        if dup:
            return "duplicate", None
        cur = con.execute("INSERT INTO inbox (dedup_hash, package, title, body, recebido_em) VALUES (?,?,?,?,?)",
                          (h, package, title, text, quando.strftime("%Y-%m-%d %H:%M:%S")))
        return "queued", cur.lastrowid


def processar(inbox_id: int) -> dict | None:
    with db.conectar() as con:
        row = con.execute("SELECT * FROM inbox WHERE id=?", (inbox_id,)).fetchone()
        if row is None or row["state"] == "done":
            return None
        data = row["recebido_em"][:10]
        parsed = parse_notification(row["package"], row["title"], row["body"])
        blob = f"{row['title']} | {row['body']}"
        lid = None
        if parsed.status in (IGNORED, UNPARSED) and parsed.motivo == "entrada":
            m = _ENTRADA.search(blob)
            if m:
                valor = parse_currency_ptbr(m["v"] or m["v2"])
                de = (m["de"] or m["de2"] or "").strip()
                lid = servicos.inserir(con, "nubank_conta", data, valor, "Transferência recebida (push)", de,
                                       origem="push", ref=f"inbox:{inbox_id}")
        elif parsed.status in (APPROVED, REFUND):
            conta = "nubank_cartao" if parsed.payment_method == "Crédito" else "nubank_conta"
            valor = parsed.amount if parsed.status == REFUND else -parsed.amount
            desc = parsed.merchant if parsed.status == APPROVED else f"Estorno de {parsed.merchant}"
            lid = servicos.inserir(con, conta, data, valor, desc, "", origem="push", ref=f"inbox:{inbox_id}",
                                   parcela=f"1/{parsed.installments}" if parsed.installments else None)
        if lid is None:
            con.execute("INSERT INTO ignorados (inbox_id, package, title, body, motivo) VALUES (?,?,?,?,?)",
                        (inbox_id, row["package"], row["title"], row["body"],
                         "recusada" if parsed.status == DECLINED else (parsed.motivo or "aviso")))
        con.execute("UPDATE inbox SET state='done' WHERE id=?", (inbox_id,))
        if lid is None:
            return None
        return next((l for l in servicos.lancamentos(con, limite=5) if l["id"] == lid), None)


async def worker() -> None:
    while True:
        inbox_id = await fila.get()
        try:
            lanc = await asyncio.to_thread(processar, inbox_id)
            if lanc and lanc["pendente"]:
                await asyncio.to_thread(avisos.pendente, lanc)
        except Exception as e:  # o worker não pode morrer; o erro fica na inbox
            with db.conectar() as con:
                con.execute("UPDATE inbox SET attempts=attempts+1, last_error=?, "
                            "state=CASE WHEN attempts+1>=? THEN 'dead' ELSE 'pending' END WHERE id=?",
                            (str(e)[:500], settings.MAX_ATTEMPTS, inbox_id))
        finally:
            fila.task_done()


def reenfileirar() -> int:
    with db.conectar() as con:
        ids = [r["id"] for r in con.execute("SELECT id FROM inbox WHERE state='pending' ORDER BY id")]
    for i in ids:
        fila.put_nowait(i)
    return len(ids)
