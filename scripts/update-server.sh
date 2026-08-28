#!/bin/bash
#
# update-server.sh — Atualiza o FilamentDB no servidor.
#
# Faz git pull, rebuild do banco e reinicia o serviço.
# Pensado para rodar via cron diariamente.
#
# Pipeline de dados (fonte de verdade → banco servido):
#   filament-data/*.yaml      → perfis de filamento (por marca)
#   material-data/materials.yaml → propriedades dos materiais (por polímero) + confidence base
#   process-base/                → herança dos perfis de processo
#         └── build.py gera filament.db a partir desses YAMLs/JSONs
#
# IMPORTANTE: material-data/ e filament-data/ PRECISAM estar versionados no git.
# Se material-data/materials.yaml faltar, o build.py ABORTA de propósito (não cai
# em defaults silenciosos), impedindo que o serviço reinicie com dados corrompidos.
# O filament.db NÃO é versionado — é sempre regenerado aqui pelo build.py.
#
# IMPORTANTE: Este script precisa rodar como root (ou com sudo) porque:
#   - systemctl restart requer privilégio de root
#   - o serviço filamentdb.service é gerenciado pelo systemd
#
# Instalação no cron (como root):
#   sudo crontab -e
#   0 4 * * * /srv/FilamentDB/scripts/update-server.sh >> /var/log/filamentdb-update.log 2>&1
#
# Execução manual:
#   sudo /srv/FilamentDB/scripts/update-server.sh
#

set -euo pipefail

REPO_DIR="/srv/FilamentDB"
SERVICE="filamentdb.service"
LOG_PREFIX="[$(date '+%Y-%m-%d %H:%M:%S')]"

log()  { echo "$LOG_PREFIX $*"; }
err()  { echo "$LOG_PREFIX ERROR: $*" >&2; }

# Verificar privilégio de root
if [ "$(id -u)" -ne 0 ]; then
    err "Este script precisa rodar como root. Use: sudo $0"
    exit 1
fi

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
