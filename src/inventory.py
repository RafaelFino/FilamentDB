"""
inventory.py — Controle de estoque de filamentos.

Banco de dados SEPARADO do catálogo (filament.db). O catálogo é recriado
(DROP + CREATE) a cada `build.py`, então o estoque — que é dado mutável do
usuário — vive em `inventory.db` e nunca é tocado pelo build.

Persistência:
  - Path via env FILAMENT_INVENTORY_DB_PATH (default: <root>/inventory.db)
  - Schema criado on-demand com CREATE TABLE IF NOT EXISTS
  - Um item de estoque pode (opcionalmente) referenciar uma variante do
    catálogo via variant_id, mas também aceita entradas totalmente manuais.
"""

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

INVENTORY_DB_PATH = os.environ.get(
    "FILAMENT_INVENTORY_DB_PATH",
    str(Path(__file__).resolve().parent.parent / "inventory.db"),
)

# Status/localização de um item de estoque.
# Representa ONDE o rolo está (ou se já foi usado), escolhido pelo usuário.
STATUS_IN_STOCK = "in_stock"   # em estoque (guardado, lacrado)
STATUS_CFS = "cfs"             # carregado no CFS (Creality Filament System) — máx 4
STATUS_SPOOL = "spool"         # drybox acoplado ao spool holder da impressora (5ª entrada) — máx 1
STATUS_DRYBOX = "drybox"       # drybox guardado/seco (armazenamento) — sem limite
STATUS_OPEN = "open"           # aberto, fora de CFS/drybox — ALERTA (exposto à umidade)
STATUS_EMPTY = "empty"         # usado (vazio)
VALID_STATUSES = {
    STATUS_IN_STOCK, STATUS_CFS, STATUS_SPOOL, STATUS_DRYBOX, STATUS_OPEN, STATUS_EMPTY,
}
DEFAULT_STATUS = STATUS_IN_STOCK

# Limites físicos das posições de alimentação da impressora (K2):
#   - CFS: 4 baias -> até 4 rolos simultâneos
#   - Spool holder: 1 posição (alimentada por um drybox acoplado) -> até 1 rolo
# Total de entradas ativas na impressora = 5 (4 CFS + 1 spool).
STATUS_LIMITS = {
    STATUS_CFS: 4,
    STATUS_SPOOL: 1,
}


class LocationFullError(Exception):
    """Levantada ao exceder a capacidade de uma localização limitada (CFS/spool)."""
    def __init__(self, status, limit):
        self.status = status
        self.limit = limit
        super().__init__(self._message())

    def _message(self):
        if self.status == STATUS_CFS:
            return (f"CFS cheio: são {self.limit} slots físicos e cada rolo ocupa "
                    f"um slot. Retire um rolo antes de adicionar outro.")
        if self.status == STATUS_SPOOL:
            return (f"Spool holder ocupado: cabe {self.limit} rolo por vez "
                    f"(drybox acoplado). Retire o atual antes de acoplar outro.")
        return f"Localização cheia: máximo de {self.limit} rolo(s)."


# Compat: alias mantido para não quebrar imports antigos.
CfsFullError = LocationFullError


def slots_used(status, exclude_id=None):
    """
    Soma quantos SLOTS FÍSICOS (rolos) estão ocupados numa localização.

    Cada slot do CFS é um espaço físico independente que segura 1 rolo,
    independente da cor. Portanto o que ocupa slot é a quantidade de rolos
    (spools) — um item com spools=2 no CFS ocupa 2 slots (o CFS troca
    automaticamente de um rolo para o outro quando o primeiro acaba).
    """
    init_db()
    conn = get_connection()
    if exclude_id is not None:
        row = conn.execute(
            "SELECT COALESCE(SUM(spools), 0) FROM inventory_items WHERE status = ? AND id != ?",
            (status, exclude_id),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT COALESCE(SUM(spools), 0) FROM inventory_items WHERE status = ?",
            (status,),
        ).fetchone()
    conn.close()
    return row[0]


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def get_connection():
    conn = sqlite3.connect(INVENTORY_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# Colunas esperadas na tabela inventory_items (nome -> definição para ALTER).
# Usado para criar o schema e para validar/migrar bancos já existentes.
_SCHEMA_COLUMNS = {
    "id":           "INTEGER PRIMARY KEY AUTOINCREMENT",
    "material":     "TEXT NOT NULL",
    "manufacturer": "TEXT NOT NULL",
    "color_name":   "TEXT NOT NULL",
    "hex_color":    "TEXT",
    "finish":       "TEXT",
    "weight_g":     "INTEGER DEFAULT 1000",
    "spools":       "INTEGER NOT NULL DEFAULT 1",
    "status":       "TEXT NOT NULL DEFAULT 'in_stock'",
    "variant_id":   "INTEGER",
    "sku":          "TEXT",
    "notes":        "TEXT",
    "created_at":   "TEXT NOT NULL",
    "updated_at":   "TEXT NOT NULL",
}

# Colunas que podem ser adicionadas via ALTER TABLE numa migração (todas exceto
# a PK e as NOT NULL sem default, que precisam existir desde a criação).
_ADDABLE_COLUMNS = {
    "hex_color": "TEXT",
    "finish": "TEXT",
    "weight_g": "INTEGER DEFAULT 1000",
    "spools": "INTEGER NOT NULL DEFAULT 1",
    "status": "TEXT NOT NULL DEFAULT 'in_stock'",
    "variant_id": "INTEGER",
    "sku": "TEXT",
    "notes": "TEXT",
}

_initialized = False


def _table_exists(conn, name):
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


def _existing_columns(conn, table):
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def init_db(force=False):
    """
    Garante que o banco de estoque existe e tem a estrutura esperada.

    Comportamento (idempotente, seguro para rodar no startup e a cada operação):
      - Se o arquivo/tabela não existe: cria o schema do zero.
      - Se existe mas faltam colunas (schema antigo após um git pull/upgrade):
        adiciona as colunas faltantes via ALTER TABLE, preservando os dados.

    Projetado para deploy por `git pull`: o inventory.db não vem no repo, então
    o app o materializa sozinho na primeira execução.
    """
    global _initialized
    if _initialized and not force:
        return

    conn = get_connection()
    try:
        cur = conn.cursor()

        if not _table_exists(conn, "inventory_items"):
            cols_sql = ",\n            ".join(
                f"{name} {ddl}" for name, ddl in _SCHEMA_COLUMNS.items()
            )
            cur.execute(f"CREATE TABLE inventory_items (\n            {cols_sql}\n        );")
        else:
            # Valida e migra: adiciona colunas faltantes preservando dados.
            existing = _existing_columns(conn, "inventory_items")
            for name, ddl in _ADDABLE_COLUMNS.items():
                if name not in existing:
                    cur.execute(f"ALTER TABLE inventory_items ADD COLUMN {name} {ddl};")

        cur.execute("CREATE INDEX IF NOT EXISTS idx_inv_material ON inventory_items(material);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_inv_status ON inventory_items(status);")
        conn.commit()
        _initialized = True
    finally:
        conn.close()


def _row_to_dict(row):
    return {k: row[k] for k in row.keys()}


def _normalize_status(status):
    """Valida o status informado, caindo no default se inválido/ausente."""
    if status in VALID_STATUSES:
        return status
    return DEFAULT_STATUS


# ─── CRUD ──────────────────────────────────────────────────────────────────────

def list_items():
    """Retorna todos os itens de estoque, ordenados por material e cor."""
    init_db()
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT * FROM inventory_items
        ORDER BY material, manufacturer, color_name
        """
    ).fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]


def get_item(item_id):
    init_db()
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM inventory_items WHERE id = ?", (item_id,)
    ).fetchone()
    conn.close()
    return _row_to_dict(row) if row else None


def add_item(data):
    """
    Cria um item de estoque.

    Campos aceitos em `data`:
      material (obrigatório), manufacturer (obrigatório), color_name (obrigatório),
      hex_color, finish, weight_g, spools, status, variant_id, sku, notes
    """
    material = (data.get("material") or "").strip()
    manufacturer = (data.get("manufacturer") or "").strip()
    color_name = (data.get("color_name") or "").strip()
    if not material or not manufacturer or not color_name:
        raise ValueError("material, manufacturer e color_name são obrigatórios")

    spools = int(data.get("spools", 1) or 0)
    status = _normalize_status(data.get("status"))
    now = _now()

    limit = STATUS_LIMITS.get(status)
    if limit is not None and slots_used(status) + spools > limit:
        raise LocationFullError(status, limit)

    init_db()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO inventory_items(
            material, manufacturer, color_name, hex_color, finish,
            weight_g, spools, status, variant_id, sku, notes,
            created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            material, manufacturer, color_name,
            data.get("hex_color"), data.get("finish"),
            int(data.get("weight_g", 1000) or 1000),
            spools, status,
            data.get("variant_id"), data.get("sku"),
            data.get("notes"), now, now,
        ),
    )
    item_id = cur.lastrowid
    conn.commit()
    conn.close()
    return get_item(item_id)


# Campos que o usuário pode atualizar diretamente
_UPDATABLE = {
    "material", "manufacturer", "color_name", "hex_color", "finish",
    "weight_g", "spools", "status", "variant_id", "sku", "notes",
}


def update_item(item_id, data):
    """Atualiza campos de um item. Recalcula status se spools mudar sem status explícito."""
    existing = get_item(item_id)
    if existing is None:
        return None

    fields = {k: v for k, v in data.items() if k in _UPDATABLE}
    if not fields:
        return existing

    # Status é explícito, escolhido pelo usuário. Se vier inválido, normaliza.
    if "status" in fields:
        fields["status"] = _normalize_status(fields["status"])

    # Estado resultante do item após o update (status e spools finais).
    new_status = fields.get("status", existing["status"])
    new_spools = int(fields.get("spools", existing["spools"]) or 0)

    # Valida capacidade da localização-alvo se ela é limitada e o item vai
    # ocupá-la. Cobre tanto MOVER para a localização quanto AUMENTAR os rolos
    # de um item que já está nela (cada rolo = 1 slot físico).
    limit = STATUS_LIMITS.get(new_status)
    if limit is not None:
        others = slots_used(new_status, exclude_id=item_id)
        if others + new_spools > limit:
            raise LocationFullError(new_status, limit)

    fields["updated_at"] = _now()
    cols = ", ".join(f"{k} = ?" for k in fields)
    vals = list(fields.values()) + [item_id]

    init_db()
    conn = get_connection()
    conn.execute(f"UPDATE inventory_items SET {cols} WHERE id = ?", vals)
    conn.commit()
    conn.close()
    return get_item(item_id)


def use_item(item_id, amount=1):
    """
    Marca uso: decrementa `amount` rolos (mínimo 0). Se zerar, marca como usado (empty).
    Usado pelo botão "usei" na interface.
    """
    existing = get_item(item_id)
    if existing is None:
        return None
    new_spools = max(0, int(existing["spools"]) - int(amount))
    patch = {"spools": new_spools}
    if new_spools == 0:
        patch["status"] = STATUS_EMPTY
    return update_item(item_id, patch)


def delete_item(item_id):
    existing = get_item(item_id)
    if existing is None:
        return False
    init_db()
    conn = get_connection()
    conn.execute("DELETE FROM inventory_items WHERE id = ?", (item_id,))
    conn.commit()
    conn.close()
    return True


# ─── Views agregadas ─────────────────────────────────────────────────────────

def grouped_by_material():
    """
    Agrupa o estoque por material → lista de itens (cores).

    Foco na necessidade real: na K2 não se mistura material numa mesma peça,
    então a paleta de cores disponível é sempre consultada DENTRO de um material.

    Retorna:
      {
        "materials": [
          {
            "material": "PLA",
            "total_spools": 7,
            "colors_available": 4,   # cores distintas não-vazias (disponíveis p/ imprimir)
            "items": [ {item...}, ... ]
          }, ...
        ],
        "summary": { "total_items": N, "total_spools": N, "materials": N }
      }
    """
    items = list_items()
    groups = {}
    for it in items:
        groups.setdefault(it["material"], []).append(it)

    materials = []
    total_spools = 0
    for material, its in sorted(groups.items()):
        mat_spools = sum(i["spools"] for i in its)
        # Cor disponível = não marcada como usada (independe de estar no CFS/drybox/estoque)
        colors_available = len({
            (i["color_name"], i["hex_color"]) for i in its if i["status"] != STATUS_EMPTY
        })
        total_spools += mat_spools
        materials.append({
            "material": material,
            "total_spools": mat_spools,
            "colors_available": colors_available,
            "items": its,
        })

    return {
        "materials": materials,
        "summary": _build_summary(items),
    }


def _build_summary(items):
    """
    Resumo agregado do estoque, usado por ambas as views.

    Itens usados (empty) NÃO entram nas estatísticas — já foram consumidos.
    """
    active = [i for i in items if i["status"] != STATUS_EMPTY]

    # Slots ocupados = soma de rolos (cada rolo = 1 slot físico), não nº de itens.
    cfs_used = sum(i["spools"] for i in active if i["status"] == STATUS_CFS)
    spool_used = sum(i["spools"] for i in active if i["status"] == STATUS_SPOOL)
    open_count = sum(1 for i in active if i["status"] == STATUS_OPEN)
    total_spools = sum(i["spools"] for i in active)
    materials = len({i["material"] for i in active})
    return {
        "total_items": len(active),
        "total_spools": total_spools,
        "materials": materials,
        "cfs_used": cfs_used,
        "cfs_max": STATUS_LIMITS[STATUS_CFS],
        "spool_used": spool_used,
        "spool_max": STATUS_LIMITS[STATUS_SPOOL],
        "open_count": open_count,
        "used_count": len(items) - len(active),
    }


def _material_groups(items):
    """Agrupa uma lista de itens por material → cores (para a seção de estoque)."""
    groups = {}
    for it in items:
        groups.setdefault(it["material"], []).append(it)
    out = []
    for material, its in sorted(groups.items()):
        out.append({
            "material": material,
            "total_spools": sum(i["spools"] for i in its),
            "colors_available": len({
                (i["color_name"], i["hex_color"]) for i in its if i["status"] != STATUS_EMPTY
            }),
            "items": its,
        })
    return out


def grouped_by_location():
    """
    Organiza o estoque por LOCALIZAÇÃO FÍSICA, na ordem do fluxo de uso:

      1. printer  — engatado na impressora agora (CFS primeiro, depois spool holder)
      2. drybox   — nos dryboxes, secos e prontos para engatar
      3. open      — abertos e fora do drybox (ALERTA: expostos à umidade)
      4. sealed    — estoque fechado/guardado (agrupado por material → cor)
      5. empty     — usados (vazios)

    Cada rolo (spools) conta como um slot físico independente da cor.
    """
    items = list_items()

    def by_status(*statuses):
        return [i for i in items if i["status"] in statuses]

    cfs_items = sorted(by_status(STATUS_CFS), key=lambda i: (i["material"], i["color_name"]))
    spool_items = sorted(by_status(STATUS_SPOOL), key=lambda i: (i["material"], i["color_name"]))
    drybox_items = sorted(by_status(STATUS_DRYBOX), key=lambda i: (i["material"], i["color_name"]))
    open_items = sorted(by_status(STATUS_OPEN), key=lambda i: (i["material"], i["color_name"]))
    sealed_items = by_status(STATUS_IN_STOCK)
    empty_items = sorted(by_status(STATUS_EMPTY), key=lambda i: (i["material"], i["color_name"]))

    return {
        "printer": {
            "cfs": {
                "items": cfs_items,
                "used": sum(i["spools"] for i in cfs_items),
                "max": STATUS_LIMITS[STATUS_CFS],
            },
            "spool": {
                "items": spool_items,
                "used": sum(i["spools"] for i in spool_items),
                "max": STATUS_LIMITS[STATUS_SPOOL],
            },
        },
        "drybox": {"items": drybox_items},
        "open": {"items": open_items},
        "sealed": {"materials": _material_groups(sealed_items)},
        "empty": {"items": empty_items},
        "summary": _build_summary(items),
    }
