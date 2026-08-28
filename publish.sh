#!/usr/bin/env bash
#
# publish.sh — Publica perfis do FilamentDB para ~/filament-db/.
#
# Por padrão exporta apenas os fabricantes habilitados (Voolt3D, Creality,
# Sunlu, F3D, Elegoo). Use --add para incluir fabricantes extras ou --all
# para exportar todos.
#
# Uso:
#   ./publish.sh                           # build + publish (fabricantes padrão)
#   ./publish.sh --add "Bambu Lab"         # inclui Bambu Lab além dos padrão
#   ./publish.sh --add 3DLab --add GTMax   # inclui múltiplos extras
#   ./publish.sh --all                     # exporta TODOS os fabricantes
#   ./publish.sh --list                    # lista fabricantes disponíveis
#   ./publish.sh --no-build                # pula o build.py

set -euo pipefail

# --- Configuração -----------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Config centralizada (fonte única de verdade). Carrega config.env se existir,
# sem sobrescrever variáveis já presentes no ambiente.
if [[ -f "${SCRIPT_DIR}/config.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "${SCRIPT_DIR}/config.env"
    set +a
fi

SOURCE_FILAMENTS="${SCRIPT_DIR}/Creality-Print/filaments"
SOURCE_PROCESS="${SCRIPT_DIR}/Creality-Print/process"
SOURCE_ORCA_FILAMENTS="${SCRIPT_DIR}/OrcaSlicer/filament"
SOURCE_ORCA_PROCESS="${SCRIPT_DIR}/OrcaSlicer/process"
DB_PATH="${SCRIPT_DIR}/filament.db"

FILAMENT_DEST="${FILAMENT_DEST:-${HOME}/filament-db/creality-print/filament}"
PROCESS_DEST="${PROCESS_DEST:-${HOME}/filament-db/creality-print/process}"
ORCA_FILAMENT_DEST="${ORCA_FILAMENT_DEST:-${HOME}/filament-db/orca/filament}"
ORCA_PROCESS_DEST="${ORCA_PROCESS_DEST:-${HOME}/filament-db/orca/process}"

# Fabricantes padrão (sempre exportados)
DEFAULT_MANUFACTURERS=("Voolt3D" "Creality" "Sunlu" "F3D" "Elegoo")

# --- Cores -------------------------------------------------------------------

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }

# --- Args --------------------------------------------------------------------

RUN_BUILD=true
EXPORT_ALL=false
SHOW_LIST=false
EXTRA_MANUFACTURERS=()
while [[ $# -gt 0 ]]; do
    case "$1" in
        --no-build)
            RUN_BUILD=false
            shift
            ;;
        --all)
            EXPORT_ALL=true
            shift
            ;;
        --list)
            SHOW_LIST=true
            shift
            ;;
        --add)
            if [[ -z "${2:-}" ]]; then
                error "--add requer um nome de fabricante"
            fi
            EXTRA_MANUFACTURERS+=("$2")
            shift 2
            ;;
        --help|-h)
            echo "Uso: $0 [opções]"
            echo ""
            echo "Opções:"
            echo "  --no-build          Pula o build.py, usa export existente"
            echo "  --add <fabricante>   Inclui fabricante extra (pode repetir)"
            echo "  --all               Exporta TODOS os fabricantes do banco"
            echo "  --list              Lista fabricantes disponíveis e sai"
            echo "  --help              Mostra esta ajuda"
            echo ""
            echo "Fabricantes padrão: ${DEFAULT_MANUFACTURERS[*]}"
            echo ""
            echo "Exemplos:"
            echo "  $0                              # build + publish local"
            echo "  $0 --add \"Bambu Lab\" --add 3DLab"
            echo "  $0 --all --no-build"
            exit 0
            ;;
        *)
            error "Argumento desconhecido: $1"
            ;;
    esac
done

# --- List (se solicitado) ----------------------------------------------------

if [[ "$SHOW_LIST" == true ]]; then
    if [[ ! -f "$DB_PATH" ]]; then
        error "Banco não encontrado: $DB_PATH (rode build.py primeiro)"
    fi

    echo -e "${BOLD}Fabricantes disponíveis no banco:${NC}"
    echo ""

    # Query fabricantes com contagem de perfis
    sqlite3 "$DB_PATH" "
        SELECT m.name, COUNT(fp.id)
        FROM manufacturers m
        JOIN filament_profiles fp ON fp.manufacturer_id = m.id
        WHERE fp.active = 1
        GROUP BY m.name
        ORDER BY m.name;
    " | while IFS='|' read -r name count; do
        # Marcar os padrão
        if printf '%s\n' "${DEFAULT_MANUFACTURERS[@]}" | grep -qx "$name"; then
            echo -e "  ${GREEN}●${NC} ${name} (${count} perfis) ${CYAN}[padrão]${NC}"
        else
            echo -e "  ○ ${name} (${count} perfis)"
        fi
    done

    echo ""
    echo -e "Use ${BOLD}--add \"Nome\"${NC} para incluir extras ou ${BOLD}--all${NC} para todos."
    exit 0
fi

# --- Build (opcional) --------------------------------------------------------

if [[ "$RUN_BUILD" == true ]]; then
    info "Executando build.py..."

    # Se há extras ou --all, passa a lista de fabricantes ao build
    if [[ "$EXPORT_ALL" == true ]]; then
        MANUFACTURERS_ENV="__ALL__"
    elif [[ ${#EXTRA_MANUFACTURERS[@]} -gt 0 ]]; then
        # Junta padrão + extras
        ALL_MFRS=("${DEFAULT_MANUFACTURERS[@]}" "${EXTRA_MANUFACTURERS[@]}")
        MANUFACTURERS_ENV=$(printf '%s,' "${ALL_MFRS[@]}")
        MANUFACTURERS_ENV="${MANUFACTURERS_ENV%,}"  # remove trailing comma
    else
        MANUFACTURERS_ENV=""
    fi

    EXPORT_MANUFACTURERS_OVERRIDE="$MANUFACTURERS_ENV" python3 "${SCRIPT_DIR}/build.py"
    echo ""
fi

# --- Validação ---------------------------------------------------------------

if [[ ! -d "$SOURCE_FILAMENTS" ]]; then
    error "Diretório de filamentos não encontrado: $SOURCE_FILAMENTS\nRode sem --no-build ou execute build.py primeiro."
fi

if [[ ! -d "$SOURCE_PROCESS" ]]; then
    error "Diretório de processos não encontrado: $SOURCE_PROCESS"
fi

# --- Preparação do destino (sync limpo) --------------------------------------

mkdir -p "$FILAMENT_DEST" "$PROCESS_DEST" "$ORCA_FILAMENT_DEST" "$ORCA_PROCESS_DEST"

# --- Backup antes de sobrescrever --------------------------------------------

BACKUP_DIR="${HOME}/filament-db/backups"
MAX_BACKUPS=10

# Só faz backup se há arquivos existentes para proteger
existing_files=$(find "$FILAMENT_DEST" "$PROCESS_DEST" "$ORCA_FILAMENT_DEST" "$ORCA_PROCESS_DEST" \
    -maxdepth 1 -type f \( -name "*.json" -o -name "*.info" \) 2>/dev/null | wc -l)

if [[ "$existing_files" -gt 0 ]]; then
    mkdir -p "$BACKUP_DIR"
    BACKUP_TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    BACKUP_FILE="${BACKUP_DIR}/profiles_${BACKUP_TIMESTAMP}.zip"

    info "Backup dos perfis atuais → ${BACKUP_FILE}"

    # Cria zip preservando estrutura de diretórios relativa a ~/filament-db/
    (cd "${HOME}/filament-db" && zip -qr "$BACKUP_FILE" \
        creality-print/filament/ \
        creality-print/process/ \
        orca/filament/ \
        orca/process/ \
        2>/dev/null) || true

    if [[ -f "$BACKUP_FILE" ]]; then
        BACKUP_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
        info "  Backup criado: ${BACKUP_SIZE} (${existing_files} arquivos)"
    fi

    # Rotação: mantém apenas os últimos MAX_BACKUPS
    backup_count=$(find "$BACKUP_DIR" -maxdepth 1 -name "profiles_*.zip" -type f | wc -l)
    if [[ "$backup_count" -gt "$MAX_BACKUPS" ]]; then
        remove_count=$((backup_count - MAX_BACKUPS))
        find "$BACKUP_DIR" -maxdepth 1 -name "profiles_*.zip" -type f -printf '%T+ %p\n' \
            | sort | head -n "$remove_count" | cut -d' ' -f2- \
            | while read -r old_backup; do
                rm -f "$old_backup"
            done
        info "  Rotação: removidos ${remove_count} backup(s) antigo(s), mantendo últimos ${MAX_BACKUPS}"
    fi
else
    info "Primeiro publish — sem backup necessário."
fi

# Limpa destino para garantir sync exato (remove antigos)
warn "Sincronizando destino (removendo perfis antigos)..."
find "$FILAMENT_DEST" -maxdepth 1 -type f \( -name "*.json" -o -name "*.info" \) -delete
find "$PROCESS_DEST" -maxdepth 1 -type f \( -name "*.json" -o -name "*.info" \) -delete
find "$ORCA_FILAMENT_DEST" -maxdepth 1 -type f -name "*.json" -delete
find "$ORCA_PROCESS_DEST" -maxdepth 1 -type f -name "*.json" -delete

# --- Copia filamentos --------------------------------------------------------

info "Publicando filamentos..."
info "  Origem:  $SOURCE_FILAMENTS"
info "  Destino: $FILAMENT_DEST"
cp -f "$SOURCE_FILAMENTS"/*.json "$FILAMENT_DEST/" 2>/dev/null || true
cp -f "$SOURCE_FILAMENTS"/*.info "$FILAMENT_DEST/" 2>/dev/null || true
FILAMENT_COUNT=$(find "$FILAMENT_DEST" -maxdepth 1 -name "*.json" -type f | wc -l)

# --- Copia processos ---------------------------------------------------------

echo ""
info "Publicando processos..."
info "  Origem:  $SOURCE_PROCESS"
info "  Destino: $PROCESS_DEST"
cp -f "$SOURCE_PROCESS"/*.json "$PROCESS_DEST/" 2>/dev/null || true
PROCESS_COUNT=$(find "$PROCESS_DEST" -maxdepth 1 -name "*.json" -type f | wc -l)

# --- Copia Orca Slicer -------------------------------------------------------

echo ""
info "Publicando filamentos Orca..."
info "  Origem:  $SOURCE_ORCA_FILAMENTS"
info "  Destino: $ORCA_FILAMENT_DEST"
cp -f "$SOURCE_ORCA_FILAMENTS"/*.json "$ORCA_FILAMENT_DEST/" 2>/dev/null || true
ORCA_FILAMENT_COUNT=$(find "$ORCA_FILAMENT_DEST" -maxdepth 1 -name "*.json" -type f | wc -l)

echo ""
info "Publicando processos Orca..."
info "  Origem:  $SOURCE_ORCA_PROCESS"
info "  Destino: $ORCA_PROCESS_DEST"
cp -f "$SOURCE_ORCA_PROCESS"/*.json "$ORCA_PROCESS_DEST/" 2>/dev/null || true
ORCA_PROCESS_COUNT=$(find "$ORCA_PROCESS_DEST" -maxdepth 1 -name "*.json" -type f | wc -l)

# --- Resumo ------------------------------------------------------------------

echo ""
echo "==========================================="
info "Publicação concluída!"
echo "==========================================="
info "Creality Print:"
info "  Filamentos: ${FILAMENT_COUNT} perfis em ${FILAMENT_DEST}"
info "  Processos:  ${PROCESS_COUNT} perfis em ${PROCESS_DEST}"
info "Orca Slicer:"
info "  Filamentos: ${ORCA_FILAMENT_COUNT} perfis em ${ORCA_FILAMENT_DEST}"
info "  Processos:  ${ORCA_PROCESS_COUNT} perfis em ${ORCA_PROCESS_DEST}"

if [[ "$EXPORT_ALL" == true ]]; then
    info "Fabricantes: TODOS"
elif [[ ${#EXTRA_MANUFACTURERS[@]} -gt 0 ]]; then
    info "Fabricantes: ${DEFAULT_MANUFACTURERS[*]} + ${EXTRA_MANUFACTURERS[*]}"
else
    info "Fabricantes: ${DEFAULT_MANUFACTURERS[*]}"
fi
echo ""
