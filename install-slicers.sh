#!/usr/bin/env bash
#
# install-slicers.sh — Instala Creality Print e OrcaSlicer (AppImages) numa
# máquina nova, baixando a versão mais recente das GitHub Releases oficiais.
#
# Fonte: CrealityOfficial/CrealityPrint e SoftFever/OrcaSlicer (mesmo binário do
# site oficial, com URL determinística e versão detectável).
#
# Instala em ~/Applications/ com symlinks em ~/.local/bin (sem sudo). Idempotente:
# se já estiver na versão mais recente, não refaz (use --force para reinstalar).
# Ao final, chama install.sh para criar a árvore ~/filament-db e (re)gerar os
# inicializadores run-*.sh com os caminhos corretos.
#
# Uso:
#   ./install-slicers.sh                 # instala ambos (mais recente)
#   ./install-slicers.sh --only creality # só um slicer (creality|orca)
#   ./install-slicers.sh --force         # reinstala mesmo se já na latest
#   ./install-slicers.sh --dry-run       # mostra sem baixar/escrever
#   ./install-slicers.sh --no-structure  # pula a chamada ao install.sh
#   ./install-slicers.sh --help

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib-slicers.sh
source "${SCRIPT_DIR}/lib-slicers.sh"

DRY_RUN=false
FORCE=false
CHECK_ONLY=false
ONLY=""
RUN_STRUCTURE=true

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run)      DRY_RUN=true; shift ;;
        --force)        FORCE=true; shift ;;
        --only)         ONLY="${2:-}"; shift 2 ;;
        --no-structure) RUN_STRUCTURE=false; shift ;;
        --help|-h)
            sed -n '2,30p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
            exit 0 ;;
        *) lib_err "Argumento desconhecido: $1"; exit 1 ;;
    esac
done

export DRY_RUN FORCE CHECK_ONLY

echo ""
lib_step "FilamentDB — instalador dos slicers"
[[ "$DRY_RUN" == true ]] && lib_warn "modo --dry-run: nada será baixado/escrito"
echo ""

lib_require_tools || exit 1

rc=0
case "$ONLY" in
    creality) lib_process_creality install || rc=1 ;;
    orca)     lib_process_orca install || rc=1 ;;
    "")
        lib_process_creality install || rc=1
        echo ""
        lib_process_orca install || rc=1
        ;;
    *) lib_err "Valor inválido para --only: $ONLY (use creality|orca)"; exit 1 ;;
esac

echo ""
lib_check_path

# --- Integração: estrutura + inicializadores ---------------------------------
if [[ "$RUN_STRUCTURE" == true && "$DRY_RUN" == false ]]; then
    echo ""
    lib_step "Gerando estrutura e inicializadores (install.sh)"
    if [[ -x "${SCRIPT_DIR}/install.sh" ]]; then
        "${SCRIPT_DIR}/install.sh" --force || lib_warn "install.sh retornou erro — verifique acima"
    else
        lib_warn "install.sh não encontrado/executável em ${SCRIPT_DIR}"
    fi
elif [[ "$RUN_STRUCTURE" == true && "$DRY_RUN" == true ]]; then
    echo ""
    lib_warn "[dry] chamaria: ${SCRIPT_DIR}/install.sh --force"
fi

echo ""
lib_step "Concluído"
echo "Próximos passos: ./publish.sh  →  ~/run-creality-print.sh  /  ~/run-orca-slicer.sh"
echo ""
exit $rc
