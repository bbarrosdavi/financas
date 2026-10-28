#!/bin/sh
# Entrega os avisos que o container deixou na fila (chamado pela financas-avisos.path).
# AVISAR é o comando que manda o aviso (Telegram, ntfy, e-mail...) e recebe o remetente e o texto como
# argumentos; defina na unit. Sem ele, o aviso vai para o journal (logger).
# Aviso que falha vai para avisos-falhos: deixá-lo na fila faria a unit disparar em laço.
FILA="$HOME/.local/state/financas/avisos"
FALHOS="$HOME/.local/state/financas/avisos-falhos"
mkdir -p "$FALHOS"
for f in "$FILA"/*.json; do
  [ -e "$f" ] || continue
  de=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["de"])' "$f")
  texto=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["texto"])' "$f")
  if [ -n "$AVISAR" ]; then
    "$AVISAR" "$de" "$texto" && ok=1 || ok=0
  else
    logger -t "$de" "$texto" && ok=1 || ok=0
  fi
  if [ "$ok" = 1 ]; then rm -f "$f"; else mv "$f" "$FALHOS/"; fi
done
