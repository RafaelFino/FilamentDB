#!/usr/bin/env bash
#
# sync-printer.sh — Sincroniza perfis de filamento com a impressora K2 via SSH
#
# Usa o go-filament-sync (https://github.com/zaggash/go-filament-sync) para
# enviar os perfis exportados para o banco interno da impressora/CFS.
#
# Uso:
#   ./sync-printer.sh                    # Auto-descobre a K2 na rede via mDNS
#   ./sync-printer.sh 192.168.0.6        # IP específico (pula discovery)
#   ./sync-printer.sh --help             # Ajuda
#
# Pré-requisitos:
#   - Impressora com SSH habilitado (ativar em Settings > Root Access)
#   - Rede local com acesso à impressora
#   - avahi-utils instalado para auto-discovery (opcional)
#

set -euo pipefail

# ─── Configuração ────────────────────────────────────────────────────────────

PRINTER_IP="${1:-}"
PRINTER_USER="${PRINTER_USER:-root}"
PRINTER_PASS="${PRINTER_PASS:-creality_2024}"
PRINTER_HOSTNAME="K2-88EA"

# Caminho dos perfis exportados pelo build.py
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROFILE_PATH="${SCRIPT_DIR}/Creality-Print/filaments"

# Binário do go-filament-sync
TOOL_DIR="${SCRIPT_DIR}/.tools"
TOOL_BIN="${TOOL_DIR}/filament-sync-tool"
TOOL_VERSION="1.0.0"
TOOL_URL="https://github.com/zaggash/go-filament-sync/releases/download/${TOOL_VERSION}/filament-sync-tool_linux_amd64.tar.gz"

# ─── Funções ─────────────────────────────────────────────────────────────────

info()  { echo -e "\033[0;32m[INFO]\033[0m  $*"; }
warn()  { echo -e "\033[1;33m[WARN]\033[0m  $*"; }
error() { echo -e "\033[0;31m[ERROR]\033[0m $*" >&2; exit 1; }

show_help() {
    cat <<EOF
Uso: ./sync-printer.sh [IP_DA_IMPRESSORA]

Sincroniza perfis de filamento com a Creality K2 via SSH.

Se nenhum IP for fornecido, tenta descobrir automaticamente via mDNS (avahi).

Argumentos:
  IP_DA_IMPRESSORA    IP da impressora na rede local (opcional com mDNS)

Variáveis de ambiente:
  PRINTER_USER        Usuário SSH (padrão: root)
  PRINTER_PASS        Senha SSH (padrão: creality_2024)

Exemplos:
  ./sync-printer.sh                      # Auto-discovery via mDNS
  ./sync-printer.sh 192.168.0.6          # IP direto
  PRINTER_PASS=minha_senha ./sync-printer.sh

O binário go-filament-sync é baixado automaticamente na primeira execução.
EOF
    exit 0
}

discover_printer() {
    # Tenta encontrar a K2 na rede via mDNS (avahi-browse)
    if ! command -v avahi-resolve &>/dev/null; then
        return 1
    fi

    info "Procurando impressora ${PRINTER_HOSTNAME} na rede..." >&2

    # Tenta resolver o hostname .local diretamente
    local ip
    ip=$(avahi-resolve -n "${PRINTER_HOSTNAME}.local" 2>/dev/null | awk '{print $2}' | head -1)

    if [[ -n "${ip}" ]]; then
        echo "${ip}"
        return 0
    fi

    # Fallback: busca em todos os serviços Creality
    ip=$(avahi-browse -rpt --all 2>/dev/null \
        | grep -i "creality" \
        | grep "^=" \
        | grep "IPv4" \
        | head -1 \
        | cut -d';' -f8)

    if [[ -n "${ip}" ]]; then
        echo "${ip}"
        return 0
    fi

    return 1
}

download_tool() {
    info "Baixando go-filament-sync v${TOOL_VERSION}..."
    mkdir -p "${TOOL_DIR}"
    local tmp_tar="${TOOL_DIR}/filament-sync-tool.tar.gz"
    curl -fSL --progress-bar -o "${tmp_tar}" "${TOOL_URL}"
    tar -xzf "${tmp_tar}" -C "${TOOL_DIR}"
    rm -f "${tmp_tar}"
    chmod +x "${TOOL_BIN}"
    info "Binário instalado em ${TOOL_BIN}"
}

# ─── Main ────────────────────────────────────────────────────────────────────

[[ "${1:-}" == "--help" || "${1:-}" == "-h" ]] && show_help

# Auto-discovery se IP não foi fornecido
if [[ -z "${PRINTER_IP}" ]]; then
    PRINTER_IP=$(discover_printer) || true
    if [[ -z "${PRINTER_IP}" ]]; then
        error "Impressora não encontrada na rede.\n  Certifique-se que a K2 está ligada e na mesma rede.\n  Ou forneça o IP: ./sync-printer.sh <IP>"
    fi
    info "Impressora encontrada: ${PRINTER_HOSTNAME} @ ${PRINTER_IP}"
fi

# Verificar se os perfis existem
if [[ ! -d "${PROFILE_PATH}" ]]; then
    error "Diretório de perfis não encontrado: ${PROFILE_PATH}\n  Execute 'python3 build.py' primeiro."
fi

file_count=$(find "${PROFILE_PATH}" -name "*.json" | wc -l)
if [[ "${file_count}" -eq 0 ]]; then
    error "Nenhum perfil JSON em ${PROFILE_PATH}\n  Execute 'python3 build.py' primeiro."
fi

# Baixar binário se necessário
if [[ ! -x "${TOOL_BIN}" ]]; then
    download_tool
fi

# Verificar conectividade SSH (ping rápido)
if ! ping -c 1 -W 2 "${PRINTER_IP}" &>/dev/null; then
    warn "Impressora em ${PRINTER_IP} não respondeu ao ping — tentando sync mesmo assim..."
fi

# Executar sync
info "Sincronizando ${file_count} perfis de filamento com ${PRINTER_IP}..."
echo ""

"${TOOL_BIN}" \
    --printer-ip "${PRINTER_IP}" \
    --profile-path "${PROFILE_PATH}" \
    --user "${PRINTER_USER}" \
    --password "${PRINTER_PASS}"

echo ""
info "Sync concluído! Os filamentos devem aparecer na tela da impressora."
info "Se não aparecerem imediatamente, reinicie a impressora."
