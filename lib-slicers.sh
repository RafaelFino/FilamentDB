#!/usr/bin/env bash
#
# lib-slicers.sh — Biblioteca comum para install-slicers.sh e update-slicers.sh.
#
# Centraliza a lógica "esperta" de resolução/instalação dos slicers via GitHub
# Releases oficiais:
#   - Creality Print: CrealityOfficial/CrealityPrint
#   - Orca Slicer:     SoftFever/OrcaSlicer
#
# Fonte de verdade: GitHub Releases (URLs determinísticas e versionadas, mesmo
# binário do site oficial). O site creality.com/download é dinâmico e não é
# automatizável de forma robusta — por isso usamos o GitHub oficial da Creality.
#
# Este arquivo é SOURCED, não executado diretamente. Não tem `set -e` próprio;
# quem faz source define suas políticas. As funções retornam status via return.

# --- Configuração de repositórios/assets -------------------------------------

CP_REPO="CrealityOfficial/CrealityPrint"
# Asset x86_64 Release AppImage: CrealityPrint-V<ver>.<build>-x86_64-Release.AppImage
CP_ASSET_REGEX='CrealityPrint-V.*x86_64.*Release\.AppImage$'

ORCA_REPO="SoftFever/OrcaSlicer"
# Asset Ubuntu 24.04 x86_64 (exclui aarch64):
#   OrcaSlicer_Linux_AppImage_Ubuntu2404_V<ver>.AppImage
ORCA_ASSET_REGEX='OrcaSlicer_Linux_AppImage_Ubuntu2404_V.*\.AppImage$'
ORCA_ASSET_EXCLUDE='aarch64'

# Diretórios de instalação (sem sudo). Sobrescrevíveis por ambiente.
APPS_DIR="${SLICER_APPS_DIR:-${HOME}/Applications}"
BIN_DIR="${SLICER_BIN_DIR:-${HOME}/.local/bin}"
OLD_DIR="${APPS_DIR}/old"

# Nomes dos symlinks estáveis no PATH
CP_LINK="${BIN_DIR}/creality-print"
ORCA_LINK="${BIN_DIR}/orca-slicer"

# --- Cores (só define se ainda não vieram do script pai) ---------------------

: "${GREEN:=\033[0;32m}"
: "${YELLOW:=\033[1;33m}"
: "${RED:=\033[0;31m}"
: "${CYAN:=\033[0;36m}"
: "${BOLD:=\033[1m}"
: "${NC:=\033[0m}"

lib_info() { echo -e "${GREEN}[OK]${NC}   $*"; }
lib_warn() { echo -e "${YELLOW}[!]${NC}   $*"; }
lib_err()  { echo -e "${RED}[ERRO]${NC} $*" >&2; }
lib_step() { echo -e "${CYAN}${BOLD}»${NC} ${BOLD}$*${NC}"; }

# --- Dependências ------------------------------------------------------------

lib_require_tools() {
    local missing=()
    local t
    for t in curl jq; do
        command -v "$t" >/dev/null 2>&1 || missing+=("$t")
    done
    if (( ${#missing[@]} > 0 )); then
        lib_err "Ferramentas ausentes: ${missing[*]} (instale com: sudo apt install ${missing[*]})"
        return 1
    fi
    return 0
}

# --- Normalização de versão --------------------------------------------------
# Extrai um número de versão comparável (ex.: 7.3.0.6157 ou 2.4.2) de um nome
# de asset ou tag. Usado com sort -V.

lib_version_from_string() {
    # Pega a primeira sequência tipo X.Y[.Z[.W]] após um 'V' ou no texto.
    echo "$1" | grep -oE '[0-9]+(\.[0-9]+){1,3}' | head -1
}

# Compara duas versões. Retorna 0 se $1 > $2, 1 caso contrário (igual ou menor).
lib_version_gt() {
    local a="$1" b="$2"
    [[ -z "$b" ]] && return 0            # nada instalado → remoto é "maior"
    [[ "$a" == "$b" ]] && return 1
    local greatest
    greatest=$(printf '%s\n%s\n' "$a" "$b" | sort -V | tail -1)
    [[ "$greatest" == "$a" ]]
}

# --- Consulta à GitHub Releases API ------------------------------------------
# Resolve o asset mais recente de um repo. Imprime "NOME<TAB>URL<TAB>VERSAO".
# Escolhe, dentro da release mais recente, o asset que casa o regex (e, no caso
# do Creality, o maior build por sort -V).

lib_resolve_latest_asset() {
    local repo="$1" asset_regex="$2" exclude="${3:-}"
    local api="https://api.github.com/repos/${repo}/releases/latest"
    local json
    json=$(curl -fsSL -H "Accept: application/vnd.github+json" "$api" 2>/dev/null) || {
        lib_err "Falha ao consultar GitHub API: $repo"
        return 1
    }

    # Filtra assets por regex, exclui o padrão de exclusão, ordena por versão.
    local filter='.assets[] | select(.name | test($re))'
    [[ -n "$exclude" ]] && filter+=' | select(.name | test($ex) | not)'

    local best
    best=$(echo "$json" | jq -r --arg re "$asset_regex" --arg ex "$exclude" \
        "[ $filter ] | .[] | .name + \"\t\" + .browser_download_url" 2>/dev/null \
        | sort -V | tail -1)

    if [[ -z "$best" ]]; then
        lib_err "Nenhum asset casando /$asset_regex/ na release mais recente de $repo"
        return 1
    fi

    local name url ver
    name=$(echo "$best" | cut -f1)
    url=$(echo "$best" | cut -f2)
    ver=$(lib_version_from_string "$name")
    printf '%s\t%s\t%s\n' "$name" "$url" "$ver"
}

# --- Detecção da versão instalada --------------------------------------------
# Lê a versão a partir do nome do AppImage apontado pelo symlink (ou dos arquivos
# em APPS_DIR). Imprime a versão ou vazio.

lib_installed_version() {
    local link="$1" prefix_regex="$2"
    local target=""
    if [[ -L "$link" ]]; then
        target=$(readlink -f "$link" 2>/dev/null)
    elif [[ -e "$link" ]]; then
        target="$link"
    fi
    if [[ -n "$target" ]]; then
        local v
        v=$(lib_version_from_string "$(basename "$target")")
        if [[ -n "$v" ]]; then echo "$v"; return 0; fi
    fi
    # Fallback: maior versão entre AppImages/binários que casam o prefixo em
    # qualquer diretório conhecido (novo layout + legado).
    local -a search_dirs=(
        "$APPS_DIR" "$OLD_DIR"
        "${HOME}/orca" "${HOME}/Downloads" "/opt"
    )
    local d f latest=""
    for d in "${search_dirs[@]}"; do
        [[ -d "$d" ]] || continue
        for f in "$d"/*.AppImage "$d"/*.appimage; do
            [[ -e "$f" ]] || continue
            [[ "$(basename "$f")" =~ $prefix_regex ]] || continue
            latest=$(printf '%s\n%s\n' "$latest" "$(lib_version_from_string "$(basename "$f")")" | sort -V | tail -1)
        done
    done
    echo "$latest"
}

# --- Download + instalação de um AppImage ------------------------------------
# Baixa a URL para APPS_DIR com o nome do asset, torna executável, rotaciona o
# AppImage anterior apontado pelo symlink para OLD_DIR e recria o symlink.
# Respeita DRY_RUN (variável do script pai).

lib_install_appimage() {
    local name="$1" url="$2" link="$3"
    local dest="${APPS_DIR}/${name}"

    if [[ "${DRY_RUN:-false}" == true ]]; then
        lib_warn "[dry] baixaria: $url"
        lib_warn "[dry]   → $dest"
        lib_warn "[dry] symlink: $link → $dest"
        return 0
    fi

    mkdir -p "$APPS_DIR" "$BIN_DIR" "$OLD_DIR"

    # Rotaciona o AppImage anterior (o alvo atual do symlink), se existir e for
    # diferente do novo.
    local prev=""
    [[ -L "$link" ]] && prev=$(readlink -f "$link" 2>/dev/null)
    if [[ -n "$prev" && -e "$prev" && "$prev" != "$dest" ]]; then
        mv -f "$prev" "${OLD_DIR}/" 2>/dev/null && \
            lib_info "versão anterior arquivada: ${OLD_DIR}/$(basename "$prev")"
    fi

    lib_step "Baixando ${name}"
    local tmp="${dest}.part"
    if ! curl -fL --progress-bar -o "$tmp" "$url"; then
        lib_err "download falhou: $url"
        rm -f "$tmp"
        return 1
    fi
    mv -f "$tmp" "$dest"
    chmod +x "$dest"
    ln -sfn "$dest" "$link"
    lib_info "instalado: ${dest/#$HOME/\~}"
    lib_info "symlink:   ${link/#$HOME/\~} → $(basename "$dest")"
    return 0
}

# --- Reconciliação do symlink com um AppImage já presente --------------------
# Quando a versão instalada já é a mais recente mas o symlink padrão não aponta
# para um AppImage válido (ex.: slicer no layout legado ~/orca), localiza o
# AppImage da versão corrente e cria/corrige o symlink — padronizando o layout
# sem baixar nada.
# Respeita DRY_RUN. Retorna 0 sempre (reconciliação é best-effort).
lib_reconcile_symlink() {
    local link="$1" prefix_regex="$2" want_ver="$3"

    # Se o symlink já aponta para um arquivo existente, nada a fazer.
    if [[ -L "$link" && -e "$(readlink -f "$link" 2>/dev/null)" ]]; then
        return 0
    fi
    [[ -z "$want_ver" ]] && return 0

    # Procura o AppImage da versão corrente nos diretórios conhecidos.
    local -a search_dirs=(
        "$APPS_DIR" "$OLD_DIR" "${HOME}/orca" "${HOME}/Downloads" "/opt"
    )
    local d f match=""
    for d in "${search_dirs[@]}"; do
        [[ -d "$d" ]] || continue
        for f in "$d"/*.AppImage "$d"/*.appimage; do
            [[ -e "$f" ]] || continue
            [[ "$(basename "$f")" =~ $prefix_regex ]] || continue
            [[ "$(lib_version_from_string "$(basename "$f")")" == "$want_ver" ]] || continue
            match="$f"; break 2
        done
    done
    [[ -z "$match" ]] && return 0

    if [[ "${DRY_RUN:-false}" == true ]]; then
        lib_warn "[dry] symlink: ${link/#$HOME/\~} → ${match/#$HOME/\~}"
        return 0
    fi
    mkdir -p "$BIN_DIR"
    chmod +x "$match" 2>/dev/null || true
    ln -sfn "$match" "$link"
    lib_info "symlink padronizado: ${link/#$HOME/\~} → $(basename "$match")"
    return 0
}

# --- Garantia de que BIN_DIR está no PATH ------------------------------------

lib_check_path() {
    case ":${PATH}:" in
        *":${BIN_DIR}:"*) return 0 ;;
        *) lib_warn "${BIN_DIR} não está no PATH — adicione ao seu ~/.zshrc: export PATH=\"${BIN_DIR}:\$PATH\"" ;;
    esac
}

# --- Orquestração por slicer -------------------------------------------------
# Processa um slicer: resolve a latest, compara com a instalada e instala
# conforme a política.
#
# Args: display_name repo asset_regex asset_exclude link prefix_regex mode
#   mode = "install" | "update"
#     install: instala se não houver nada OU se --force; se já na latest, pula.
#     update:  instala somente se a remota for MAIOR que a instalada.
#
# Variáveis do pai respeitadas: DRY_RUN, FORCE, CHECK_ONLY.
# Retorna 0 em sucesso/no-op, 1 em erro.

lib_process_slicer() {
    local display="$1" repo="$2" regex="$3" exclude="$4" link="$5" prefix_regex="$6" mode="$7"

    lib_step "${display}"

    local resolved
    resolved=$(lib_resolve_latest_asset "$repo" "$regex" "$exclude") || return 1
    local remote_name remote_url remote_ver
    remote_name=$(echo "$resolved" | cut -f1)
    remote_url=$(echo "$resolved" | cut -f2)
    remote_ver=$(echo "$resolved" | cut -f3)

    local installed_ver
    installed_ver=$(lib_installed_version "$link" "$prefix_regex")

    lib_info "instalada: ${installed_ver:-<nenhuma>}   |   mais recente: ${remote_ver}"

    # Modo --check: só reporta, nunca instala.
    if [[ "${CHECK_ONLY:-false}" == true ]]; then
        if lib_version_gt "$remote_ver" "$installed_ver"; then
            lib_warn "atualização disponível: ${installed_ver:-<nenhuma>} → ${remote_ver}"
        else
            lib_info "já na versão mais recente"
        fi
        return 0
    fi

    # Decisão de instalar
    local do_install=false reason=""
    if [[ "${FORCE:-false}" == true ]]; then
        do_install=true; reason="--force"
    elif [[ -z "$installed_ver" ]]; then
        do_install=true; reason="nada instalado"
    elif lib_version_gt "$remote_ver" "$installed_ver"; then
        do_install=true; reason="versão mais nova disponível"
    fi

    if [[ "$mode" == "update" && "$do_install" == true && "${FORCE:-false}" != true && -z "$installed_ver" ]]; then
        # update numa máquina sem o slicer: ainda instala (bootstrap), mas avisa.
        lib_warn "slicer ausente — instalando do zero"
    fi

    if [[ "$do_install" != true ]]; then
        lib_info "já na versão mais recente"
        # Mesmo sem baixar, garante o symlink padrão apontando para o AppImage
        # corrente (padroniza o layout legado sem reinstalar).
        lib_reconcile_symlink "$link" "$prefix_regex" "$installed_ver"
        return 0
    fi

    lib_info "ação: instalar (${reason})"
    lib_install_appimage "$remote_name" "$remote_url" "$link" || return 1
    return 0
}

# Atalhos nomeados para os dois slicers conhecidos.
lib_process_creality() {
    local mode="$1"
    lib_process_slicer "Creality Print" "$CP_REPO" "$CP_ASSET_REGEX" "" \
        "$CP_LINK" 'CrealityPrint-V.*x86_64' "$mode"
}
lib_process_orca() {
    local mode="$1"
    lib_process_slicer "Orca Slicer" "$ORCA_REPO" "$ORCA_ASSET_REGEX" "$ORCA_ASSET_EXCLUDE" \
        "$ORCA_LINK" 'OrcaSlicer_Linux_AppImage_Ubuntu2404_V' "$mode"
}
