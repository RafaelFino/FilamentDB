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

# ── Config centralizada (fonte única de verdade) ──
# Carrega config.env (se existir) sem sobrescrever o que já veio do ambiente.
# Garante que o backup respalde EXATAMENTE os mesmos arquivos que o serviço usa.
if [ -f "${REPO_DIR}/config.env" ]; then
    set -a
    # shellcheck disable=SC1091
    . "${REPO_DIR}/config.env"
    set +a
    log "Config carregada de ${REPO_DIR}/config.env"
fi

# ── Backup dos bancos antes de qualquer alteração ──
# Rede de segurança contra perda/corrupção de dados. O inventory.db (estoque
# mutável do usuário) NÃO é tocado pelo pipeline, mas fazemos backup mesmo
# assim para blindar contra mudanças futuras e falhas de disco. O filament.db
# é regenerável, mas incluímos para permitir rollback rápido do catálogo.
#
# Respeita os mesmos paths que o backend/build usam (env override + default).
FILAMENT_DB="${FILAMENT_DB_PATH:-${REPO_DIR}/filament.db}"
INVENTORY_DB="${FILAMENT_INVENTORY_DB_PATH:-${REPO_DIR}/inventory.db}"
BACKUP_DIR="${FILAMENTDB_BACKUP_DIR:-${REPO_DIR}/backups}"
MAX_DB_BACKUPS="${MAX_DB_BACKUPS:-30}"

backup_db() {
    # backup_db <caminho_do_banco> <rotulo>
    local src="$1" label="$2"
    [ -f "$src" ] || { log "Backup: ${label} ausente (${src}), pulando."; return 0; }
    local ts dest
    ts="$(date '+%Y%m%d_%H%M%S')"
    dest="${BACKUP_DIR}/${label}_${ts}.db"
    # sqlite3 .backup faz cópia consistente mesmo com o serviço ativo (respeita
    # o lock do WAL). Fallback para cp caso o binário sqlite3 não exista.
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
    # Rotação: mantém apenas os últimos MAX_DB_BACKUPS deste label.
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
# Inventário primeiro: é o dado insubstituível (estoque do usuário).
backup_db "$INVENTORY_DB" "inventory"
backup_db "$FILAMENT_DB"  "filament"

# ── Limpeza de artefatos de build antes do pull ──
# O build.py regenera filament.db (e os exports) a cada execução, sujando o
# working tree. Se esses artefatos estiverem rastreados/modificados, o git pull
# falha ("local changes would be overwritten"). Como são sempre regenerados,
# removemos com segurança antes do pull para garantir um fast-forward limpo.
log "Limpando artefatos de build (regenerados pelo build.py)..."
# Remove do índice se ainda estiver rastreado (ex.: db versionado em commits antigos)
git rm --cached --quiet filament.db 2>/dev/null || true
# Remove do disco os artefatos gerados que poderiam colidir no merge
rm -f filament.db 2>/dev/null || true
# Descarta qualquer modificação local em arquivos ainda rastreados que sejam
# puramente gerados (defensivo; não toca em fontes como *.yaml)
git checkout -- filament.db 2>/dev/null || true

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
# SEMPRE reconstrói o banco. Motivos:
#   1. filament.db não é versionado e foi removido na limpeza acima — precisa
#      ser regenerado a cada execução, mesmo sem commits novos.
#   2. Evita servir um banco ausente/defasado (causa de "no such table").
# O build.py aborta (exit != 0) se material-data faltar; nesse caso NÃO
# reiniciamos o serviço, deixando-o no estado anterior em vez de subir quebrado.
log "Executando build..."
if ! python3 build.py 2>&1 | sed 's/^/  /'; then
    err "build.py falhou. Serviço NÃO será reiniciado (mantém estado anterior)."
    exit 1
fi

# Validação: garante que o banco foi criado e tem a tabela principal antes de
# reiniciar. Barreira final contra subir o serviço com banco inválido.
if ! python3 -c "import sqlite3,sys; c=sqlite3.connect('${REPO_DIR}/filament.db'); \
    c.execute('SELECT 1 FROM filament_profiles LIMIT 1'); sys.exit(0)" 2>/dev/null; then
    err "filament.db inválido ou sem tabela filament_profiles após o build. Serviço NÃO reiniciado."
    exit 1
fi
log "Banco validado (filament_profiles presente)."

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

# ── Dump lógico do estoque (JSON via API) ──
# Complementa o backup binário do início: um export versionado e desacoplado
# do schema, restaurável via POST /api/inventory/import. Best-effort — roda
# após o serviço estar no ar. Se a API não responder, apenas avisa (o backup
# binário do inventory.db, feito lá no início, já garante a recuperação).
API_URL="${FILAMENTDB_API_URL:-http://localhost:5000}"
JSON_BACKUP_DIR="${BACKUP_DIR}/inventory-json"
MAX_JSON_BACKUPS="${MAX_JSON_BACKUPS:-30}"

if command -v curl >/dev/null 2>&1; then
    mkdir -p "$JSON_BACKUP_DIR"
    ts_json="$(date '+%Y%m%d_%H%M%S')"
    json_dest="${JSON_BACKUP_DIR}/inventory_${ts_json}.json"
    # --fail: status != 2xx vira erro; --max-time: não trava o cron se o serviço pendurar.
    if curl -fsS --max-time 15 "${API_URL}/api/inventory/export" -o "$json_dest" 2>/dev/null; then
        # Sanidade: precisa ser JSON com a chave "items", senão descarta.
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
    # Rotação dos dumps JSON.
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

log "Atualização concluída."
