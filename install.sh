#!/usr/bin/env bash
#
# install.sh — Bootstrap da estrutura local do FilamentDB numa máquina nova.
#
# Faz, de forma idempotente:
#   1. Detecta os slicers instalados (Creality Print e/ou OrcaSlicer).
#   2. Cria a árvore ~/filament-db/ (destino de publicação do publish.sh).
#   3. Gera os inicializadores ~/run-creality-print.sh e ~/run-orca-slicer.sh,
#      que sincronizam os perfis publicados para o diretório de usuário do
#      slicer e abrem o aplicativo.
#
# Os inicializadores gerados detectam SOZINHOS, em runtime:
#   - Creality Print: a versão mais recente (sort -V) e o user id numérico.
#   - Orca Slicer:     agrega a raiz (K2) + subpastas de device (cc2, ...).
# Portanto este instalador não hardcoda versões — só resolve o binário/AppImage.
#
# Uso:
#   ./install.sh            # detecta, cria estrutura e gera inicializadores
#   ./install.sh --dry-run  # mostra o que faria, sem escrever nada
#   ./install.sh --force    # sobrescreve inicializadores sem perguntar
#   ./install.sh --help

set -euo pipefail

# --- Configuração ------------------------------------------------------------

DB_ROOT="${FILAMENT_DB_ROOT:-${HOME}/filament-db}"
CP_RUNNER="${HOME}/run-creality-print.sh"
ORCA_RUNNER="${HOME}/run-orca-slicer.sh"

# Candidatos de binário/AppImage por slicer. O primeiro que existir vence.
# Layout padrão (gerenciado por install-slicers.sh): ~/.local/bin + ~/Applications.
# Os caminhos legados (/usr/local/bin, ~/orca) ficam só como fallback.
CP_BIN_CANDIDATES=(
    "$(command -v creality-print 2>/dev/null || true)"
    "${HOME}/.local/bin/creality-print"
    "/usr/local/bin/creality-print"
    "/usr/bin/creality-print"
    "/opt/creality-print/creality-print"
)
ORCA_GLOB_DIRS=(
    "${HOME}/.local/bin"
    "${HOME}/Applications"
    "${HOME}/orca"
    "${HOME}/Downloads"
    "/opt"
)

# --- Cores -------------------------------------------------------------------

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

info()  { echo -e "${GREEN}[OK]${NC}   $*"; }
warn()  { echo -e "${YELLOW}[!]${NC}   $*"; }
err()   { echo -e "${RED}[ERRO]${NC} $*" >&2; }
step()  { echo -e "${CYAN}${BOLD}»${NC} ${BOLD}$*${NC}"; }

# --- Args --------------------------------------------------------------------

DRY_RUN=false
FORCE=false
while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run) DRY_RUN=true; shift ;;
        --force)   FORCE=true; shift ;;
        --help|-h)
            cat <<EOF
Uso: $0 [opções]

Opções:
  --dry-run   Mostra o que seria feito, sem escrever nada
  --force     Sobrescreve inicializadores existentes sem perguntar
  --help      Mostra esta ajuda

Variáveis de ambiente:
  FILAMENT_DB_ROOT   Raiz da publicação local (default: ~/filament-db)
EOF
            exit 0
            ;;
        *) err "Argumento desconhecido: $1"; exit 1 ;;
    esac
done

run() {
    # Executa um comando, ou apenas o descreve em dry-run.
    if [[ "$DRY_RUN" == true ]]; then
        echo -e "   ${YELLOW}[dry]${NC} $*"
    else
        eval "$@"
    fi
}

# --- Detecção: Creality Print ------------------------------------------------

detect_creality_bin() {
    local c
    for c in "${CP_BIN_CANDIDATES[@]}"; do
        [[ -n "$c" && -x "$c" ]] && { echo "$c"; return 0; }
    done
    return 1
}

detect_creality_config_base() {
    local base="${HOME}/.config/Creality/Creality Print"
    [[ -d "$base" ]] && { echo "$base"; return 0; }
    return 1
}

# --- Detecção: OrcaSlicer ----------------------------------------------------

detect_orca_appimage() {
    # Procura o AppImage mais recente (maior versão no nome / mtime) nos dirs
    # candidatos. O nome embute a versão, então não dá pra fixar.
    local d found
    local -a hits=()
    for d in "${ORCA_GLOB_DIRS[@]}"; do
        [[ -d "$d" ]] || continue
        while IFS= read -r found; do
            hits+=("$found")
        done < <(find "$d" -maxdepth 2 -iname '*OrcaSlicer*.AppImage' -type f 2>/dev/null)
    done
    # Fallback: binário instalado no PATH
    local pathbin
    pathbin="$(command -v orca-slicer 2>/dev/null || command -v OrcaSlicer 2>/dev/null || true)"
    [[ -n "$pathbin" ]] && hits+=("$pathbin")

    [[ ${#hits[@]} -eq 0 ]] && return 1

    # Ordena por versão embutida no nome; o último é o mais novo.
    printf '%s\n' "${hits[@]}" | sort -V | tail -1
}

detect_orca_config_dir() {
    local d="${HOME}/.config/OrcaSlicer/user/default"
    [[ -d "${HOME}/.config/OrcaSlicer" ]] && { echo "$d"; return 0; }
    return 1
}

# --- Geração: árvore ~/filament-db -------------------------------------------

create_db_tree() {
    step "Criando árvore em ${DB_ROOT}"
    local -a dirs=(
        "${DB_ROOT}/creality-print/filament"
        "${DB_ROOT}/creality-print/process"
        "${DB_ROOT}/orca/filament"
        "${DB_ROOT}/orca/process"
        "${DB_ROOT}/backups"
        "${DB_ROOT}/diff"
    )
    local d
    for d in "${dirs[@]}"; do
        if [[ -d "$d" ]]; then
            info "existe: ${d/#$HOME/\~}"
        else
            run "mkdir -p \"$d\""
            if [[ "$DRY_RUN" == false ]]; then info "criado: ${d/#$HOME/\~}"; fi
        fi
    done
    echo "   (subpastas de device do Orca, ex.: orca/cc2/, são criadas pelo publish.sh)"
}

# --- Geração: backup de um arquivo antes de sobrescrever ---------------------

backup_if_exists() {
    local f="$1"
    [[ -f "$f" ]] || return 0
    if [[ "$FORCE" == true ]]; then
        return 0
    fi
    local bak="${f}.bak.$(date +%Y%m%d_%H%M%S)"
    run "cp \"$f\" \"$bak\""
    if [[ "$DRY_RUN" == false ]]; then
        warn "backup do antigo: ${bak/#$HOME/\~}"
    fi
    return 0
}

# --- Geração: inicializador do Creality Print --------------------------------

write_creality_runner() {
    local cp_bin="$1"
    step "Gerando ${CP_RUNNER/#$HOME/\~}"
    backup_if_exists "$CP_RUNNER"
    if [[ "$DRY_RUN" == true ]]; then
        echo -e "   ${YELLOW}[dry]${NC} escreveria $CP_RUNNER (bin: ${cp_bin})"
        return 0
    fi
    cat > "$CP_RUNNER" <<'RUNNER_EOF'
#!/bin/zsh
#
# run-creality-print.sh — Sincroniza perfis do FilamentDB e abre o Creality Print.
# GERADO por install.sh. Detecta a versão e o user id em runtime.
#

FILAMENT_SRC="${HOME}/filament-db/creality-print/filament"
PROCESS_SRC="${HOME}/filament-db/creality-print/process"
DIFF_DIR="${HOME}/filament-db/diff"
CP_BASE="${HOME}/.config/Creality/Creality Print"

DATE_SUFFIX=$(date +%Y%m%d)

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()  { echo -e "${GREEN}[OK]${NC} $*"; }
warn()  { echo -e "${YELLOW}[!]${NC}  $*"; }
err()   { echo -e "${RED}[ERRO]${NC} $*" >&2; }

detect_cp_version() {
    find "$CP_BASE" -maxdepth 1 -type d -regextype posix-extended \
        -regex '.*/[0-9]+\.[0-9]+' -printf '%f\n' 2>/dev/null \
        | sort -V | tail -1
}
detect_cp_user() {
    local user_base="$1"
    find "$user_base" -maxdepth 1 -type d -regextype posix-extended \
        -regex '.*/[0-9]+' -printf '%T@\t%f\n' 2>/dev/null \
        | sort -rn | head -1 | cut -f2
}

if [[ ! -d "$FILAMENT_SRC" ]]; then
    err "$FILAMENT_SRC não encontrado. Rode publish.sh primeiro."
    exit 1
fi
if [[ ! -d "$CP_BASE" ]]; then
    err "Creality Print não encontrado em: $CP_BASE"
    exit 1
fi

CP_VERSION=$(detect_cp_version)
if [[ -z "$CP_VERSION" ]]; then
    err "Nenhuma versão X.Y do Creality Print encontrada em $CP_BASE"
    exit 1
fi
CP_USER_BASE="${CP_BASE}/${CP_VERSION}/user"
CP_USER_ID=$(detect_cp_user "$CP_USER_BASE")
if [[ -z "$CP_USER_ID" ]]; then
    err "Nenhum user id numérico encontrado em $CP_USER_BASE"
    exit 1
fi

CP_USER_DIR="${CP_USER_BASE}/${CP_USER_ID}"
FILAMENT_DST="${CP_USER_DIR}/filament"
PROCESS_DST="${CP_USER_DIR}/process"
info "Creality Print alvo: versão ${CP_VERSION}, user ${CP_USER_ID}"

mkdir -p "$FILAMENT_DST" "$PROCESS_DST" "$DIFF_DIR"

archive_orphans() {
    local src_dir="$1" dst_dir="$2" label="$3" moved=0
    for dst_file in "$dst_dir"/*.json(N) "$dst_dir"/*.info(N); do
        [[ -f "$dst_file" ]] || continue
        local base="${dst_file:t}" ext="${dst_file:t:e}" name="${dst_file:t:r}"
        if [[ ! -f "$src_dir/$base" ]]; then
            mv "$dst_file" "$DIFF_DIR/${name}_${DATE_SUFFIX}.${ext}"
            moved=$((moved + 1))
        fi
    done
    (( moved > 0 )) && warn "${label}: ${moved} perfis órfãos arquivados em ~/filament-db/diff/"
}

archive_orphans "$FILAMENT_SRC" "$FILAMENT_DST" "Filamentos"
archive_orphans "$PROCESS_SRC" "$PROCESS_DST" "Processos"

find "$FILAMENT_DST" -maxdepth 1 -type f \( -name "*.json" -o -name "*.info" \) -delete
cp "$FILAMENT_SRC"/* "$FILAMENT_DST/"
info "Filamentos: $(find "$FILAMENT_DST" -maxdepth 1 -name '*.json' -type f | wc -l) perfis sincronizados"

find "$PROCESS_DST" -maxdepth 1 -type f \( -name "*.json" -o -name "*.info" \) -delete
cp "$PROCESS_SRC"/*.json "$PROCESS_DST/"
info "Processos: $(find "$PROCESS_DST" -maxdepth 1 -name '*.json' -type f | wc -l) perfis sincronizados"

echo ""
info "Abrindo Creality Print..."
RUNNER_EOF
    # Injeta o exec com o caminho resolvido do binário (não depende do PATH).
    printf 'exec "%s" "$@"\n' "$cp_bin" >> "$CP_RUNNER"
    chmod 755 "$CP_RUNNER"
    info "gerado e executável: ${CP_RUNNER/#$HOME/\~}"
}

# --- Geração: inicializador do Orca Slicer -----------------------------------

write_orca_runner() {
    local appimage="$1"
    step "Gerando ${ORCA_RUNNER/#$HOME/\~}"
    backup_if_exists "$ORCA_RUNNER"
    if [[ "$DRY_RUN" == true ]]; then
        echo -e "   ${YELLOW}[dry]${NC} escreveria $ORCA_RUNNER (AppImage: ${appimage:-<não detectado>})"
        return 0
    fi
    # Injeta o caminho do AppImage detectado (ou um placeholder a corrigir).
    local orca_exec="${appimage:-${HOME}/orca/OrcaSlicer.AppImage  # <-- AJUSTE: AppImage não detectado}"
    cat > "$ORCA_RUNNER" <<RUNNER_EOF
#!/bin/zsh
#
# run-orca-slicer.sh — Sincroniza perfis do FilamentDB e abre o Orca Slicer.
# GERADO por install.sh. Agrega raiz (K2) + subpastas de device (cc2, ...).
#

ORCA_ROOT="\${HOME}/filament-db/orca"
FILAMENT_SRC="\${ORCA_ROOT}/filament"
PROCESS_SRC="\${ORCA_ROOT}/process"
DIFF_DIR="\${HOME}/filament-db/diff"
ORCA_USER_DIR="\${HOME}/.config/OrcaSlicer/user/default"
FILAMENT_DST="\${ORCA_USER_DIR}/filament"
PROCESS_DST="\${ORCA_USER_DIR}/process"
ORCA_APPIMAGE="${orca_exec}"

DATE_SUFFIX=\$(date +%Y%m%d)

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()  { echo -e "\${GREEN}[OK]\${NC} \$*"; }
warn()  { echo -e "\${YELLOW}[!]\${NC}  \$*"; }
err()   { echo -e "\${RED}[ERRO]\${NC} \$*" >&2; }

if [[ ! -d "\$FILAMENT_SRC" ]]; then
    err "\$FILAMENT_SRC não encontrado. Rode publish.sh primeiro."
    exit 1
fi
mkdir -p "\$FILAMENT_DST" "\$PROCESS_DST" "\$DIFF_DIR"

collect_sources() {
    local kind="\$1"
    local -a dirs
    dirs=("\${ORCA_ROOT}/\${kind}")
    local sub
    for sub in "\${ORCA_ROOT}"/*/"\${kind}"(N/); do
        dirs+=("\${sub%/}")
    done
    print -l -- "\${dirs[@]}"
}

archive_orphans() {
    local dst_dir="\$1" label="\$2"; shift 2
    local -a src_dirs=("\$@") ; local moved=0 dst_file
    for dst_file in "\$dst_dir"/*.json(N); do
        [[ -f "\$dst_file" ]] || continue
        local base="\${dst_file:t}" ext="\${dst_file:t:e}" name="\${dst_file:t:r}"
        local found=0 src
        for src in "\${src_dirs[@]}"; do
            [[ -f "\${src}/\${base}" ]] && { found=1; break; }
        done
        if (( ! found )); then
            mv "\$dst_file" "\$DIFF_DIR/\${name}_orca_\${DATE_SUFFIX}.\${ext}"
            moved=\$((moved + 1))
        fi
    done
    (( moved > 0 )) && warn "\${label}: \${moved} perfis órfãos arquivados em ~/filament-db/diff/"
}

sync_kind() {
    local kind="\$1" dst_dir="\$2" label="\$3"; shift 3
    local -a src_dirs=("\$@") ; local src
    find "\$dst_dir" -maxdepth 1 -type f -name "*.json" -delete
    for src in "\${src_dirs[@]}"; do
        cp "\$src"/*.json(N) "\$dst_dir/" 2>/dev/null
    done
    info "\${label}: \$(find "\$dst_dir" -maxdepth 1 -name '*.json' -type f | wc -l) perfis sincronizados"
}

FILAMENT_SRCS=("\${(@f)\$(collect_sources filament)}")
PROCESS_SRCS=("\${(@f)\$(collect_sources process)}")
info "Fontes de filamento: \${#FILAMENT_SRCS[@]} (raiz + devices)"
info "Fontes de processo:  \${#PROCESS_SRCS[@]} (raiz + devices)"

archive_orphans "\$FILAMENT_DST" "Filamentos Orca" "\${FILAMENT_SRCS[@]}"
archive_orphans "\$PROCESS_DST" "Processos Orca" "\${PROCESS_SRCS[@]}"
sync_kind filament "\$FILAMENT_DST" "Filamentos" "\${FILAMENT_SRCS[@]}"
sync_kind process "\$PROCESS_DST" "Processos" "\${PROCESS_SRCS[@]}"

echo ""
info "Abrindo Orca Slicer..."
exec "\$ORCA_APPIMAGE" "\$@"
RUNNER_EOF
    chmod 755 "$ORCA_RUNNER"
    info "gerado e executável: ${ORCA_RUNNER/#$HOME/\~}"
}

# --- Execução ----------------------------------------------------------------

echo ""
step "FilamentDB — instalador de estrutura local"
[[ "$DRY_RUN" == true ]] && warn "modo --dry-run: nada será escrito"
echo ""

# 1) Detecção
step "Detectando slicers"
CP_BIN=""; CP_CFG=""
if CP_BIN=$(detect_creality_bin); then
    info "Creality Print: binário em ${CP_BIN}"
    if CP_CFG=$(detect_creality_config_base); then
        info "  config base: ${CP_CFG/#$HOME/\~}"
    else
        warn "  config ainda não existe (slicer nunca aberto?) — o inicializador detecta em runtime"
    fi
else
    warn "Creality Print não encontrado (binário)."
fi

ORCA_APP=""; ORCA_CFG=""
if ORCA_APP=$(detect_orca_appimage); then
    info "Orca Slicer: ${ORCA_APP/#$HOME/\~}"
    if ORCA_CFG=$(detect_orca_config_dir); then
        info "  config: ${ORCA_CFG/#$HOME/\~}"
    else
        warn "  config ainda não existe (slicer nunca aberto?)"
    fi
else
    warn "Orca Slicer não encontrado (AppImage/binário)."
fi

if [[ -z "$CP_BIN" && -z "$ORCA_APP" ]]; then
    err "Nenhum slicer detectado. Instale Creality Print e/ou OrcaSlicer antes."
    exit 1
fi
echo ""

# 2) Árvore
create_db_tree
echo ""

# 3) Inicializadores (só do que foi detectado)
if [[ -n "$CP_BIN" ]]; then
    write_creality_runner "$CP_BIN"
    echo ""
fi
if [[ -n "$ORCA_APP" ]]; then
    write_orca_runner "$ORCA_APP"
    echo ""
fi

# --- Resumo ------------------------------------------------------------------

echo "==========================================="
step "Instalação concluída"
echo "==========================================="
if [[ -n "$CP_BIN" ]];  then info "Creality Print: ${CP_RUNNER/#$HOME/\~}"; fi
if [[ -n "$ORCA_APP" ]]; then info "Orca Slicer:    ${ORCA_RUNNER/#$HOME/\~}"; fi
echo ""
echo "Próximos passos:"
echo "  1. Rode o build+publish:   ./publish.sh"
echo "  2. Sincronize e abra:      ~/run-creality-print.sh  /  ~/run-orca-slicer.sh"
if [[ -z "$ORCA_APP" ]]; then warn "Orca não detectado — ajuste ORCA_APPIMAGE no inicializador se instalar depois."; fi
echo ""
