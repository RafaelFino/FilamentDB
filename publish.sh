#!/usr/bin/env bash
#
# publish.sh — Publica os perfis gerados para o Creality Print local.
#
# Copia os filamentos e processos exportados em Creality-Print/ para os
# diretórios que o Creality Print lê na máquina local.
#
# Uso:
#   ./publish.sh              # build + publish
#   ./publish.sh --no-build   # apenas publish (sem rodar build.py)
#   ./publish.sh --clean      # limpa destino antes de copiar
#
# Configuração:
#   As variáveis FILAMENT_DEST e PROCESS_DEST podem ser sobrescritas
#   via variáveis de ambiente:
#     FILAMENT_DEST=~/outro/path ./publish.sh
#

set -euo pipefail

# --- Configuração -----------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_FILAMENTS="${SCRIPT_DIR}/Creality-Print/filaments"
SOURCE_PROCESS="${SCRIPT_DIR}/Creality-Print/process"

FILAMENT_DEST="${FILAMENT_DEST:-${HOME}/filament-db/filament}"
PROCESS_DEST="${PROCESS_DEST:-${HOME}/filament-db/process}"

# --- Cores -------------------------------------------------------------------

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }

# --- Args --------------------------------------------------------------------

RUN_BUILD=true
CLEAN=false

for arg in "$@"; do
    case "$arg" in
        --no-build) RUN_BUILD=false ;;
        --clean)    CLEAN=true ;;
        --help|-h)
            echo "Uso: $0 [--no-build] [--clean] [--help]"
            echo ""
            echo "  --no-build   Pula o build.py, apenas copia arquivos existentes"
            echo "  --clean      Remove arquivos antigos no destino antes de copiar"
            echo "  --help       Mostra esta ajuda"
            echo ""
            echo "Variáveis de ambiente:"
            echo "  FILAMENT_DEST   Diretório destino dos filamentos (default: ~/filament/filament)"
            echo "  PROCESS_DEST    Diretório destino dos processos  (default: ~/filament/process)"
            exit 0
            ;;
        *) error "Argumento desconhecido: $arg" ;;
    esac
done

# --- Build (opcional) --------------------------------------------------------

if [[ "$RUN_BUILD" == true ]]; then
    info "Executando build.py..."
    python3 "${SCRIPT_DIR}/build.py"
    echo ""
fi

# --- Validação ---------------------------------------------------------------

if [[ ! -d "$SOURCE_FILAMENTS" ]]; then
    error "Diretório de filamentos não encontrado: $SOURCE_FILAMENTS"
fi

if [[ ! -d "$SOURCE_PROCESS" ]]; then
    error "Diretório de processos não encontrado: $SOURCE_PROCESS"
fi

# --- Preparação do destino ---------------------------------------------------

mkdir -p "$FILAMENT_DEST" "$PROCESS_DEST"

if [[ "$CLEAN" == true ]]; then
    warn "Limpando destino..."
    find "$FILAMENT_DEST" -maxdepth 1 -type f -name "*.json" -delete
    find "$PROCESS_DEST" -maxdepth 1 -type f -name "*.json" -delete
fi

# --- Copia -------------------------------------------------------------------

info "Publicando filamentos..."
info "  Origem:  $SOURCE_FILAMENTS"
info "  Destino: $FILAMENT_DEST"
cp -f "$SOURCE_FILAMENTS"/*.json "$FILAMENT_DEST/" 2>/dev/null || true
FILAMENT_COUNT=$(find "$FILAMENT_DEST" -maxdepth 1 -name "*.json" -type f | wc -l)

echo ""
info "Publicando processos..."
info "  Origem:  $SOURCE_PROCESS"
info "  Destino: $PROCESS_DEST"
cp -f "$SOURCE_PROCESS"/*.json "$PROCESS_DEST/" 2>/dev/null || true
PROCESS_COUNT=$(find "$PROCESS_DEST" -maxdepth 1 -name "*.json" -type f | wc -l)

# --- Resumo ------------------------------------------------------------------

echo ""
echo "==========================================="
info "Publicação concluída!"
echo "==========================================="
info "Filamentos: ${FILAMENT_COUNT} perfis em ${FILAMENT_DEST}"
info "Processos:  ${PROCESS_COUNT} perfis em ${PROCESS_DEST}"
echo ""
