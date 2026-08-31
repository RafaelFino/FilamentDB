#!/bin/bash
# update-server.sh — Atualiza o FilamentDB no servidor.
#
# Faz git pull, rebuild do banco e reinicia o serviço.
# Pensado para rodar via cron diariamente.

set -euo pipefail

REPO_DIR="/srv/FilamentDB"
SERVICE="filamentdb.service"
LOG_PREFIX="[$(date '+%Y-%m-%d %H:%M:%S')]"

log()  { echo "$LOG_PREFIX $*"; }
err()  { echo "$LOG_PREFIX ERROR: $*" >&2; }

if [ "$(id -u)" -ne 0 ]; then
    err "Este script precisa rodar como root. Use: sudo $0"
    exit 1
fi

cd "$REPO_DIR"

if [ -f "${REPO_DIR}/config.env" ]; then
    set -a
    # shellcheck disable=SC1091
    . "${REPO_DIR}/config.env"
    set +a
    log "Config carregada de ${REPO_DIR}/config.env"
else
    log "AVISO: ${REPO_DIR}/config.env não existe — usando defaults do código."
fi

case "${FILAMENTDB_AUTH_ENABLED:-0}" in
    1|true|yes|on|TRUE|YES|ON)
        if [ -z "${FILAMENTDB_WRITERS:-}" ]; then
            err "AUTH ligada mas FILAMENTDB_WRITERS vazia — NINGUÉM poderá escrever."
            err "  Preencha FILAMENTDB_WRITERS em ${REPO_DIR}/config.env."
        else
            log "Auth ligada; allowlist de writers presente."
        fi
        ;;
esac

# Paths canônicos: DB_PATH é a mesma variável usada por src/config.py.
# O banco principal é gerado por build.py em data/filament.db por padrão.
FILAMENT_DB="${DB_PATH:-${REPO_DIR}/data/filament.db}"
INVENTORY_DB="${FILAMENT_INVENTORY_DB_PATH:-${FILAMENT_DB%/*}/inventory.db}"
PRICE_HISTORY_DB="${FILAMENT_PRICE_HISTORY_DB_PATH:-${FILAMENT_DB%/*}/price-history.db}"
BACKUP_DIR="${FILAMENTDB_BACKUP_DIR:-${REPO_DIR}/backups}"
MAX_DB_BACKUPS="${MAX_DB_BACKUPS:-30}"

backup_db() {
    local src="$1" label="$2"
    [ -f "$src" ] || { log "Backup: ${label} ausente (${src}), pulando."; return 0; }
    local ts dest
    ts="$(date '+%Y%m%d_%H%M%S')"
    dest="${BACKUP_DIR}/${label}_${ts}.db"
    if command -v sqlite3 >/dev/null 2>&1; then
        if sqlite3 "$src" ".backup '${dest}'" 2>/dev/null; then
            log "Backup: ${label} → ${dest}"
        else
            err "Backup de ${label} FALHOU via sqlite3. Abortando para não arriscar os dados."
            exit 1
        fi
    else
        cp -p "$src" "$dest" || { err "Backup de ${label} (cp) FALHOU. Abortando."; exit 1; }
        log "Backup (cp): ${label} → ${dest}"
    fi
    local count
    count=$(find "$BACKUP_DIR" -maxdepth 1 -name "${label}_*.db" -type f 2>/dev/null | wc -l)
    if [ "$count" -gt "$MAX_DB_BACKUPS" ]; then
        find "$BACKUP_DIR" -maxdepth 1 -name "${label}_*.db" -type f -printf '%T+ %p\n' \
            | sort | head -n "$((count - MAX_DB_BACKUPS))" | cut -d' ' -f2- \
            | while read -r old; do rm -f "$old"; done
        log "Rotação ${label}: mantidos últimos ${MAX_DB_BACKUPS}."
    fi
}

log "Fazendo backup dos bancos..."
mkdir -p "$BACKUP_DIR"
backup_db "$INVENTORY_DB" "inventory"
backup_db "$FILAMENT_DB" "filament"
backup_db "$PRICE_HISTORY_DB" "price-history"

log "Limpando artefatos de build (regenerados pelo build.py)..."
git rm --cached --quiet filament.db 2>/dev/null || true
rm -f filament.db 2>/dev/null || true
git checkout -- filament.db 2>/dev/null || true

log "Verificando atualizações..."
BEFORE=$(git rev-parse HEAD)
git pull --ff-only origin main 2>&1 || { err "git pull falhou"; exit 1; }
AFTER=$(git rev-parse HEAD)

if [ "$BEFORE" = "$AFTER" ]; then
    log "Sem commits novos (HEAD: ${BEFORE:0:8})."
else
    log "Atualizado: ${BEFORE:0:8} → ${AFTER:0:8}"
    log "Commits novos:"
    git log --oneline "$BEFORE..$AFTER" | sed 's/^/  /'
fi

# Install/update the isolated public API unit from the repository.
# This makes a fresh server self-healing: `git pull` brings the unit and this
# script installs it before the API restart below.
API_SERVICE="filamentdb-api.service"
API_UNIT_SOURCE="${REPO_DIR}/systemd/${API_SERVICE}"
API_UNIT_TARGET="/etc/systemd/system/${API_SERVICE}"
if [ -f "$API_UNIT_SOURCE" ]; then
    install -m 0644 "$API_UNIT_SOURCE" "$API_UNIT_TARGET"
    systemctl daemon-reload
    systemctl enable "$API_SERVICE" >/dev/null
    log "Unit ${API_SERVICE} instalada/atualizada e habilitada."
else
    err "${API_UNIT_SOURCE} não encontrado após git pull. Serviço API NÃO será iniciado."
    exit 1
fi

log "Executando build..."
if ! python3 build.py 2>&1 | sed 's/^/  /'; then
    err "build.py falhou. Serviço NÃO será reiniciado."
    exit 1
fi

# Re-resolve DB_PATH after build/config and validate the exact canonical path.
FILAMENT_DB="${DB_PATH:-${REPO_DIR}/data/filament.db}"
if ! python3 -c "import sqlite3,sys; p='${FILAMENT_DB}'; c=sqlite3.connect(p); c.execute('SELECT 1 FROM filament_profiles LIMIT 1'); c.close(); sys.exit(0)" 2>/dev/null; then
    err "${FILAMENT_DB} inválido ou sem tabela filament_profiles após o build. Serviço NÃO reiniciado."
    exit 1
fi
log "Banco validado (${FILAMENT_DB}; filament_profiles presente)."

log "Importando snapshots de preços..."
if ! python3 scripts/import_price_data.py 2>&1 | sed 's/^/  /'; then
    err "import_price_data.py falhou. Serviço NÃO será reiniciado."
    exit 1
fi
log "Snapshots de preços importados e validados."

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

log "Reiniciando ${API_SERVICE}..."
systemctl restart "$API_SERVICE" 2>&1
sleep 2
if systemctl is-active --quiet "$API_SERVICE"; then
    log "${API_SERVICE} reiniciado com sucesso."
else
    err "${API_SERVICE} falhou ao reiniciar!"
    systemctl status "$API_SERVICE" --no-pager 2>&1 | sed 's/^/  /'
    exit 1
fi

# Validate the API locally before declaring the deployment successful.
API_LOCAL_URL="http://${FILAMENTDB_API_HOST:-127.0.0.1}:${FILAMENTDB_API_PORT:-5001}"
if ! curl -fsS --max-time 10 "${API_LOCAL_URL}/health" >/dev/null; then
    err "Health da ${API_SERVICE} falhou em ${API_LOCAL_URL}/health."
    systemctl status "$API_SERVICE" --no-pager 2>&1 | sed 's/^/  /'
    exit 1
fi
if ! curl -fsS --max-time 10 "${API_LOCAL_URL}/health/ready" >/dev/null; then
    err "Ready da ${API_SERVICE} falhou em ${API_LOCAL_URL}/health/ready."
    systemctl status "$API_SERVICE" --no-pager 2>&1 | sed 's/^/  /'
    exit 1
fi
log "API health e ready OK em ${API_LOCAL_URL}."

API_URL="${FILAMENTDB_API_URL:-http://localhost:5000}"
JSON_BACKUP_DIR="${BACKUP_DIR}/inventory-json"
MAX_JSON_BACKUPS="${MAX_JSON_BACKUPS:-30}"

if command -v curl >/dev/null 2>&1; then
    mkdir -p "$JSON_BACKUP_DIR"
    ts_json="$(date '+%Y%m%d_%H%M%S')"
    json_dest="${JSON_BACKUP_DIR}/inventory_${ts_json}.json"
    if curl -fsS --max-time 15 "${API_URL}/api/inventory/export" -o "$json_dest" 2>/dev/null; then
        if python3 -c "import json,sys; d=json.load(open('$json_dest')); sys.exit(0 if 'items' in d else 1)" 2>/dev/null; then
            log "Dump JSON do estoque → ${json_dest}"
        else
            err "Export JSON retornou conteúdo inesperado. Descartando ${json_dest}."
            rm -f "$json_dest"
        fi
    else
        rm -f "$json_dest" 2>/dev/null || true
        err "Export JSON do estoque falhou (API em ${API_URL} não respondeu). Backup binário do início permanece válido."
    fi
    json_count=$(find "$JSON_BACKUP_DIR" -maxdepth 1 -name "inventory_*.json" -type f 2>/dev/null | wc -l)
    if [ "$json_count" -gt "$MAX_JSON_BACKUPS" ]; then
        find "$JSON_BACKUP_DIR" -maxdepth 1 -name "inventory_*.json" -type f -printf '%T+ %p\n' \
            | sort | head -n "$((json_count - MAX_JSON_BACKUPS))" | cut -d' ' -f2- \
            | while read -r old; do rm -f "$old"; done
        log "Rotação dumps JSON: mantidos últimos ${MAX_JSON_BACKUPS}."
    fi
else
    err "curl ausente — dump JSON do estoque pulado (backup binário permanece válido)."
fi

BUILD_INFO_PATH="${FILAMENTDB_BUILD_INFO_PATH:-${REPO_DIR}/build-info.env}"
CURRENT_COMMIT="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
CURRENT_SUBJECT="$(git log -1 --pretty=%s 2>/dev/null | tr -d '\n' | tr '"' "'" || echo '')"
{
    echo "updated_at=$(date '+%Y-%m-%dT%H:%M:%S%z')"
    echo "commit=${CURRENT_COMMIT}"
    echo "commit_subject=${CURRENT_SUBJECT}"
} > "$BUILD_INFO_PATH"
log "build-info gravado em ${BUILD_INFO_PATH} (commit ${CURRENT_COMMIT})."
log "Atualização concluída."
