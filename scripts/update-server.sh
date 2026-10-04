#!/bin/bash
# update-server.sh — Atualiza o FilamentDB no servidor.
#
# Faz git pull, rebuild do banco e reinicia o serviço.
# Pensado para rodar via cron diariamente.

set -euo pipefail

# Deploy roda em cron/root, sem terminal interativo. Impede que qualquer git que
# precise de credencial (ex.: remote virou privado/SSH sem chave) fique pendurado
# esperando input — falha na hora com erro claro em vez de travar o cron.
export GIT_TERMINAL_PROMPT=0
export GIT_SSH_COMMAND="ssh -oBatchMode=yes"

REPO_DIR="/srv/FilamentDB"
SERVICE="filamentdb.service"
# Usuário/grupo dono do projeto e sob o qual AMBOS os serviços rodam. Precisa
# bater com User=/Group= das units systemd. Configurável via config.env para
# não fixar no código; default = fino.
RUN_USER="${FILAMENTDB_RUN_USER:-fino}"
RUN_GROUP="${FILAMENTDB_RUN_GROUP:-$RUN_USER}"
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

# Re-resolve após carregar config.env (pode definir FILAMENTDB_RUN_USER).
RUN_USER="${FILAMENTDB_RUN_USER:-fino}"
RUN_GROUP="${FILAMENTDB_RUN_GROUP:-$RUN_USER}"

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
WORKTREE_BACKUP_DIR="${BACKUP_DIR}/worktree"
MAX_WORKTREE_BACKUPS="${MAX_WORKTREE_BACKUPS:-20}"
# Dump JSON lógico do estoque (dado vivo e insubstituível) ANTES de qualquer
# alteração do deploy. Diferente do dump via API no fim (estado pós-deploy),
# este captura o ponto exato pré-deploy e via Python direto — robusto mesmo se
# a API estiver fora. Nome com data-hora-segundos para restaurar o ponto exato.
INVENTORY_JSON_PRE_DIR="${BACKUP_DIR}/inventory-json-pre"
MAX_INVENTORY_JSON_PRE="${MAX_INVENTORY_JSON_PRE:-20}"

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

# Snapshot da working tree ANTES de qualquer descarte (git checkout/clean no
# deploy). Rede de segurança: se a limpeza algum dia remover algo que importava
# (ex.: inventory.db e data/price-history.db são TRACKED — o estoque é o dado
# mais precioso), este zip preserva o estado exato de antes.
#
# Cuidados pedidos:
#   - só o que o git RASTREIA (git ls-files): nada de .venv/, caches, nem o
#     próprio backups/ — o que também evita o zip-dentro-do-zip recursivo, já
#     que backups/ não é tracked;
#   - inclui os bancos tracked (inventory.db, data/price-history.db) — o dado
#     precioso entra na rede de segurança;
#   - rotação dos últimos MAX_WORKTREE_BACKUPS (default 20) para não lotar disco.
snapshot_tracked_worktree() {
    if ! command -v zip >/dev/null 2>&1; then
        err "zip ausente — snapshot da working tree PULADO (backup dos bancos permanece válido)."
        return 0
    fi
    mkdir -p "$WORKTREE_BACKUP_DIR"
    local ts dest
    ts="$(date '+%Y%m%d_%H%M%S')"
    dest="${WORKTREE_BACKUP_DIR}/worktree_${ts}.zip"
    # git ls-files: um arquivo rastreado por linha. `zip -@` lê essa lista do
    # stdin (uma entrada por linha) — lida corretamente com espaços nos nomes
    # dos perfis (ex.: "...Standard @Creality K2 0.4 nozzle - PLA.json"); só
    # falharia com newline literal no nome, que não ocorre neste repo.
    if git ls-files | zip -q "$dest" -@ 2>/dev/null; then
        local size
        size=$(du -h "$dest" 2>/dev/null | cut -f1)
        log "Snapshot da working tree (tracked) → ${dest} (${size})"
    else
        rm -f "$dest" 2>/dev/null || true
        err "Snapshot da working tree FALHOU. Abortando antes de descartar qualquer coisa."
        exit 1
    fi
    local count
    count=$(find "$WORKTREE_BACKUP_DIR" -maxdepth 1 -name "worktree_*.zip" -type f 2>/dev/null | wc -l)
    if [ "$count" -gt "$MAX_WORKTREE_BACKUPS" ]; then
        find "$WORKTREE_BACKUP_DIR" -maxdepth 1 -name "worktree_*.zip" -type f -printf '%T+ %p\n' \
            | sort | head -n "$((count - MAX_WORKTREE_BACKUPS))" | cut -d' ' -f2- \
            | while read -r old; do rm -f "$old"; done
        log "Rotação worktree: mantidos últimos ${MAX_WORKTREE_BACKUPS}."
    fi
}

# Dump JSON lógico do ESTOQUE (dado vivo) antes de qualquer alteração do deploy.
# Usa inventory.export_data() direto (sem HTTP) — lê o inventory.db atual e
# gera o mesmo envelope versionado de GET /api/inventory/export, restaurável
# via POST /api/inventory/import ou scripts/restore_inventory.sh.
#
# Executa ANTES do git pull/build: captura o estado exato pré-deploy. O backup
# binário (.db via sqlite3) e o dump via API no fim continuam existindo; este é
# a camada lógica, legível e diffável, do ponto de partida.
snapshot_inventory_json() {
    mkdir -p "$INVENTORY_JSON_PRE_DIR"
    local ts dest
    ts="$(date '+%Y%m%d_%H%M%S')"
    dest="${INVENTORY_JSON_PRE_DIR}/inventory_${ts}.json"
    # Gera e valida num passo só: o Python escreve o envelope e falha (exit!=0)
    # se export_data() quebrar ou o resultado não tiver 'items'.
    #
    # Preferimos rodar como ${RUN_USER} (mesmo dono dos serviços e do
    # inventory.db) para não criar artefato root. Se nem runuser nem sudo
    # existirem, rodamos direto (o deploy já é root) e o chown -R posterior
    # normaliza o dono — então nunca deixamos de gerar o dump por falta da
    # ferramenta de troca de usuário.
    local -a RUN_AS
    if command -v runuser >/dev/null 2>&1; then
        RUN_AS=(runuser -u "$RUN_USER" --)
    elif command -v sudo >/dev/null 2>&1; then
        RUN_AS=(sudo -u "$RUN_USER")
    else
        RUN_AS=()
    fi
    if "${RUN_AS[@]}" python3 - "$dest" <<'PY' 2>/dev/null
import json, sys
sys.path.insert(0, ".")
from src import inventory
data = inventory.export_data()
if "items" not in data:
    sys.exit("export_data sem 'items'")
with open(sys.argv[1], "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
PY
    then
        local n size
        n=$(python3 -c "import json;print(json.load(open('$dest')).get('count','?'))" 2>/dev/null || echo '?')
        size=$(du -h "$dest" 2>/dev/null | cut -f1)
        log "Dump JSON do estoque (pré-deploy) → ${dest} (${n} itens, ${size})"
    else
        rm -f "$dest" 2>/dev/null || true
        # Não aborta o deploy: o backup binário do inventory.db (via sqlite3,
        # feito logo abaixo) é a garantia primária. Este dump é camada extra.
        err "Dump JSON do estoque (pré-deploy) FALHOU — seguindo com backup binário do inventory.db."
    fi
    local count
    count=$(find "$INVENTORY_JSON_PRE_DIR" -maxdepth 1 -name "inventory_*.json" -type f 2>/dev/null | wc -l)
    if [ "$count" -gt "$MAX_INVENTORY_JSON_PRE" ]; then
        find "$INVENTORY_JSON_PRE_DIR" -maxdepth 1 -name "inventory_*.json" -type f -printf '%T+ %p\n' \
            | sort | head -n "$((count - MAX_INVENTORY_JSON_PRE))" | cut -d' ' -f2- \
            | while read -r old; do rm -f "$old"; done
        log "Rotação dump JSON estoque (pré): mantidos últimos ${MAX_INVENTORY_JSON_PRE}."
    fi
}

mkdir -p "$BACKUP_DIR"

log "Dump JSON lógico do estoque (dado vivo) — primeiro, antes de tudo..."
snapshot_inventory_json

log "Fazendo backup dos bancos..."
backup_db "$INVENTORY_DB" "inventory"
backup_db "$FILAMENT_DB" "filament"
backup_db "$PRICE_HISTORY_DB" "price-history"

log "Snapshot da working tree (arquivos tracked) antes de qualquer descarte..."
snapshot_tracked_worktree

log "Limpando artefatos de build (regenerados pelo build.py)..."
git rm --cached --quiet filament.db 2>/dev/null || true
rm -f filament.db 2>/dev/null || true
git checkout -- filament.db 2>/dev/null || true

# Artefatos de export (Creality-Print/, OrcaSlicer/) são versionados mas o
# build.py os reescreve a cada execução — em especial os .info, cujos campos
# setting_id/updated_time carregam o timestamp do build. No server, isso deixa
# a árvore "suja" nesses arquivos e fazia o `git pull --ff-only` abortar com
# "local changes would be overwritten". Como esses artefatos são 100%
# regeneráveis pelo build logo abaixo, descartamos as modificações locais DELES
# (cirurgicamente, só os paths de export rastreados) antes do pull.
#
# Deliberadamente NÃO usamos `git reset --hard` global aqui: isso apagaria
# qualquer mudança local, inclusive em código/config que não deveria sumir num
# deploy automático. O checkout restrito aos diretórios de export resolve o
# bloqueio real sem esse risco.
EXPORT_PATHS=(Creality-Print OrcaSlicer)
dirty_exports=$(git status --porcelain -- "${EXPORT_PATHS[@]}" 2>/dev/null | wc -l)
if [ "$dirty_exports" -gt 0 ]; then
    log "Descartando ${dirty_exports} artefato(s) de export modificado(s) localmente (regeneráveis)..."
    # Restaura os rastreados ao estado do commit (resolve o conflito do pull)...
    git checkout -- "${EXPORT_PATHS[@]}" 2>/dev/null || true
    # ...e remove export não rastreado (ex.: subpastas de device antigas) para
    # não acumular lixo que o build atual não geraria mais.
    git clean -fdq -- "${EXPORT_PATHS[@]}" 2>/dev/null || true
fi

log "Verificando atualizações..."
BEFORE=$(git rev-parse HEAD)
# Em caso de bloqueio inesperado por artefatos de export (ex.: um .info que
# escapou da limpeza acima), tenta uma segunda vez após re-restaurar os paths
# de export — mantendo a limpeza cirúrgica, sem reset --hard global.
if ! git pull --ff-only origin main 2>&1; then
    warn "git pull falhou na 1a tentativa; re-limpando artefatos de export e repetindo..."
    git checkout -- "${EXPORT_PATHS[@]}" 2>/dev/null || true
    git clean -fdq -- "${EXPORT_PATHS[@]}" 2>/dev/null || true
    if ! git pull --ff-only origin main 2>&1; then
        err "git pull falhou. Possíveis causas: mudanças locais FORA dos artefatos"
        err "  de export (em código/config — investigue com 'git status'), ou erro"
        err "  de autenticação (remote privado/SSH sem credencial no deploy)."
        err "  Remote atual: $(git remote get-url origin 2>/dev/null || echo '?')"
        exit 1
    fi
fi
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

# Install/update the web app unit from the repo too (self-healing).
WEB_UNIT_SOURCE="${REPO_DIR}/systemd/${SERVICE}"
WEB_UNIT_TARGET="/etc/systemd/system/${SERVICE}"
if [ -f "$WEB_UNIT_SOURCE" ]; then
    install -m 0644 "$WEB_UNIT_SOURCE" "$WEB_UNIT_TARGET"
    systemctl daemon-reload
    systemctl enable "$SERVICE" >/dev/null
    log "Unit ${SERVICE} instalada/atualizada e habilitada."
else
    log "AVISO: ${WEB_UNIT_SOURCE} não encontrado; mantendo unit existente de ${SERVICE}."
fi

# Ownership canônico: o deploy roda como root (cron), mas build.py, os bancos e
# AMBOS os serviços operam como ${RUN_USER}. Sem este chown, o git pull/build
# como root deixaria os arquivos root:root e a API (User=fino) falharia ao
# escrever em price-history.db (causa raiz do PermissionError). Idempotente.
if id "$RUN_USER" >/dev/null 2>&1; then
    chown -R "${RUN_USER}:${RUN_GROUP}" "$REPO_DIR"
    log "Ownership normalizado: ${RUN_USER}:${RUN_GROUP} em ${REPO_DIR}."
else
    err "Usuário ${RUN_USER} não existe. Ajuste FILAMENTDB_RUN_USER em config.env. Abortando para não deixar permissões inconsistentes."
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

# build.py e import_price_data.py rodaram como root e recriaram/tocaram os
# bancos (DROP+CREATE do filament.db, escrita em price-history.db). Renormaliza
# o dono para ${RUN_USER} antes de subir os serviços, senão a API não escreve.
chown -R "${RUN_USER}:${RUN_GROUP}" "$REPO_DIR"
log "Ownership renormalizado pós-build: ${RUN_USER}:${RUN_GROUP}."

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
API_LOCAL_URL="http://127.0.0.1:${FILAMENTDB_API_PORT:-5001}"
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
