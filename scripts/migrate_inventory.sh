#!/usr/bin/env bash
#
# migrate_inventory.sh — Roda a migração do estoque (tipo × cor) com rede de
# segurança: backup, verificação antes/depois, idempotência e rollback guiado.
#
# A migração em si é o init_db() de src/inventory.py (ALTER TABLE das colunas
# color_id/profile_name + backfill CONSERVADOR de profile_name; itens sem
# inferência segura ficam type_missing — nunca adivinha). Ela já roda sozinha no
# startup do app; este script é o jeito manual, auditável, de executá-la (local
# ou no servidor) e PROVAR que nada se perdeu.
#
# Uso:
#   ./scripts/migrate_inventory.sh --dry-run            # ensaio numa CÓPIA em /tmp (original intacto)
#   ./scripts/migrate_inventory.sh                      # real, pede confirmação
#   ./scripts/migrate_inventory.sh --yes                # real, sem perguntar
#   ./scripts/migrate_inventory.sh --db /caminho/inventory.db --dry-run
#
# Flags:
#   --db PATH   Banco alvo (sobrepõe as variáveis abaixo)
#   --dry-run   Trabalha numa cópia temporária; imprime o relatório; não toca o original
#   --yes       Não pede confirmação interativa
#   -h|--help   Esta ajuda
#
# Resolução do banco alvo (primeiro que existir na ordem):
#   --db PATH > FILAMENT_INVENTORY_DB_PATH > <dir de DB_PATH>/inventory.db > <repo>/data/inventory.db
#   (variáveis lidas do ambiente e, se ausentes, de config.env)
#
# Variáveis de ambiente:
#   PYTHON                 Interpretador (default: .venv/bin/python se existir, senão python3)
#   BACKUP_DIR             Diretório de backups (default: FILAMENTDB_BACKUP_DIR ou <repo>/backups)
#   MAX_DB_BACKUPS         Rotação de inventory_premigration_*.db (default: 30, como update-server.sh)
#   CONFIG_ENV             Caminho do config.env (default: <repo>/config.env)
#   MIGRATE_CATALOG_DB     Catálogo (filament.db) lido no backfill; default: filament.db ao lado
#                          do banco alvo, se existir, senão o default da config
#
# O que faz (aborta no 1º problema):
#   1. Backup binário consistente (sqlite3 .backup; fallback cp -p) em
#      <BACKUP_DIR>/inventory_premigration_<ts>.db — se falhar, ABORTA.
#      + dump JSON lógico (scripts/dump_inventory.sh) em <BACKUP_DIR>/inventory-json/
#      (se falhar, avisa e segue: o backup binário é a garantia).
#   2. Snapshot "antes" (schema via PRAGMA, itens, campos não derivados).
#   3. Migração (scripts/verify_inventory_migration.py migrate → init_db()).
#   4. Verificação "depois": mesma contagem (ajustada pelo split de spools>1),
#      mesmos ids/uids, campos preservados idênticos, colunas profile_name/color_id.
#   5. 2ª execução da migração e comparação de fingerprint (idempotência).
#   6. Relatório: total, profile_name inferido, type_missing, com color_id.
#
# Exit 0 só se tudo conferir. Qualquer divergência: exit 1, imprime o comando de
# rollback e MANTÉM o backup.
#
# Serviço: não é parado aqui. SQLite tolera rodar com o serviço ligado, mas o
# ideal é pará-lo (sudo systemctl stop filamentdb filamentdb-api) para a janela
# do backup→migração ser consistente.
#
# ROLLBACK (serviço parado):
#   cp -p <BACKUP_DIR>/inventory_premigration_<ts>.db <banco> && rm -f <banco>-wal <banco>-shm
#   ou restaurar o JSON: ./scripts/restore_inventory.sh --replace <dump.json>
#
# Sugestão de uso no servidor: ./scripts/migrate_inventory.sh --dry-run
# (confere o relatório) e depois ./scripts/migrate_inventory.sh.
#
set -euo pipefail

# ── Cores ──
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*" >&2; }
error() { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

# ── Argumentos ──
DB_ARG=""; DRY_RUN=0; ASSUME_YES=0
while [ $# -gt 0 ]; do
    case "$1" in
        --db)      [ $# -ge 2 ] || error "--db exige um caminho."; DB_ARG="$2"; shift 2 ;;
        --dry-run) DRY_RUN=1; shift ;;
        --yes|-y)  ASSUME_YES=1; shift ;;
        -h|--help) grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) error "Argumento desconhecido: $1 (use --help)" ;;
    esac
done

# ── Config: ambiente primeiro; config.env só preenche o que faltar ──
CONFIG_ENV="${CONFIG_ENV:-${REPO_DIR}/config.env}"
cfg_get() {
    local key="$1" val=""
    if [ -n "${!key:-}" ]; then printf '%s' "${!key}"; return 0; fi
    if [ -f "$CONFIG_ENV" ]; then
        val=$(grep -E "^[[:space:]]*(export[[:space:]]+)?${key}=" "$CONFIG_ENV" | tail -n1 \
              | sed -E "s/^[^=]*=//; s/^[\"']//; s/[\"']\$//" || true)
    fi
    printf '%s' "$val"
}

if [ -n "${PYTHON:-}" ]; then
    :
elif [ -x "${REPO_DIR}/.venv/bin/python" ]; then
    PYTHON="${REPO_DIR}/.venv/bin/python"
else
    PYTHON="python3"
fi
HELPER="${SCRIPT_DIR}/verify_inventory_migration.py"
[ -f "$HELPER" ] || error "Helper ausente: ${HELPER}"

# ── Resolve o banco alvo ──
resolve_db() {
    local v dbp
    if [ -n "$DB_ARG" ]; then printf '%s' "$DB_ARG"; return; fi
    v="$(cfg_get FILAMENT_INVENTORY_DB_PATH)"
    if [ -n "$v" ]; then printf '%s' "$v"; return; fi
    dbp="$(cfg_get DB_PATH)"
    if [ -n "$dbp" ]; then printf '%s/inventory.db' "$(dirname "$dbp")"; return; fi
    printf '%s' "${REPO_DIR}/data/inventory.db"
}
TARGET_DB="$(resolve_db)"
[ -f "$TARGET_DB" ] || error "Banco de estoque não encontrado: ${TARGET_DB} (use --db PATH)."
TARGET_DB="$(cd "$(dirname "$TARGET_DB")" && pwd)/$(basename "$TARGET_DB")"

BACKUP_DIR="${BACKUP_DIR:-$(cfg_get FILAMENTDB_BACKUP_DIR)}"
BACKUP_DIR="${BACKUP_DIR:-${REPO_DIR}/backups}"
MAX_DB_BACKUPS="${MAX_DB_BACKUPS:-30}"

CATALOG_DB="${MIGRATE_CATALOG_DB:-}"
if [ -z "$CATALOG_DB" ] && [ -f "$(dirname "$TARGET_DB")/filament.db" ]; then
    CATALOG_DB="$(dirname "$TARGET_DB")/filament.db"
fi

info "Banco alvo: ${TARGET_DB}"
info "Catálogo (leitura): ${CATALOG_DB:-<default da config>}"

WORK_DIR="$(mktemp -d /tmp/migrate_inventory.XXXXXX)"
trap 'rm -rf "$WORK_DIR"' EXIT
SNAPSHOT="${WORK_DIR}/before.json"

sha_of() { sha256sum "$1" | cut -d' ' -f1; }

# ── Confirmação (só no modo real) ──
if [ "$DRY_RUN" -eq 0 ] && [ "$ASSUME_YES" -eq 0 ]; then
    warn "Vai migrar o estoque de verdade em ${TARGET_DB}."
    warn "Recomendado parar o serviço antes (sudo systemctl stop filamentdb filamentdb-api)."
    warn "Rodar com o serviço ligado funciona (SQLite), mas há risco de escrita concorrente."
    if [ ! -t 0 ]; then
        error "Sem terminal para confirmar. Use --yes ou --dry-run."
    fi
    read -r -p "Continuar? [s/N] " ans
    case "$ans" in s|S|sim|SIM|y|Y|yes) ;; *) error "Cancelado pelo usuário." ;; esac
fi

# ── Dry-run: trabalha numa cópia consistente ──
WORK_DB="$TARGET_DB"
ORIG_SHA=""
if [ "$DRY_RUN" -eq 1 ]; then
    ORIG_SHA="$(sha_of "$TARGET_DB")"
    WORK_DB="${WORK_DIR}/inventory.db"
    if command -v sqlite3 >/dev/null 2>&1 && sqlite3 "$TARGET_DB" ".backup '${WORK_DB}'" 2>/dev/null; then
        :
    else
        cp -p "$TARGET_DB" "$WORK_DB" || error "Falha ao copiar o banco para o ensaio."
    fi
    info "DRY-RUN: trabalhando na cópia ${WORK_DB} (original intocado)."
fi

BACKUP=""
rollback_hint() {
    echo >&2
    echo -e "${RED}[ROLLBACK]${NC} Restaure o estado anterior com o serviço PARADO:" >&2
    if [ -n "$BACKUP" ]; then
        echo "  cp -p '${BACKUP}' '${TARGET_DB}' && rm -f '${TARGET_DB}-wal' '${TARGET_DB}-shm'" >&2
        echo "  (alternativa lógica: ${REPO_DIR}/scripts/restore_inventory.sh --replace <dump.json em ${BACKUP_DIR}/inventory-json/>)" >&2
        echo "  O backup foi MANTIDO em ${BACKUP}." >&2
    else
        echo "  (dry-run: o original não foi alterado; nada a restaurar)" >&2
    fi
}
fail() { echo -e "${RED}[ERROR]${NC} $*" >&2; rollback_hint; exit 1; }

# ── 1. Backup (só no modo real) ──
if [ "$DRY_RUN" -eq 0 ]; then
    mkdir -p "$BACKUP_DIR"
    TS="$(date '+%Y%m%d_%H%M%S')"
    BACKUP="${BACKUP_DIR}/inventory_premigration_${TS}.db"
    if command -v sqlite3 >/dev/null 2>&1; then
        sqlite3 "$TARGET_DB" ".backup '${BACKUP}'" 2>/dev/null \
            || error "Backup binário via sqlite3 FALHOU. Abortando sem alterar nada."
    else
        cp -p "$TARGET_DB" "$BACKUP" || error "Backup binário (cp) FALHOU. Abortando sem alterar nada."
    fi
    [ -s "$BACKUP" ] || error "Backup vazio: ${BACKUP}. Abortando sem alterar nada."
    info "Backup binário → ${BACKUP}"

    # Dump JSON lógico a partir de uma CÓPIA do backup (export_data() chama
    # init_db(); assim o banco real não é tocado por ele). Não-fatal.
    DUMP_DIR="${WORK_DIR}/dumpsrc"
    mkdir -p "$DUMP_DIR"
    cp -p "$BACKUP" "${DUMP_DIR}/inventory.db"
    [ -n "$CATALOG_DB" ] && ln -s "$CATALOG_DB" "${DUMP_DIR}/filament.db"
    if DB_PATH="${DUMP_DIR}/filament.db" BACKUP_DIR="$BACKUP_DIR" PYTHON="$PYTHON" \
        "${SCRIPT_DIR}/dump_inventory.sh" >/dev/null 2>&1; then
        info "Dump JSON lógico gerado em ${BACKUP_DIR}/inventory-json/"
    else
        warn "Dump JSON FALHOU — o backup binário permanece a garantia."
    fi

    # Rotação (mesma política MAX_DB_BACKUPS do update-server.sh).
    count=$(find "$BACKUP_DIR" -maxdepth 1 -name "inventory_premigration_*.db" -type f 2>/dev/null | wc -l)
    if [ "$count" -gt "$MAX_DB_BACKUPS" ]; then
        find "$BACKUP_DIR" -maxdepth 1 -name "inventory_premigration_*.db" -type f -printf '%T+ %p\n' \
            | sort | head -n "$((count - MAX_DB_BACKUPS))" | cut -d' ' -f2- \
            | while read -r old; do rm -f "$old"; done
        info "Rotação: mantidos os últimos ${MAX_DB_BACKUPS} backups premigration."
    fi
fi

# ── 2. Snapshot "antes" ──
"$PYTHON" "$HELPER" snapshot --db "$WORK_DB" --out "$SNAPSHOT" \
    || fail "Falha ao ler o estado 'antes' (tabela inventory_items existe?)."

# ── 3. Migração ──
info "Rodando a migração (init_db)..."
"$PYTHON" "$HELPER" migrate --db "$WORK_DB" --catalog "$CATALOG_DB" \
    || fail "A migração (init_db) falhou."

# ── 4. Verificação "depois" + relatório ──
"$PYTHON" "$HELPER" compare --db "$WORK_DB" --snapshot "$SNAPSHOT" \
    || fail "Verificação pós-migração DIVERGIU."

# ── 5. Idempotência ──
FP1="$("$PYTHON" "$HELPER" fingerprint --db "$WORK_DB")" || fail "Falha no fingerprint (1)."
"$PYTHON" "$HELPER" migrate --db "$WORK_DB" --catalog "$CATALOG_DB" >/dev/null \
    || fail "A 2ª execução da migração falhou."
FP2="$("$PYTHON" "$HELPER" fingerprint --db "$WORK_DB")" || fail "Falha no fingerprint (2)."
[ "$FP1" = "$FP2" ] || fail "Migração NÃO idempotente: a 2ª execução alterou o banco."
info "Idempotência confirmada (2ª execução idêntica)."

# ── Dry-run: garante que o original não mudou ──
if [ "$DRY_RUN" -eq 1 ]; then
    [ "$(sha_of "$TARGET_DB")" = "$ORIG_SHA" ] || fail "O original MUDOU durante o dry-run (inesperado)."
    info "DRY-RUN concluído: original inalterado (sha256 igual)."
else
    info "Migração concluída. Backup mantido em ${BACKUP}"
fi
exit 0
