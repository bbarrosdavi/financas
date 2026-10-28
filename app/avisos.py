"""Aviso de lançamento pendente.

Quem entrega o aviso (Telegram, ntfy, e-mail) roda no host, então o container não
o chama: deixa um arquivo na fila (diretório montado do host) e a unit
`financas-avisos.path` entrega pelo comando que você escolher (ver deploy/).
No máximo um aviso a cada 10 minutos, juntando o que chegou.
"""

import json
import time
from datetime import datetime, timedelta
from pathlib import Path

from app import db
from app.config import settings
from app.money import fmt_brl

INTERVALO = timedelta(minutes=10)


def pendente(lanc: dict) -> bool:
    fila = Path(settings.AVISOS_FILA)
    if not fila.is_dir():
        return False
    with db.conectar_real() as con:
        ultimo = db.parametro(con, "aviso_ultimo")
        agora = datetime.now()
        if ultimo and agora - datetime.fromisoformat(ultimo) < INTERVALO:
            return False
        n = con.execute(f"SELECT COUNT(*) FROM lancamentos l WHERE {db.PENDENTE_SQL}").fetchone()[0]
        db.definir_parametro(con, "aviso_ultimo", agora.isoformat(timespec="seconds"))
    nome = lanc["contraparte"] or lanc["descricao"]
    texto = (f"Gasto sem categoria: {fmt_brl(abs(lanc['valor']))} em {nome}. "
             f"{'Há ' + str(n) + ' pendentes. ' if n > 1 else ''}Classifique em {settings.URL_PUBLICA}/#pendentes")
    tmp = fila / f".{time.time_ns()}.json"
    tmp.write_text(json.dumps({"de": settings.AVISOS_REMETENTE, "texto": texto}, ensure_ascii=False))
    tmp.rename(fila / tmp.name[1:])        # rename atômico: a unit nunca lê arquivo pela metade
    return True
