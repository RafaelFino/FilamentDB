#!/usr/bin/env bash
#
# update-slicers.sh — Mantém Creality Print e OrcaSlicer sempre na versão mais
# recente, sem intervenção manual.
#
# Compara a versão instalada (lida do AppImage apontado pelo symlink) com a
# mais recente nas GitHub Releases oficiais e atualiza SOMENTE se houver versão
# nova. A versão anterior é arquivada em ~/Applications/old/.
#
# Uso:
#   ./update-slicers.sh              # atualiza o que estiver desatualizado
#   ./update-slicers.sh --check      # só reporta, não baixa (dry de verdade)
#   ./update-slicers.sh --only orca  # só um slicer (creality|orca)
#   ./update-slicers.sh --dry-run    # mostra o que faria, sem baixar/escrever
#   ./update-slicers.sh --no-structure  # não regenera runners após atualizar
#   ./update-slicers.sh --help
#
# Diferença entre --check e --dry-run:
#   --check    só consulta e reporta se há atualização (nunca escreve).
#   --dry-run  simula a atualização inteira (incl. decisão de instalar).

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
        --check)        CHECK_ONLY=true; shift ;;
        --dry-run)      DRY_RUN=true; shift ;;
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
if [[ "$CHECK_ONLY" == true ]]; then
    lib_step "FilamentDB — verificação de atualização dos slicers (--check)"
else
    lib_step "FilamentDB — atualização dos slicers"
    [[ "$DRY_RUN" == true ]] && lib_warn "modo --dry-run: nada será baixado/escrito"
fi
echo ""

lib_require_tools || exit 1

rc=0
case "$ONLY" in
    creality) lib_process_creality update || rc=1 ;;
    orca)     lib_process_orca update || rc=1 ;;
    "")
        lib_process_creality update || rc=1
        echo ""
        lib_process_orca update || rc=1
        ;;
    *) lib_err "Valor inválido para --only: $ONLY (use creality|orca)"; exit 1 ;;
esac

# --- Integração: regenerar inicializadores após atualizar --------------------
# Só faz sentido fora do modo --check (que não altera nada). Regenera os runners
# para que o ORCA_APPIMAGE aponte para o AppImage novo.
if [[ "$CHECK_ONLY" != true && "$RUN_STRUCTURE" == true && "$DRY_RUN" == false ]]; then
    echo ""
    lib_step "Regenerando inicializadores (install.sh)"
    if [[ -x "${SCRIPT_DIR}/install.sh" ]]; then
        "${SCRIPT_DIR}/install.sh" --force || lib_warn "install.sh retornou erro — verifique acima"
    else
        lib_warn "install.sh não encontrado/executável em ${SCRIPT_DIR}"
    fi
fi

echo ""
lib_step "Concluído"
echo ""
exit $rc
