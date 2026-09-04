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
# Autorização:
#   Quando a API roda com FILAMENTDB_AUTH_ENABLED=1 (fail-closed), a escrita
#   exige o segredo compartilhado do proxy e uma identidade na allowlist. Este
#   script lê essas credenciais do config.env do projeto e injeta os headers:
#     - X-Proxy-Secret: <FILAMENTDB_PROXY_SECRET>   (passa o gate untrusted_origin)
#     - <FILAMENTDB_IDENTITY_HEADER>: <writer>       (passa o gate not_a_writer)
#   A identidade usada é SEED_IDENTITY, se definida; senão o 1º e-mail de
#   FILAMENTDB_WRITERS. Sem PROXY_SECRET configurado, nenhum header é enviado
#   (comportamento idêntico ao anterior, útil em dev/local com auth desligada).
#
# Variáveis de ambiente:
#   BASE_URL       URL base da API (default: http://localhost:5000)
#   CONFIG_ENV     Caminho do config.env (default: <repo>/config.env)
#   SEED_IDENTITY  E-mail/usuário a enviar no header de identidade (sobrepõe o
#                  1º de FILAMENTDB_WRITERS)
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

# ── Carrega credenciais de auth do config.env ────────────────────────────────
# O config.env é KEY=VALUE (mesmo formato lido por src/config.py). Só extraímos
# as chaves de auth — sem `source` para não herdar/expandir o arquivo inteiro
# nem quebrar com valores que contenham espaços/aspas.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
CONFIG_ENV="${CONFIG_ENV:-${REPO_DIR}/config.env}"

# read_config <KEY>: lê o valor de uma chave do config.env, removendo aspas.
# Retorna vazio se o arquivo ou a chave não existirem. A precedência dá ao
# ambiente prioridade sobre o arquivo (igual ao src/config.py).
read_config() {
    local key="$1" val=""
    if [ -f "$CONFIG_ENV" ]; then
        # última ocorrência vence; ignora comentários; tira `export ` e aspas.
        val=$(grep -E "^[[:space:]]*(export[[:space:]]+)?${key}=" "$CONFIG_ENV" 2>/dev/null \
              | sed -E "s/^[[:space:]]*(export[[:space:]]+)?${key}=//; s/^[\"']//; s/[\"']$//" \
              | tail -n1)
    fi
    printf '%s' "$val"
}

# Ambiente > config.env (mantém a mesma precedência do carregador Python).
PROXY_SECRET="${FILAMENTDB_PROXY_SECRET:-$(read_config FILAMENTDB_PROXY_SECRET)}"
IDENTITY_HEADER="${FILAMENTDB_IDENTITY_HEADER:-$(read_config FILAMENTDB_IDENTITY_HEADER)}"
IDENTITY_HEADER="${IDENTITY_HEADER:-Remote-Email}"
WRITERS="${FILAMENTDB_WRITERS:-$(read_config FILAMENTDB_WRITERS)}"
# Identidade a enviar: SEED_IDENTITY explícito, senão o 1º e-mail de WRITERS.
IDENTITY="${SEED_IDENTITY:-${WRITERS%%,*}}"

# Monta os headers de auth uma única vez. Vazio quando não há PROXY_SECRET —
# nesse caso o script se comporta exatamente como antes (dev/local sem auth).
AUTH_HEADERS=()
if [ -n "$PROXY_SECRET" ]; then
    AUTH_HEADERS+=(-H "X-Proxy-Secret: ${PROXY_SECRET}")
    if [ -n "$IDENTITY" ]; then
        AUTH_HEADERS+=(-H "${IDENTITY_HEADER}: ${IDENTITY}")
        info "Auth: enviando X-Proxy-Secret + ${IDENTITY_HEADER}=${IDENTITY}"
    else
        warn "PROXY_SECRET presente, mas sem identidade (SEED_IDENTITY/FILAMENTDB_WRITERS vazios)."
        warn "Escrita pode falhar com 'not_a_writer'. Defina SEED_IDENTITY=<email-writer>."
    fi
else
    info "Auth: nenhum PROXY_SECRET no config.env — não enviando headers (modo aberto/dev)."
fi

# ── Checa se a API está no ar ──
if ! curl -fsS --max-time 5 "${AUTH_HEADERS[@]}" "${BASE_URL}/health" >/dev/null 2>&1; then
    error "API não respondeu em ${BASE_URL}/health. O servidor está rodando?"
fi
info "API respondeu em /health"

# ── POST helper: post_item <material> <manufacturer> <color> <hex> <finish> <spools> <status> [weight_g] ──
# weight_g é opcional; se omitido, assume 1000 (rolo padrão de 1 kg).
post_item() {
    local material="$1" manufacturer="$2" color="$3" hex="$4" finish="$5" spools="$6" status="$7" weight="${8:-1000}"
    local finish_json="null"
    [ -n "$finish" ] && finish_json="\"${finish}\""

    local payload
    payload=$(cat <<JSON
{"material":"${material}","manufacturer":"${manufacturer}","color_name":"${color}","hex_color":"${hex}","finish":${finish_json},"weight_g":${weight},"spools":${spools},"status":"${status}"}
JSON
)
    local http_code
    http_code=$(curl -s -o /tmp/seed_resp.$$ -w '%{http_code}' \
        -X POST "${BASE_URL}/api/inventory" \
        -H 'Content-Type: application/json' \
        "${AUTH_HEADERS[@]}" \
        --data "${payload}" || echo "000")

    if [ "$http_code" = "201" ]; then
        printf "  ${GREEN}OK${NC}  %-9s %-7s %-9s %-18s x%s %sg\n" "$status" "$material" "$manufacturer" "$color" "$spools" "$weight"
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
    ids=$(curl -fsS "${AUTH_HEADERS[@]}" "${BASE_URL}/api/inventory/items" | grep -o '"id"[[:space:]]*:[[:space:]]*[0-9]*' | grep -o '[0-9]*' || true)
    for id in $ids; do
        curl -s -o /dev/null "${AUTH_HEADERS[@]}" -X DELETE "${BASE_URL}/api/inventory/${id}"
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

# ── Compras recentes ──
post_item "PETG"   "Creality" "Verde"           "#2E7D32" "Hyper"     2 "in_stock"
post_item "PETG"   "Creality" "Verde"           "#2E7D32" "CR-PETG"   1 "in_stock"
post_item "PETG"   "Creality" "Preto"           "#101010" "CR-PETG"   2 "in_stock"
post_item "PLA"    "Sunlu"    "Branco"          "#F4F4F2" "Matte"     1 "in_stock" 500
post_item "PLA"    "Sunlu"    "Preto"           "#101010" "Matte"     1 "in_stock" 500

echo ""
info "Concluído: ${OK} inseridos, ${FAIL} falhas."

# ── Resumo ──
info "Resumo do estoque:"
curl -fsS "${AUTH_HEADERS[@]}" "${BASE_URL}/api/inventory" \
    | python3 -c 'import sys,json; s=json.load(sys.stdin)["summary"]; print("  materiais=%s itens=%s rolos=%s | CFS=%s/%s spool=%s/%s abertos=%s" % (s["materials"],s["total_items"],s["total_spools"],s["cfs_used"],s["cfs_max"],s["spool_used"],s["spool_max"],s["open_count"]))' \
    2>/dev/null || warn "Não foi possível formatar o resumo (python3 ausente?)."

[ "$FAIL" -eq 0 ] || exit 1
