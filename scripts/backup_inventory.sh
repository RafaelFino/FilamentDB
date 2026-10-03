#!/usr/bin/env bash
#
# backup_inventory.sh — Exporta todo o estoque para um arquivo JSON (via API).
#
# Baixa o envelope versionado de GET /api/inventory/export e grava num arquivo
# com timestamp. É o backup lógico do estoque: desacoplado do schema físico do
# SQLite, restaurável com restore_inventory.sh.
#
# Uso:
#   ./scripts/backup_inventory.sh                       # usa http://localhost:5000
#   BASE_URL=https://filamentdb.exemplo.com ./scripts/backup_inventory.sh
#   ./scripts/backup_inventory.sh https://meu-servidor:5000
#   ./scripts/backup_inventory.sh -o /caminho/backup.json   # arquivo de saída fixo
#
# Sem -o, o arquivo é gravado em backups/inventory-json/inventory_<timestamp>.json
# e os últimos MAX_JSON_BACKUPS (default 30) são mantidos (rotação).
#
# Autorização:
#   O endpoint de export é somente-leitura (aberto). Ainda assim, se houver
#   FILAMENTDB_PROXY_SECRET no config.env, enviamos os headers do proxy — útil
#   quando a API está atrás do Pangolin e exige o segredo até para leitura.
#
# Variáveis de ambiente:
#   BASE_URL           URL base da API (default: http://localhost:5000)
#   CONFIG_ENV         Caminho do config.env (default: <repo>/config.env)
#   BACKUP_DIR         Diretório-base de backups (default: <repo>/backups)
#   MAX_JSON_BACKUPS   Quantos dumps manter na rotação (default: 30)
#
set -euo pipefail

# ── Cores ──
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }

# ── Argumentos ──
OUTPUT=""
POSITIONAL_URL=""
while [ $# -gt 0 ]; do
    case "$1" in
        -o|--output) OUTPUT="${2:-}"; shift 2 ;;
        http://*|https://*) POSITIONAL_URL="$1"; shift ;;
        -h|--help) grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) warn "Argumento ignorado: $1"; shift ;;
    esac
done

BASE_URL="${POSITIONAL_URL:-${BASE_URL:-http://localhost:5000}}"
BASE_URL="${BASE_URL%/}"

command -v curl >/dev/null 2>&1 || error "curl não encontrado. Instale o curl."

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
CONFIG_ENV="${CONFIG_ENV:-${REPO_DIR}/config.env}"

# read_config <KEY>: lê o valor de uma chave do config.env, removendo aspas.
read_config() {
    local key="$1" val=""
    if [ -f "$CONFIG_ENV" ]; then
        val=$(grep -E "^[[:space:]]*(export[[:space:]]+)?${key}=" "$CONFIG_ENV" 2>/dev/null \
              | sed -E "s/^[[:space:]]*(export[[:space:]]+)?${key}=//; s/^[\"']//; s/[\"']$//" \
              | tail -n1)
    fi
    printf '%s' "$val"
}

# Ambiente > config.env (mesma precedência do carregador Python).
PROXY_SECRET="${FILAMENTDB_PROXY_SECRET:-$(read_config FILAMENTDB_PROXY_SECRET)}"
IDENTITY_HEADER="${FILAMENTDB_IDENTITY_HEADER:-$(read_config FILAMENTDB_IDENTITY_HEADER)}"
IDENTITY_HEADER="${IDENTITY_HEADER:-Remote-Email}"
WRITERS="${FILAMENTDB_WRITERS:-$(read_config FILAMENTDB_WRITERS)}"
IDENTITY="${SEED_IDENTITY:-${WRITERS%%,*}}"

AUTH_HEADERS=()
if [ -n "$PROXY_SECRET" ]; then
    AUTH_HEADERS+=(-H "X-Proxy-Secret: ${PROXY_SECRET}")
    [ -n "$IDENTITY" ] && AUTH_HEADERS+=(-H "${IDENTITY_HEADER}: ${IDENTITY}")
fi

info "Alvo: ${BASE_URL}"

# ── Define o arquivo de saída ──
if [ -n "$OUTPUT" ]; then
    DEST="$OUTPUT"
    mkdir -p "$(dirname "$DEST")"
else
    BACKUP_DIR="${BACKUP_DIR:-${REPO_DIR}/backups}"
    JSON_DIR="${BACKUP_DIR}/inventory-json"
    mkdir -p "$JSON_DIR"
    DEST="${JSON_DIR}/inventory_$(date '+%Y%m%d_%H%M%S').json"
fi

# ── Baixa o export para um temporário e valida antes de mover ──
TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT

if ! curl -fsS --max-time 30 "${AUTH_HEADERS[@]}" "${BASE_URL}/api/inventory/export" -o "$TMP"; then
    error "Falha ao baixar o export de ${BASE_URL}/api/inventory/export (API no ar? auth ok?)."
fi

# Valida que é um envelope de export com 'items'.
COUNT=$(python3 -c "
import json, sys
d = json.load(open('$TMP'))
if 'items' not in d:
    sys.exit(1)
print(d.get('count', len(d['items'])))
" 2>/dev/null) || error "Resposta inesperada (sem 'items'). Nada foi gravado."

mv "$TMP" "$DEST"
trap - EXIT
info "Backup do estoque → ${DEST} (${COUNT} itens)"

# ── Rotação (só no modo diretório padrão) ──
if [ -z "$OUTPUT" ]; then
    MAX_JSON_BACKUPS="${MAX_JSON_BACKUPS:-30}"
    count=$(find "$JSON_DIR" -maxdepth 1 -name "inventory_*.json" -type f 2>/dev/null | wc -l)
    if [ "$count" -gt "$MAX_JSON_BACKUPS" ]; then
        find "$JSON_DIR" -maxdepth 1 -name "inventory_*.json" -type f -printf '%T+ %p\n' \
            | sort | head -n "$((count - MAX_JSON_BACKUPS))" | cut -d' ' -f2- \
            | while read -r old; do rm -f "$old"; done
        info "Rotação: mantidos os últimos ${MAX_JSON_BACKUPS} dumps."
    fi
fi
