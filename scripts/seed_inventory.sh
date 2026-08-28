#!/usr/bin/env bash
#
# seed_inventory.sh — Cadastra o estoque inicial de filamentos via API (curl).
#
# O backend cria/valida o banco de estoque (inventory.db) sozinho no startup,
# então basta a API estar no ar. Este script apenas insere os itens.
#
# Uso:
#   ./scripts/seed_inventory.sh                      # usa http://localhost:5000
#   BASE_URL=https://filamentdb.exemplo.com ./scripts/seed_inventory.sh
#   ./scripts/seed_inventory.sh https://meu-servidor:5000
#   ./scripts/seed_inventory.sh --reset              # apaga o estoque antes de inserir
#
# Variáveis de ambiente:
#   BASE_URL   URL base da API (default: http://localhost:5000)
#
set -euo pipefail

# ── Cores ──
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }

# ── Argumentos ──
RESET=0
POSITIONAL_URL=""
for arg in "$@"; do
    case "$arg" in
        --reset) RESET=1 ;;
        http://*|https://*) POSITIONAL_URL="$arg" ;;
        -h|--help)
            grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) warn "Argumento ignorado: $arg" ;;
    esac
done

BASE_URL="${POSITIONAL_URL:-${BASE_URL:-http://localhost:5000}}"
BASE_URL="${BASE_URL%/}"   # remove barra final

command -v curl >/dev/null 2>&1 || error "curl não encontrado. Instale o curl."

info "Alvo: ${BASE_URL}"

# ── Checa se a API está no ar ──
if ! curl -fsS --max-time 5 "${BASE_URL}/health" >/dev/null 2>&1; then
    error "API não respondeu em ${BASE_URL}/health. O servidor está rodando?"
fi
info "API respondeu em /health"

# ── POST helper: post_item <material> <manufacturer> <color> <hex> <finish> <spools> <status> ──
post_item() {
    local material="$1" manufacturer="$2" color="$3" hex="$4" finish="$5" spools="$6" status="$7"
    local finish_json="null"
    [ -n "$finish" ] && finish_json="\"${finish}\""

    local payload
    payload=$(cat <<JSON
{"material":"${material}","manufacturer":"${manufacturer}","color_name":"${color}","hex_color":"${hex}","finish":${finish_json},"spools":${spools},"status":"${status}"}
JSON
)
    local http_code
    http_code=$(curl -s -o /tmp/seed_resp.$$ -w '%{http_code}' \
        -X POST "${BASE_URL}/api/inventory" \
        -H 'Content-Type: application/json' \
        --data "${payload}" || echo "000")

    if [ "$http_code" = "201" ]; then
        printf "  ${GREEN}OK${NC}  %-9s %-7s %-9s %-18s x%s\n" "$status" "$material" "$manufacturer" "$color" "$spools"
        OK=$((OK+1))
    else
        local msg; msg=$(cat /tmp/seed_resp.$$ 2>/dev/null || true)
        printf "  ${RED}ERR(%s)${NC} %-7s %-9s %-18s -> %s\n" "$http_code" "$material" "$manufacturer" "$color" "$msg"
        FAIL=$((FAIL+1))
    fi
    rm -f /tmp/seed_resp.$$
}

# ── Reset opcional: apaga todos os itens atuais ──
if [ "$RESET" = "1" ]; then
    warn "Removendo estoque atual (--reset)..."
    ids=$(curl -fsS "${BASE_URL}/api/inventory/items" | grep -o '"id"[[:space:]]*:[[:space:]]*[0-9]*' | grep -o '[0-9]*' || true)
    for id in $ids; do
        curl -s -o /dev/null -X DELETE "${BASE_URL}/api/inventory/${id}"
    done
    info "Estoque limpo."
fi

OK=0; FAIL=0

info "Cadastrando filamentos..."

# ── CFS (4 slots) ──
post_item "PLA"    "Voolt3D" "Preto"            "#101010" "Velvet"   1 "cfs"
post_item "PLA"    "Voolt3D" "Azul"             "#1565C0" "Velvet"   1 "cfs"
post_item "PLA"    "Voolt3D" "Amarelo"          "#F4C20D" "Velvet"   1 "cfs"
post_item "PLA"    "Sunlu"   "Branco"           "#F4F4F2" "Matte"    1 "cfs"

# ── Spool holder (1) ──
post_item "PETG"   "Sunlu"   "Preto"            "#101010" "HF"       1 "spool"

# ── Dryboxes ──
post_item "PLA"    "Voolt3D" "Amarelo Macarron" "#F3E37C" "Premium"  1 "drybox"
post_item "PLA"    "Elegoo"  "Preto"            "#101010" "Rapid+"   1 "drybox"
post_item "PLA"    "Voolt3D" "Branco"           "#F4F4F2" "Velvet"   1 "drybox"

# ── Aberto (alerta) ──
post_item "PLA"    "Voolt3D" "Laranja"          "#E8720C" "Velvet"   1 "open"

# ── Em estoque (fechado) ──
post_item "ABS"    "Voolt3D"  "Preto"           "#101010" ""          1 "in_stock"
post_item "PLA-CF" "Voolt3D"  "Preto"           "#101010" ""          1 "in_stock"
post_item "PETG"   "Creality" "Azul"            "#1565C0" "Hyper"     2 "in_stock"
post_item "PETG"   "Voolt3D"  "Translucido"     "#CFE8F0" "HF"        1 "in_stock"
post_item "TPU"    "Elegoo"   "Preto"           "#101010" "T95"       1 "in_stock"
post_item "PETG"   "Voolt3D"  "Azul"            "#1565C0" "HF"        1 "in_stock"
post_item "PLA"    "Voolt3D"  "Lilas Macarron"  "#C9A8E0" "Premium"   1 "in_stock"
post_item "PLA"    "Voolt3D"  "Dourado"         "#D4AF37" "Silk"      1 "in_stock"
post_item "PLA"    "Voolt3D"  "Vermelho"        "#C41E3A" "Velvet"    2 "in_stock"
post_item "PLA"    "Voolt3D"  "Amarelo"         "#F4C20D" "Velvet"    1 "in_stock"
post_item "PLA"    "Voolt3D"  "Preto"           "#101010" "Velvet"    3 "in_stock"
post_item "PLA"    "Sunlu"    "Preto"           "#101010" "HF Matte"  3 "in_stock"
post_item "PETG"   "Sunlu"    "Preto"           "#101010" "HF Matte"  1 "in_stock"
post_item "PETG"   "Sunlu"    "Laranja"         "#E8720C" "HF Fosco"  1 "in_stock"
post_item "PLA"    "Voolt3D"  "Branco"          "#F4F4F2" "Velvet"    3 "in_stock"

echo ""
info "Concluído: ${OK} inseridos, ${FAIL} falhas."

# ── Resumo ──
info "Resumo do estoque:"
curl -fsS "${BASE_URL}/api/inventory" \
    | python3 -c 'import sys,json; s=json.load(sys.stdin)["summary"]; print("  materiais=%s itens=%s rolos=%s | CFS=%s/%s spool=%s/%s abertos=%s" % (s["materials"],s["total_items"],s["total_spools"],s["cfs_used"],s["cfs_max"],s["spool_used"],s["spool_max"],s["open_count"]))' \
    2>/dev/null || warn "Não foi possível formatar o resumo (python3 ausente?)."

[ "$FAIL" -eq 0 ] || exit 1
