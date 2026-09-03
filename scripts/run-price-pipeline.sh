#!/usr/bin/env bash
#
# run-price-pipeline.sh — executa o pipeline de coleta de preços localmente,
# replicando o fluxo snapshot-first do GitHub Actions, para validar antes de
# rodar no CI.
#
#   build.py --only-db  ->  collect_prices_agent.py  ->  validate_price_snapshot.py  [-> publish]
#
# Uso:
#   ./scripts/run-price-pipeline.sh                 # build + collect + validate (sem publicar)
#   ./scripts/run-price-pipeline.sh --publish       # inclui publicação na API
#   PRICE_AGENT_MAX_PROFILES=2 ./scripts/run-price-pipeline.sh   # itera rápido com poucos perfis
#   ./scripts/run-price-pipeline.sh --date 2026-09-02
#
# Sem MISTRAL_API_KEY/GEMINI_API_KEY configuradas, a etapa de coleta é pulada e
# o runner valida o snapshot mais recente já existente em data/price-data/.
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PUBLISH=0
DATE_ARG=""
while [ $# -gt 0 ]; do
    case "$1" in
        --publish) PUBLISH=1; shift ;;
        --date) DATE_ARG="$2"; shift 2 ;;
        --date=*) DATE_ARG="${1#*=}"; shift ;;
        -h|--help) grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "[ERRO] argumento desconhecido: $1" >&2; exit 2 ;;
    esac
done

# --- Python / venv ---------------------------------------------------------
if [ -x "$ROOT/.venv/bin/python" ]; then
    PY="$ROOT/.venv/bin/python"
else
    PY="$(command -v python3 || true)"
    [ -n "$PY" ] || { echo "[ERRO] Python não encontrado (nem .venv nem python3)." >&2; exit 1; }
    echo "[WARN] .venv não encontrado; usando $PY"
fi

info() { printf '\033[1;36m[pipeline]\033[0m %s\n' "$*"; }

# --- Dependências do collector --------------------------------------------
if ! "$PY" -c "import openai" >/dev/null 2>&1 || ! "$PY" -c "import ddgs" >/dev/null 2>&1; then
    info "Instalando dependências do collector (openai, ddgs, requirements.txt)..."
    "$PY" -m pip install --quiet --upgrade -r requirements.txt openai ddgs
fi

# --- 1. Catálogo -----------------------------------------------------------
info "Build do catálogo (build.py --only-db)"
"$PY" build.py --only-db

# --- 2. Coleta -------------------------------------------------------------
HAS_KEYS=0
if [ -n "${MISTRAL_API_KEY:-}" ] || [ -n "${GEMINI_API_KEY:-}" ]; then
    HAS_KEYS=1
fi

if [ "$HAS_KEYS" -eq 1 ]; then
    info "Coleta de preços (collect_prices_agent.py)"
    if [ -n "$DATE_ARG" ]; then
        PYTHONUNBUFFERED=1 "$PY" scripts/collect_prices_agent.py --date "$DATE_ARG"
    else
        PYTHONUNBUFFERED=1 "$PY" scripts/collect_prices_agent.py
    fi
else
    info "Sem MISTRAL_API_KEY/GEMINI_API_KEY — pulando coleta; validando o snapshot mais recente existente."
fi

# --- 3. Validação ----------------------------------------------------------
info "Validação do snapshot (validate_price_snapshot.py)"
if [ -n "$DATE_ARG" ] && [ -f "data/price-data/${DATE_ARG}.json" ]; then
    "$PY" scripts/validate_price_snapshot.py "data/price-data/${DATE_ARG}.json"
else
    "$PY" scripts/validate_price_snapshot.py
fi

# --- 4. Publicação (opcional) ---------------------------------------------
if [ "$PUBLISH" -eq 1 ]; then
    if [ -z "${FILAMENTDB_API_SECRET:-}" ]; then
        echo "[ERRO] --publish exige FILAMENTDB_API_SECRET no ambiente." >&2
        exit 1
    fi
    info "Publicação na API (publish_price_snapshot.py)"
    if [ -n "$DATE_ARG" ] && [ -f "data/price-data/${DATE_ARG}.json" ]; then
        "$PY" scripts/publish_price_snapshot.py "data/price-data/${DATE_ARG}.json"
    else
        "$PY" scripts/publish_price_snapshot.py
    fi
else
    info "Publicação NÃO executada (use --publish para enviar à API)."
fi

info "Pipeline local concluído."
