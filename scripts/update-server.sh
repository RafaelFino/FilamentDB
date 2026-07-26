#!/bin/bash
#
# update-server.sh — Atualiza o FilamentDB no servidor.
#
# Faz git pull, rebuild do banco e reinicia o serviço.
# Pensado para rodar via cron diariamente.
#
# Uso:
#   /srv/FilamentDB/scripts/update-server.sh
#
# Cron (como root):
#   0 4 * * * /srv/FilamentDB/scripts/update-server.sh >> /var/log/filamentdb-update.log 2>&1
#

set -euo pipefail

REPO_DIR="/srv/FilamentDB"
SERVICE="filamentdb.service"
LOG_PREFIX="[$(date '+%Y-%m-%d %H:%M:%S')]"

log()  { echo "$LOG_PREFIX $*"; }
err()  { echo "$LOG_PREFIX ERROR: $*" >&2; }

cd "$REPO_DIR"

# ── Git pull ──
log "Verificando atualizações..."
BEFORE=$(git rev-parse HEAD)
git pull --ff-only origin main 2>&1 || { err "git pull falhou"; exit 1; }
AFTER=$(git rev-parse HEAD)

if [ "$BEFORE" = "$AFTER" ]; then
    log "Sem alterações (HEAD: ${BEFORE:0:8}). Nada a fazer."
    exit 0
fi

log "Atualizado: ${BEFORE:0:8} → ${AFTER:0:8}"
log "Commits novos:"
git log --oneline "$BEFORE..$AFTER" | sed 's/^/  /'

# ── Rebuild ──
log "Executando build..."
python3 build.py 2>&1 | sed 's/^/  /'

# ── Restart serviço ──
log "Reiniciando ${SERVICE}..."
systemctl restart "$SERVICE" 2>&1
sleep 2

if systemctl is-active --quiet "$SERVICE"; then
    log "Serviço reiniciado com sucesso."
else
    err "Serviço falhou ao reiniciar!"
    systemctl status "$SERVICE" --no-pager 2>&1 | sed 's/^/  /'
    exit 1
fi

log "Atualização concluída."
