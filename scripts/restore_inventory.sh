#!/usr/bin/env bash
#
# restore_inventory.sh — Restaura (seed) o estoque a partir de um JSON (via API).
#
# Envia um envelope de export para POST /api/inventory/import. O import faz
# upsert idempotente por `uid`: reaplica o mesmo arquivo sem duplicar. Com
# --replace ativa o modo espelho (remove itens que não estão no arquivo).
#
# É o par de backup_inventory.sh e a forma recomendada de popular/restaurar o
# estoque (preserva uid, status por rolo e timestamps — fiel ao estado salvo).
#
# Uso:
#   ./scripts/restore_inventory.sh backup.json                 # merge (não apaga nada)
#   ./scripts/restore_inventory.sh --replace backup.json       # espelho (apaga ausentes)
#   BASE_URL=https://filamentdb.exemplo.com ./scripts/restore_inventory.sh backup.json
#   ./scripts/restore_inventory.sh backup.json https://meu-servidor:5000
#
# Se nenhum arquivo for informado, usa o dump JSON mais recente em
# backups/inventory-json/.
#
# Autorização:
#   O import é uma operação de ESCRITA. Com FILAMENTDB_AUTH_ENABLED=1 exige o
#   segredo do proxy + uma identidade writer (lidos do config.env, como no
#   seed_inventory.sh). Sem PROXY_SECRET, nenhum header é enviado (dev/local).
#
# Variáveis de ambiente:
#   BASE_URL       URL base da API (default: http://localhost:5000)
#   CONFIG_ENV     Caminho do config.env (default: <repo>/config.env)
#   SEED_IDENTITY  Identidade a enviar (sobrepõe o 1º de FILAMENTDB_WRITERS)
#
set -euo pipefail

# ── Cores ──
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }

# ── Argumentos ──
REPLACE=0
INPUT=""
POSITIONAL_URL=""
while [ $# -gt 0 ]; do
    case "$1" in
        --replace) REPLACE=1; shift ;;
        http://*|https://*) POSITIONAL_URL="$1"; shift ;;
        -h|--help) grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        -*) warn "Opção ignorada: $1"; shift ;;
        *) INPUT="$1"; shift ;;
    esac
done

BASE_URL="${POSITIONAL_URL:-${BASE_URL:-http://localhost:5000}}"
BASE_URL="${BASE_URL%/}"

command -v curl >/dev/null 2>&1 || error "curl não encontrado. Instale o curl."

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
CONFIG_ENV="${CONFIG_ENV:-${REPO_DIR}/config.env}"

# ── Resolve o arquivo de entrada ──
if [ -z "$INPUT" ]; then
    JSON_DIR="${BACKUP_DIR:-${REPO_DIR}/backups}/inventory-json"
    INPUT=$(find "$JSON_DIR" -maxdepth 1 -name "inventory_*.json" -type f -printf '%T+ %p\n' 2>/dev/null \
            | sort | tail -n1 | cut -d' ' -f2-)
    [ -n "$INPUT" ] || error "Nenhum arquivo informado e nenhum dump em ${JSON_DIR}."
    info "Usando o dump mais recente: ${INPUT}"
fi
[ -f "$INPUT" ] || error "Arquivo não encontrado: ${INPUT}"

# Valida que o arquivo é um envelope de export (ou lista de itens).
python3 -c "
import json, sys
d = json.load(open('$INPUT'))
ok = isinstance(d, list) or (isinstance(d, dict) and 'items' in d)
sys.exit(0 if ok else 1)
" 2>/dev/null || error "Arquivo inválido: esperado envelope de export (com 'items') ou lista de itens."

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

PROXY_SECRET="${FILAMENTDB_PROXY_SECRET:-$(read_config FILAMENTDB_PROXY_SECRET)}"
IDENTITY_HEADER="${FILAMENTDB_IDENTITY_HEADER:-$(read_config FILAMENTDB_IDENTITY_HEADER)}"
IDENTITY_HEADER="${IDENTITY_HEADER:-Remote-Email}"
WRITERS="${FILAMENTDB_WRITERS:-$(read_config FILAMENTDB_WRITERS)}"
IDENTITY="${SEED_IDENTITY:-${WRITERS%%,*}}"

AUTH_HEADERS=()
if [ -n "$PROXY_SECRET" ]; then
    AUTH_HEADERS+=(-H "X-Proxy-Secret: ${PROXY_SECRET}")
    if [ -n "$IDENTITY" ]; then
        AUTH_HEADERS+=(-H "${IDENTITY_HEADER}: ${IDENTITY}")
        info "Auth: enviando X-Proxy-Secret + ${IDENTITY_HEADER}=${IDENTITY}"
    else
        warn "PROXY_SECRET presente, mas sem identidade (SEED_IDENTITY/FILAMENTDB_WRITERS vazios)."
        warn "A escrita pode falhar com 'not_a_writer'. Defina SEED_IDENTITY=<email-writer>."
    fi
else
    info "Auth: nenhum PROXY_SECRET no config.env — não enviando headers (modo aberto/dev)."
fi

# ── Monta a URL do import (com ?replace=true no modo espelho) ──
IMPORT_URL="${BASE_URL}/api/inventory/import"
if [ "$REPLACE" = "1" ]; then
    IMPORT_URL="${IMPORT_URL}?replace=true"
    warn "Modo ESPELHO (--replace): itens ausentes no arquivo serão REMOVIDOS do estoque."
fi

info "Alvo: ${BASE_URL}"
info "Importando: ${INPUT}"

RESP="$(mktemp)"; trap 'rm -f "$RESP"' EXIT
HTTP_CODE=$(curl -s -o "$RESP" -w '%{http_code}' \
    -X POST "$IMPORT_URL" \
    -H 'Content-Type: application/json' \
    "${AUTH_HEADERS[@]}" \
    --data @"$INPUT" || echo "000")

if [ "$HTTP_CODE" = "200" ]; then
    # Resumo: {created, updated, deleted, skipped, errors}
    python3 -c "
import json, sys
d = json.load(open('$RESP'))
s = d.get('summary', d)
print('  criados=%s atualizados=%s removidos=%s ignorados=%s erros=%s' % (
    s.get('created','?'), s.get('updated','?'), s.get('deleted','?'),
    s.get('skipped','?'), len(s.get('errors', [])) if isinstance(s.get('errors'), list) else s.get('errors','?')))
" 2>/dev/null || cat "$RESP"
    info "Restauração concluída (HTTP 200)."
else
    warn "Falha na importação (HTTP ${HTTP_CODE}):"
    cat "$RESP" >&2
    error "Import não concluído."
fi
