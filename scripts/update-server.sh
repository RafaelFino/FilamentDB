#!/bin/bash
# update-server.sh — Atualiza o FilamentDB no servidor.
# Faz git pull, rebuild do banco e reinicia o serviço.
# Pensado para rodar manualmente ou via cron/systemd timer.

set -u

# ── Configuração ──
REPO_DIR="/srv/FilamentDB"
SERVICE_NAME="filamentdb"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }
err() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: $*" >&2; }

cd "$REPO_DIR" || { err "Não foi possível entrar em ${REPO_DIR}."; exit 1; }

# Carrega configuração local, se existir.
if [ -f "${REPO_DIR}/config.env" ]; then
    # shellcheck disable=SC1091
    . "${REPO_DIR}/config.env"
    log "Config carregada de ${REPO_DIR}/config.env"
else
    log "AVISO: ${REPO_DIR}/config.env não existe — usando defaults do código."
fi

# ── Pré-condições ──
if [ ! -d .git ]; then
    err "${REPO_DIR} não parece ser um repositório Git."
    exit 1
fi

# ── Paths canônicos dos bancos ──
# O backend resolve DB_PATH para data/filament.db por padrão; respeitamos o
# mesmo override FILAMENT_DB_PATH quando configurado.
FILAMENT_DB="${FILAMENT_DB_PATH:-${REPO_DIR}/data/filament.db}"
INVENTORY_DB="${FILAMENT_INVENTORY_DB_PATH:-${REPO_DIR}/inventory.db}"
PRICE_HISTORY_DB="${FILAMENT_PRICE_HISTORY_DB_PATH:-${REPO_DIR}/data/price-history.db}"
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

# ── Limpeza de artefatos de build antes do pull ──
log "Limpando artefatos de build (regenerados pelo build.py)..."
git rm --cached --quiet filament.db data/filament.db 2>/dev/null || true
rm -f filament.db data/filament.db 2>/dev/null || true
git checkout -- filament.db data/filament.db 2>/dev/null || true

# ── Git pull ──
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

# ── Rebuild ──
log "Executando build..."
if ! python3 build.py 2>&1 | sed 's/^/  /'; then
    err "build.py falhou. Serviço NÃO será reiniciado (mantém estado anterior)."
    exit 1
fi

# Validação: usa exatamente o mesmo caminho resolvido pelo backend.
if ! python3 -c "import sqlite3,sys; c=sqlite3.connect('${FILAMENT_DB}'); c.execute('SELECT 1 FROM filament_profiles LIMIT 1'); sys.exit(0)" 2>/dev/null; then
    err "${FILAMENT_DB} inválido ou sem tabela filament_profiles após o build. Serviço NÃO reiniciado."
    exit 1
fi
log "Banco validado (filament_profiles presente em ${FILAMENT_DB})."

# ── Importação dos snapshots de preços ──
log "Importando snapshots de preços..."
if ! python3 scripts/import_price_data.py 2>&1 | sed 's/^/  /'; then
    err "import_price_data.py falhou. Serviço NÃO será reiniciado."
    exit 1
fi

# ── Reinício ──
log "Reiniciando serviço ${SERVICE_NAME}..."
if ! systemctl restart "$SERVICE_NAME"; then
    err "Falha ao reiniciar ${SERVICE_NAME}."
    exit 1
fi

log "Aguardando serviço..."
sleep 2

if ! systemctl is-active --quiet "$SERVICE_NAME"; then
    err "Serviço ${SERVICE_NAME} não ficou ativo."
    systemctl status "$SERVICE_NAME" --no-pager || true
    exit 1
fi

log "Serviço ${SERVICE_NAME} ativo."

# Health check opcional, se curl estiver disponível.
if command -v curl >/dev/null 2>&1; then
    PORT="${PORT:-5000}"
    if curl -fsS --max-time 10 "http://127.0.0.1:${PORT}/health/ready" >/dev/null; then
        log "Health check OK."
    else
        err "Health check falhou após reinício."
        exit 1
    fi
fi

# ── Registrar build-info ──
BUILD_INFO_PATH="${FILAMENTDB_BUILD_INFO_PATH:-${REPO_DIR}/build-info.env}"
cat > "$BUILD_INFO_PATH" <<EOF
BUILD_COMMIT=${AFTER}
BUILD_AT=$(date -Iseconds)
EOF
log "build-info gravado em ${BUILD_INFO_PATH} (commit ${AFTER})."
log "Atualização concluída com sucesso."
