"""
inventory.py — Controle de estoque de filamentos.

Banco de dados SEPARADO do catálogo (filament.db). O catálogo é recriado
(DROP + CREATE) a cada `build.py`, então o estoque — que é dado mutável do
usuário — vive em `inventory.db` e nunca é tocado pelo build.

Persistência:
  - Path derived from DB_PATH: sibling `inventory.db`
  - Schema criado on-demand com CREATE TABLE IF NOT EXISTS
  - Um item de estoque pode (opcionalmente) referenciar uma variante do
    catálogo via variant_id, mas também aceita entradas totalmente manuais.
"""

import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from src import palette
from src import config  # carrega config.env no os.environ antes de resolver paths
from src import database  # catálogo (filament.db) — leitura para validar tipo/cor

config.load()

# Todos os bancos persistentes ficam no mesmo diretório definido por DB_PATH.
INVENTORY_DB_PATH = config.database_path("inventory.db")

# Versão do formato de export/import do estoque. Incrementar quando o formato
# do envelope ou o significado dos campos mudar de forma incompatível. O
# import usa isso para aplicar migrações e manter retrocompatibilidade.
#   v1: sem profile_name (tipo implícito em variant_id/finish)
#   v2: adiciona profile_name (tipo = produto do catálogo, separado da cor)
INVENTORY_SCHEMA_VERSION = 2

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
    # uid: identificador estável e único do item FÍSICO. Diferente do `id`
    # (autoincrement, local ao arquivo .db), o uid sobrevive a export/import e
    # à recriação do banco. É a chave natural do upsert na importação. Um rolo
    # físico é único — não pode existir em dois lugares.
    "uid":          "TEXT",
    "material":     "TEXT NOT NULL",
    "manufacturer": "TEXT NOT NULL",
    "color_name":   "TEXT NOT NULL",
    "hex_color":    "TEXT",
    # color_id: id estável da paleta (src/color_palette.json); NULL = cor vinda
    # de variante do catálogo/texto livre (legado).
    "color_id":     "TEXT",
    # profile_name: TIPO do item = produto do catálogo (filament_profiles.
    # profile_name, chave estável). NULL = tipo não definido (legado).
    "profile_name": "TEXT",
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
    "uid": "TEXT",
    "hex_color": "TEXT",
    "color_id": "TEXT",
    "profile_name": "TEXT",
    "finish": "TEXT",
    "weight_g": "INTEGER DEFAULT 1000",
    "spools": "INTEGER NOT NULL DEFAULT 1",
    "status": "TEXT NOT NULL DEFAULT 'in_stock'",
    "variant_id": "INTEGER",
    "sku": "TEXT",
    "notes": "TEXT",
}

# Rastreia QUAL arquivo foi inicializado (não um simples booleano). Se o path
# mudar ou o arquivo sumir/for recriado, a checagem barata abaixo detecta e
# reinicializa — evita o "no such table" quando o .db é removido/trocado em
# runtime (ex.: restore de backup, mudança de config, ou o próprio arquivo
# recriado vazio por outro processo).
_initialized_path = None


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
    global _initialized_path

    # Fast-path: só pula se JÁ inicializamos ESTE mesmo arquivo E ele ainda
    # contém a tabela. A verificação de schema_master é barata (uma linha) e
    # blinda contra o arquivo ter sido removido/recriado depois do primeiro
    # init — causa raiz do erro "no such table: inventory_items" em runtime.
    if not force and _initialized_path == INVENTORY_DB_PATH:
        conn = get_connection()
        try:
            if _table_exists(conn, "inventory_items"):
                return
        finally:
            conn.close()

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

        # Backfill de uid: itens de bancos antigos (criados antes da coluna uid)
        # ficam sem identificador estável. Geramos um uuid4 para cada um, de
        # forma idempotente (só onde está nulo/vazio). Sem isso o export/import
        # não teria chave natural para esses itens.
        rows = cur.execute(
            "SELECT id FROM inventory_items WHERE uid IS NULL OR uid = ''"
        ).fetchall()
        for r in rows:
            cur.execute(
                "UPDATE inventory_items SET uid = ? WHERE id = ?",
                (str(uuid.uuid4()), r[0]),
            )

        # ─── Migração: 1 linha = 1 rolo ───────────────────────────────────
        # Modelo antigo: uma linha podia ter spools=N (N rolos agregados numa
        # linha só). Isso causava o bug de "mover leva todos os rolos juntos".
        # Modelo novo: cada rolo é uma linha física independente (spools=1).
        # Quebramos as linhas antigas com spools>1 em N linhas de 1, gerando
        # uid novo para as extras. Idempotente via flag em _inv_meta.
        cur.execute(
            "CREATE TABLE IF NOT EXISTS _inv_meta (key TEXT PRIMARY KEY, value TEXT);"
        )
        done = cur.execute(
            "SELECT value FROM _inv_meta WHERE key = 'split_spools_v1'"
        ).fetchone()
        if not done:
            multi = cur.execute(
                "SELECT * FROM inventory_items WHERE spools > 1"
            ).fetchall()
            for row in multi:
                extra = int(row["spools"]) - 1
                # A linha original passa a valer 1 rolo.
                cur.execute(
                    "UPDATE inventory_items SET spools = 1, updated_at = ? WHERE id = ?",
                    (_now(), row["id"]),
                )
                # As demais viram novas linhas físicas (uid próprio).
                for _ in range(extra):
                    cur.execute(
                        """
                        INSERT INTO inventory_items(
                            uid, material, manufacturer, color_name, hex_color,
                            finish, weight_g, spools, status, variant_id, sku,
                            notes, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            str(uuid.uuid4()), row["material"], row["manufacturer"],
                            row["color_name"], row["hex_color"], row["finish"],
                            row["weight_g"], row["status"], row["variant_id"],
                            row["sku"], row["notes"], row["created_at"], _now(),
                        ),
                    )
            cur.execute(
                "INSERT INTO _inv_meta(key, value) VALUES ('split_spools_v1', ?)",
                (_now(),),
            )

        cur.execute("CREATE INDEX IF NOT EXISTS idx_inv_material ON inventory_items(material);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_inv_status ON inventory_items(status);")
        # uid é único: garante que o upsert do import não crie duplicatas e que
        # dois itens físicos nunca compartilhem identidade.
        cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_inv_uid ON inventory_items(uid);")
        conn.commit()
        _initialized_path = INVENTORY_DB_PATH
    finally:
        conn.close()

    # Backfill do tipo (idempotente, conservador). Nunca derruba o init: se o
    # catálogo estiver ausente/ilegível, simplesmente não preenche nada.
    try:
        backfill_profiles()
    except sqlite3.Error:
        pass


def _row_to_dict(row):
    return {k: row[k] for k in row.keys()}


def _needs_review(item):
    """Pendências de revisão do item (lista vazia = nada a revisar)."""
    flags = []
    if not item.get("profile_name"):
        flags.append("type_missing")
    if not item.get("color_id") and item.get("variant_id") is None:
        flags.append("color_free_text")
    return flags


def _row_to_item(row):
    item = _row_to_dict(row)
    item["needs_review"] = _needs_review(item)
    return item


def _normalize_status(status):
    """Valida o status informado, caindo no default se inválido/ausente."""
    if status in VALID_STATUSES:
        return status
    return DEFAULT_STATUS


# ─── CRUD ──────────────────────────────────────────────────────────────────────

# Filtros aceitos em list_items (coluna -> comparação case-insensitive?).
# As chaves são constantes (nunca vêm do usuário); os VALORES vão parametrizados.
_FILTER_COLUMNS = {
    "material": True,
    "manufacturer": True,
    "profile_name": False,
    "color_id": False,
    "color_name": True,
}


def list_items(filters=None):
    """Retorna os itens de estoque, ordenados por material e cor.

    `filters` (opcional): dict com material, manufacturer, profile_name,
    color_id, color_name — combinados com AND; valores vazios são ignorados.
    """
    init_db()
    where, params = [], []
    for key, nocase in _FILTER_COLUMNS.items():
        val = (filters or {}).get(key)
        if val is None or str(val).strip() == "":
            continue
        where.append(f"{key} = ?" + (" COLLATE NOCASE" if nocase else ""))
        params.append(str(val).strip())
    sql = "SELECT * FROM inventory_items"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY material, manufacturer, color_name"
    conn = get_connection()
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [_row_to_item(r) for r in rows]


def get_item(item_id):
    init_db()
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM inventory_items WHERE id = ?", (item_id,)
    ).fetchone()
    conn.close()
    return _row_to_item(row) if row else None


# ─── Catálogo (filament.db) — leitura para validar tipo/cor ────────────────────

class TypeColorError(ValueError):
    """Erro de validação de tipo/cor (HTTP 400) com `code` estável p/ a UI."""
    def __init__(self, message, code="validation_error"):
        super().__init__(message)
        self.code = code


class ItemNotFoundError(LookupError):
    """Item de estoque inexistente (HTTP 404)."""
    def __init__(self, item_id):
        self.item_id = item_id
        super().__init__(f"item {item_id} não encontrado")


def _catalog_query(sql, params=()):
    """Executa uma leitura no catálogo. Retorna lista de dicts, ou None se o
    catálogo/tabela estiver ausente ou ilegível (nunca cria o arquivo)."""
    try:
        if not Path(database.DB_PATH).exists():
            return None
        conn = database.get_db_connection()
        try:
            return [dict(r) for r in conn.execute(sql, params).fetchall()]
        finally:
            conn.close()
    except sqlite3.Error:
        return None


_PROFILE_SELECT = (
    "SELECT p.id, p.profile_name, p.commercial_name, "
    "mf.name AS manufacturer, mt.name AS material "
    "FROM filament_profiles p "
    "JOIN manufacturers mf ON mf.id = p.manufacturer_id "
    "JOIN materials mt ON mt.id = p.material_id"
)


def _catalog_profile(profile_name):
    """Perfil do catálogo por profile_name. None = catálogo indisponível;
    {} = perfil inexistente; dict = perfil."""
    rows = _catalog_query(_PROFILE_SELECT + " WHERE p.profile_name = ?", (profile_name,))
    if rows is None:
        return None
    return rows[0] if rows else {}


def _catalog_variants(profile_id):
    """Variantes (cores) de um perfil. None = catálogo indisponível."""
    return _catalog_query(
        "SELECT id, sku, color_name, hex_color, finish "
        "FROM filament_variants WHERE filament_id = ?",
        (profile_id,),
    )


def _catalog_snapshot():
    """Foto do catálogo (perfis + variantes) para inferência em lote."""
    profiles = _catalog_query(_PROFILE_SELECT)
    variants = _catalog_query(
        "SELECT id, filament_id, sku, color_name FROM filament_variants"
    )
    if profiles is None or variants is None:
        return None
    return {
        "profiles": {p["id"]: p for p in profiles},
        "names": {p["profile_name"] for p in profiles},
        "variants": variants,
    }


def _norm(text):
    return (text or "").strip().casefold()


def _infer_profile(item, snap):
    """Infere o profile_name de forma CONSERVADORA (nunca adivinha).

    variant_id não é estável (o catálogo é recriado a cada build), então só
    aceita se o perfil tiver mesmo fabricante+material e a variante a mesma
    cor do item. Alternativa: sku que case com exatamente um perfil do mesmo
    fabricante+material. Caso contrário devolve None.
    """
    if not snap:
        return None
    mfr, mat = _norm(item.get("manufacturer")), _norm(item.get("material"))

    def same_product(p):
        return p is not None and _norm(p["manufacturer"]) == mfr and _norm(p["material"]) == mat

    vid = item.get("variant_id")
    if vid is not None:
        for v in snap["variants"]:
            if v["id"] == vid:
                p = snap["profiles"].get(v["filament_id"])
                if same_product(p) and _norm(v["color_name"]) == _norm(item.get("color_name")):
                    return p["profile_name"]
                break
    sku = (item.get("sku") or "").strip()
    if sku:
        found = {
            v["filament_id"] for v in snap["variants"]
            if (v["sku"] or "").strip() == sku
            and same_product(snap["profiles"].get(v["filament_id"]))
        }
        if len(found) == 1:
            return snap["profiles"][found.pop()]["profile_name"]
    return None


def backfill_profiles():
    """Preenche profile_name onde está NULL, só com inferência segura.

    Idempotente: só toca linhas com profile_name IS NULL; sem flag de execução
    (o catálogo pode estar indisponível no 1º start). Nunca reescreve
    color_name nem outras colunas. Retorna quantas linhas foram preenchidas.
    """
    conn = get_connection()
    try:
        if not _table_exists(conn, "inventory_items"):
            return 0
        if "profile_name" not in _existing_columns(conn, "inventory_items"):
            return 0
        rows = conn.execute(
            "SELECT id, manufacturer, material, color_name, variant_id, sku "
            "FROM inventory_items WHERE profile_name IS NULL"
        ).fetchall()
        if not rows:
            return 0
        snap = _catalog_snapshot()
        if snap is None:
            return 0
        filled = 0
        for r in rows:
            name = _infer_profile(_row_to_dict(r), snap)
            if name:
                conn.execute(
                    "UPDATE inventory_items SET profile_name = ? "
                    "WHERE id = ? AND profile_name IS NULL",
                    (name, r["id"]),
                )
                filled += 1
        conn.commit()
        return filled
    finally:
        conn.close()


# ─── Validadores ───────────────────────────────────────────────────────────────

_HEX_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")
WEIGHT_MAX_G = 10000


def _validate_hex(value):
    if value is None or value == "":
        return None
    if not isinstance(value, str) or not _HEX_RE.match(value):
        raise ValueError("hex_color inválido: use o formato #RRGGBB")
    return value


def _validate_weight(value):
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= WEIGHT_MAX_G:
        raise ValueError(f"weight_g deve ser um inteiro entre 0 e {WEIGHT_MAX_G}")
    return value


def _validate_fields(fields, patch=False):
    """Validações de formato (hex, peso e, em PATCH, spools). In place."""
    if "hex_color" in fields:
        fields["hex_color"] = _validate_hex(fields["hex_color"])
    if "weight_g" in fields:
        fields["weight_g"] = _validate_weight(fields["weight_g"])
    if patch and "spools" in fields:
        s = fields["spools"]
        if isinstance(s, bool) or not isinstance(s, int) or s not in (0, 1):
            raise ValueError(
                "spools deve ser 0 ou 1 (1 linha = 1 rolo); para mais rolos use add-spool"
            )


def validate_type_color(fields, existing=None):
    """Valida/deriva tipo (profile_name) e cor, in place em `fields`.

    - profile_name deve existir no catálogo; material/manufacturer são
      derivados do perfil (payload divergente -> erro).
    - Cor efetiva: color_id da paleta (sempre válido) OU variante do perfil
      (variant_id do perfil ou color_name igual, case-insensitive; o hex vem
      da variante). Texto livre com tipo definido -> erro.
    - Trocar o tipo revalida a cor efetiva: sem escrever nada se incompatível
      (code 'color_incompatible').
    - Sem profile_name (no payload ou no item) e sem tipo/cor tocados: legado,
      não revalida.
    """
    ex = existing or {}
    type_in = "profile_name" in fields
    if type_in:
        pn = fields["profile_name"]
        if pn is None or (isinstance(pn, str) and not pn.strip()):
            fields["profile_name"] = None
        elif not isinstance(pn, str):
            raise TypeColorError("profile_name deve ser texto", "invalid_profile")
        else:
            fields["profile_name"] = pn.strip()
    new_profile = fields["profile_name"] if type_in else ex.get("profile_name")
    if not new_profile:
        return
    color_touched = any(k in fields for k in ("color_id", "color_name", "variant_id"))
    mm_touched = any(k in fields for k in ("material", "manufacturer"))
    if not (type_in or color_touched or mm_touched):
        return
    type_changed = type_in and new_profile != ex.get("profile_name")

    prof = _catalog_profile(new_profile)
    if prof is None:
        raise TypeColorError("catálogo indisponível: não é possível validar o tipo",
                             "catalog_unavailable")
    if not prof:
        raise TypeColorError(f"tipo inexistente no catálogo: {new_profile!r}",
                             "profile_not_found")

    for key in ("material", "manufacturer"):
        if key in fields and _norm(fields[key]) != _norm(prof[key]):
            raise TypeColorError(
                f"{key} {fields[key]!r} diverge do tipo {new_profile!r} ({prof[key]})",
                "type_mismatch")
        if type_in or key in fields:
            fields[key] = prof[key]

    if not (type_changed or color_touched):
        return
    color_id = fields["color_id"] if "color_id" in fields else ex.get("color_id")
    if (color_id and "color_id" not in fields and not type_changed
            and ("color_name" in fields or "variant_id" in fields)):
        # color_name/variant_id sem color_id: sai da paleta; valida como cor de variante
        # (evita gravar nome novo mantendo color_id/hex antigos).
        fields["color_id"] = None
        color_id = None
    if color_id:
        # Cor da paleta vale para qualquer tipo; não carrega variante de outro produto.
        if "color_id" in fields or type_changed:
            fields.setdefault("variant_id", None)
        return

    variants = _catalog_variants(prof["id"])
    if variants is None:
        raise TypeColorError("catálogo indisponível: não é possível validar a cor",
                             "catalog_unavailable")
    eff_name = fields["color_name"] if "color_name" in fields else ex.get("color_name")
    eff_name = (eff_name or "").strip()
    if not eff_name and fields.get("variant_id") is None:
        raise TypeColorError("cor obrigatória: escolha uma cor do tipo ou da paleta",
                             "color_required")

    chosen = None
    vid = fields.get("variant_id")
    if vid is not None:
        chosen = next((v for v in variants if v["id"] == vid), None)
    if chosen is None and eff_name:
        chosen = next((v for v in variants if _norm(v["color_name"]) == _norm(eff_name)), None)
    if (chosen is None and vid is None and "color_name" not in fields
            and ex.get("variant_id") is not None):
        chosen = next((v for v in variants if v["id"] == ex["variant_id"]), None)

    if chosen is None:
        if existing and type_changed and not color_touched:
            raise TypeColorError(
                f"a cor {eff_name!r} não existe no tipo {new_profile!r}; "
                "escolha outra cor do tipo ou uma cor da paleta",
                "color_incompatible")
        raise TypeColorError(
            f"cor {eff_name!r} inválida para o tipo {new_profile!r}: "
            "use uma cor do tipo ou da paleta (texto livre não é aceito)",
            "color_invalid")

    fields["color_name"] = chosen["color_name"]
    fields["variant_id"] = chosen["id"]
    if chosen.get("hex_color") and _HEX_RE.match(chosen["hex_color"]):
        fields["hex_color"] = chosen["hex_color"]


def _apply_palette(data):
    """Se `color_id` veio no payload, valida contra a paleta e sobrescreve
    color_name/hex_color com os valores canônicos (o servidor é autoritativo).

    `color_id` vazio/None limpa a referência (cor volta a ser texto/variante).
    Id fora da paleta -> ValueError (HTTP 400). Modifica `data` in place.
    """
    if "color_id" not in data:
        return
    cid = data["color_id"]
    if cid is None or cid == "":
        data["color_id"] = None
        return
    color = palette.get_color(cid)
    if color is None:
        raise ValueError(f"color_id inválido: {cid!r} (não pertence à paleta)")
    data["color_id"] = color["id"]
    data["color_name"] = color["name"]
    data["hex_color"] = color["hex"]


def add_item(data, validate_catalog=True):
    """
    Cria um item de estoque.

    Campos aceitos em `data`:
      material (obrigatório), manufacturer (obrigatório), color_name (obrigatório),
      profile_name (tipo; OBRIGATÓRIO na criação, validado contra o catálogo;
      ausente/vazio -> TypeColorError code=profile_required),
      hex_color, finish, weight_g, spools, status, variant_id, sku, notes

    `validate_catalog=False` é de uso interno (clonar rolo existente sem
    revalidar contra um catálogo que pode ter mudado).
    """
    data = dict(data)
    if data.get("weight_g") is None:
        data.pop("weight_g", None)
    _apply_palette(data)
    if validate_catalog:
        profile = data.get("profile_name")
        if not isinstance(profile, str) or not profile.strip():
            raise TypeColorError("Escolha o tipo (produto) do filamento.",
                                 "profile_required")
        _validate_fields(data)
        validate_type_color(data)
    elif not (data.get("profile_name") or "").strip():
        data["profile_name"] = None
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

    # Modelo físico: 1 linha = 1 rolo. Um pedido de N rolos vira N linhas
    # independentes, cada uma com uid próprio (identidade física única). Isso é
    # o que permite mover/usar um rolo por vez sem arrastar os demais.
    #
    # O uid do payload (reimportação de um item existente) só faz sentido para
    # UM rolo — se vier junto com spools>1, ele é usado na primeira linha e as
    # demais recebem uid novo.
    payload_uid = (data.get("uid") or "").strip() or None
    # Peso 0 é válido (rolo acabado): só o ausente vira o default de 1000 g.
    weight_g = data["weight_g"] if "weight_g" in data else 1000

    init_db()
    conn = get_connection()
    cur = conn.cursor()
    first_id = None
    count = max(1, spools)  # spools<=0 ainda cria 1 rolo (comportamento anterior)
    for i in range(count):
        item_uid = payload_uid if (i == 0 and payload_uid) else str(uuid.uuid4())
        cur.execute(
            """
            INSERT INTO inventory_items(
                uid, material, manufacturer, color_name, hex_color, color_id,
                profile_name, finish, weight_g, spools, status, variant_id, sku,
                notes, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item_uid, material, manufacturer, color_name,
                data.get("hex_color"), data.get("color_id"),
                data.get("profile_name"), data.get("finish"),
                weight_g, 1, status,
                data.get("variant_id"), data.get("sku"),
                data.get("notes"), now, now,
            ),
        )
        if first_id is None:
            first_id = cur.lastrowid
    conn.commit()
    conn.close()
    return get_item(first_id)


# Campos que o usuário pode atualizar diretamente
_UPDATABLE = {
    "material", "manufacturer", "color_name", "hex_color", "color_id", "finish",
    "weight_g", "spools", "status", "variant_id", "sku", "notes", "profile_name",
}


def _prepare_update(existing, data):
    """Filtra, normaliza e valida os campos de um PATCH (só os enviados)."""
    fields = {k: v for k, v in data.items() if k in _UPDATABLE}
    if not fields:
        return fields
    _apply_palette(fields)

    # Status é explícito, escolhido pelo usuário. Se vier inválido, normaliza.
    if "status" in fields:
        fields["status"] = _normalize_status(fields["status"])

    _validate_fields(fields, patch=True)
    validate_type_color(fields, existing)
    return fields


def update_item(item_id, data):
    """Atualiza SÓ os campos enviados de um item (PATCH).

    Tipo/cor/peso/spools são validados antes de escrever qualquer coisa.
    """
    existing = get_item(item_id)
    if existing is None:
        return None

    fields = _prepare_update(existing, data)
    if not fields:
        return existing

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
    Marca uso de UM rolo: como cada linha é exatamente 1 rolo (spools=1), usar
    esse item significa marcá-lo como vazio (empty). O parâmetro `amount` é
    mantido por compatibilidade de API, mas um item representa um único rolo —
    qualquer amount >= 1 esvazia a linha.

    Usado pelo botão "usei" na interface.
    """
    existing = get_item(item_id)
    if existing is None:
        return None
    if int(amount) <= 0:
        return existing
    return update_item(item_id, {"spools": 0, "status": STATUS_EMPTY})


def bulk_update(ids, fields):
    """Aplica os mesmos `fields` a vários rolos, de forma ATÔMICA.

    Valida tudo antes (itens existentes, tipo/cor por item, capacidade de
    CFS/spool considerando o estado final) e grava numa única transação:
    qualquer erro => nada muda. Levanta ItemNotFoundError (404), ValueError
    (400) ou LocationFullError (409). Retorna a lista de itens atualizados.
    """
    if (not isinstance(ids, list) or not ids
            or any(isinstance(i, bool) or not isinstance(i, int) for i in ids)):
        raise ValueError("ids deve ser uma lista não vazia de inteiros")
    ids = list(dict.fromkeys(ids))
    if len(ids) > 500:
        raise ValueError("máximo de 500 itens por operação em lote")
    if not isinstance(fields, dict) or not any(k in _UPDATABLE for k in fields):
        raise ValueError("nenhum campo atualizável informado")

    init_db()
    conn = get_connection()
    try:
        prepared = {}
        finals = {}
        for i in ids:
            row = conn.execute("SELECT * FROM inventory_items WHERE id = ?", (i,)).fetchone()
            if row is None:
                raise ItemNotFoundError(i)
            existing = _row_to_item(row)
            prepared[i] = _prepare_update(existing, dict(fields))
            finals[i] = (
                prepared[i].get("status", existing["status"]),
                int(prepared[i].get("spools", existing["spools"]) or 0),
            )

        marks = ",".join("?" * len(ids))
        for status, limit in STATUS_LIMITS.items():
            mine = sum(sp for st, sp in finals.values() if st == status)
            if not any(st == status for st, _ in finals.values()):
                continue
            others = conn.execute(
                f"SELECT COALESCE(SUM(spools), 0) FROM inventory_items "
                f"WHERE status = ? AND id NOT IN ({marks})",
                [status, *ids],
            ).fetchone()[0]
            if others + mine > limit:
                raise LocationFullError(status, limit)

        now = _now()
        for i, f in prepared.items():
            f = dict(f, updated_at=now)
            cols = ", ".join(f"{k} = ?" for k in f)
            conn.execute(f"UPDATE inventory_items SET {cols} WHERE id = ?", [*f.values(), i])
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()
    return [get_item(i) for i in ids]


def add_spool(item_id, count=1):
    """
    "Comprei mais rolos" deste mesmo filamento.

    Como 1 linha = 1 rolo, adicionar rolos cria `count` (1..50) NOVAS linhas
    físicas (uid próprio) espelhando o item de referência, sempre em estoque
    (in_stock) e com spools=1. Devolve o primeiro item recém-criado.
    """
    if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 50:
        raise ValueError("count deve ser um inteiro entre 1 e 50")
    existing = get_item(item_id)
    if existing is None:
        return None
    return add_item({
        "material": existing["material"],
        "manufacturer": existing["manufacturer"],
        "color_name": existing["color_name"],
        "hex_color": existing.get("hex_color"),
        "color_id": existing.get("color_id"),
        "profile_name": existing.get("profile_name"),
        "finish": existing.get("finish"),
        "weight_g": existing.get("weight_g"),
        "variant_id": existing.get("variant_id"),
        "sku": existing.get("sku"),
        "notes": existing.get("notes"),
        "spools": count,
        "status": STATUS_IN_STOCK,
    }, validate_catalog=False)


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


# ─── Export / Import (backup lógico versionado) ──────────────────────────────
# Formato intermediário desacoplado do schema físico do SQLite. Permite backup,
# migração entre versões e restauração sem ficar preso à estrutura do .db.

# Campos de cada item que fazem parte do contrato de export. `id` é omitido de
# propósito: é local ao arquivo .db e não deve atravessar import (a identidade
# estável é o `uid`). created_at/updated_at são preservados para manter histórico.
_EXPORT_FIELDS = (
    "uid", "material", "manufacturer", "color_name", "hex_color", "color_id",
    "profile_name", "finish",
    "weight_g", "spools", "status", "variant_id", "sku", "notes",
    "created_at", "updated_at",
)


def export_data():
    """Exporta todo o estoque num envelope versionado (dump lógico).

    Formato:
      {
        "schema_version": <int>,
        "exported_at": "<iso8601>",
        "count": <int>,
        "items": [ { <campos de _EXPORT_FIELDS> }, ... ]
      }

    Estável entre versões do banco: o import de uma versão futura sabe ler
    (e migrar) envelopes gerados por versões anteriores via schema_version.
    """
    items = list_items()
    exported = [{k: it.get(k) for k in _EXPORT_FIELDS} for it in items]
    return {
        "schema_version": INVENTORY_SCHEMA_VERSION,
        "exported_at": _now(),
        "count": len(exported),
        "items": exported,
    }


def _migrate_item(item, from_version, snapshot=None):
    """Migra o dict de um item de um schema_version antigo para o atual.

    Ponto único de evolução: ao subir INVENTORY_SCHEMA_VERSION, adicione aqui
    a transformação incremental (v1→v2, v2→v3, ...).
    """
    v = from_version
    if v < 2:
        # v1 não tinha tipo: profile_name nasce NULL, com inferência segura
        # (mesma regra do backfill) quando o catálogo está disponível.
        item["profile_name"] = _infer_profile(item, snapshot)
        v = 2
    return item


def import_data(payload, replace=False):
    """Importa um envelope de export, com upsert idempotente por uid.

    Args:
        payload: dict no formato de export_data() (aceita também apenas uma
            lista de itens; nesse caso assume-se schema_version atual).
        replace: se True, apaga todos os itens que NÃO estão no payload
            (sincronização espelho). Se False (default), faz merge: cria/atualiza
            os itens do payload e deixa os demais intactos.

    Idempotência: itens são casados pelo `uid`. Reimportar o mesmo envelope não
    duplica nada — apenas reaplica os mesmos valores.

    Returns:
        dict com resumo: {"created", "updated", "deleted", "skipped", "errors"}.
    """
    if isinstance(payload, list):
        items_in = payload
        from_version = INVENTORY_SCHEMA_VERSION
    elif isinstance(payload, dict):
        items_in = payload.get("items", [])
        from_version = int(payload.get("schema_version", INVENTORY_SCHEMA_VERSION))
    else:
        raise ValueError("payload deve ser um objeto de export ou uma lista de itens")

    if from_version > INVENTORY_SCHEMA_VERSION:
        raise ValueError(
            f"schema_version {from_version} é mais novo que o suportado "
            f"({INVENTORY_SCHEMA_VERSION}). Atualize o servidor antes de importar."
        )

    init_db()
    created = updated = skipped = 0
    errors = []
    seen_uids = set()
    snapshot = _catalog_snapshot()

    conn = get_connection()
    try:
        for raw in items_in:
            try:
                item = _migrate_item(dict(raw), from_version, snapshot)
                item["profile_name"] = _import_profile_name(item, snapshot)
                item_uid = (item.get("uid") or "").strip()
                if not item_uid:
                    # Item sem uid (ex.: exportado por ferramenta externa): gera
                    # um novo e trata como criação.
                    item_uid = str(uuid.uuid4())
                    item["uid"] = item_uid
                seen_uids.add(item_uid)

                existing = conn.execute(
                    "SELECT id FROM inventory_items WHERE uid = ?", (item_uid,)
                ).fetchone()

                if existing is None:
                    _insert_from_import(conn, item)
                    created += 1
                else:
                    _update_from_import(conn, existing[0], item)
                    updated += 1
            except Exception as exc:  # não deixa um item ruim abortar o lote
                errors.append({"uid": raw.get("uid") if isinstance(raw, dict) else None,
                               "error": str(exc)})
                skipped += 1

        deleted = 0
        if replace:
            # Remove itens ausentes do payload (modo espelho).
            all_rows = conn.execute("SELECT id, uid FROM inventory_items").fetchall()
            stale = [r[0] for r in all_rows if r[1] not in seen_uids]
            for sid in stale:
                conn.execute("DELETE FROM inventory_items WHERE id = ?", (sid,))
            deleted = len(stale)

        conn.commit()
    finally:
        conn.close()

    return {
        "created": created,
        "updated": updated,
        "deleted": deleted,
        "skipped": skipped,
        "errors": errors,
    }


def _import_color_id(item):
    """color_id do envelope; desconhecido vira None (restauração não aborta)."""
    cid = item.get("color_id")
    return cid if palette.is_valid_id(cid) else None


def _import_profile_name(item, snapshot):
    """profile_name do envelope; vazio/desconhecido no catálogo vira None
    (restauração não aborta). Sem catálogo disponível, preserva o valor."""
    name = item.get("profile_name")
    if not isinstance(name, str) or not name.strip():
        return None
    name = name.strip()
    if snapshot is not None and name not in snapshot["names"]:
        return None
    return name


def _import_weight(item):
    """Peso do envelope: ausente/None => 1000; 0 é preservado."""
    w = item.get("weight_g")
    return 1000 if w is None or w == "" else int(w)


def _insert_from_import(conn, item):
    """Insere um item vindo do import preservando uid e timestamps.

    Não passa por add_item de propósito: o import não deve aplicar validação de
    capacidade (CFS/spool cheios) — está restaurando um estado que já era válido,
    e abortar por limite quebraria a restauração. A validação de capacidade é
    responsabilidade das operações interativas (add/update via UI/API).
    """
    now = _now()
    conn.execute(
        """
        INSERT INTO inventory_items(
            uid, material, manufacturer, color_name, hex_color, color_id,
            profile_name, finish,
            weight_g, spools, status, variant_id, sku, notes,
            created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            item["uid"],
            (item.get("material") or "").strip(),
            (item.get("manufacturer") or "").strip(),
            (item.get("color_name") or "").strip(),
            item.get("hex_color"), _import_color_id(item),
            item.get("profile_name"), item.get("finish"),
            _import_weight(item),
            int(item.get("spools", 1) or 0),
            _normalize_status(item.get("status")),
            item.get("variant_id"), item.get("sku"), item.get("notes"),
            item.get("created_at") or now,
            item.get("updated_at") or now,
        ),
    )


def _update_from_import(conn, item_id, item):
    """Atualiza (por id) um item existente identificado pelo uid, com os valores do import."""
    conn.execute(
        """
        UPDATE inventory_items SET
            material = ?, manufacturer = ?, color_name = ?, hex_color = ?,
            color_id = ?, profile_name = ?,
            finish = ?, weight_g = ?, spools = ?, status = ?, variant_id = ?,
            sku = ?, notes = ?, updated_at = ?
        WHERE id = ?
        """,
        (
            (item.get("material") or "").strip(),
            (item.get("manufacturer") or "").strip(),
            (item.get("color_name") or "").strip(),
            item.get("hex_color"), _import_color_id(item),
            item.get("profile_name"), item.get("finish"),
            _import_weight(item),
            int(item.get("spools", 1) or 0),
            _normalize_status(item.get("status")),
            item.get("variant_id"), item.get("sku"), item.get("notes"),
            item.get("updated_at") or _now(),
            item_id,
        ),
    )


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


def _sort_key_color(item):
    """
    Ordenação padrão dos itens do estoque:
      1º cor (color_name) alfabética
      2º marca (manufacturer) alfabética
    Case-insensitive para não separar 'Azul' de 'azul'.
    """
    return (
        (item.get("color_name") or "").strip().lower(),
        (item.get("manufacturer") or "").strip().lower(),
    )


def _material_groups(items):
    """Agrupa uma lista de itens por material → cores (para a seção de estoque)."""
    groups = {}
    for it in items:
        groups.setdefault(it["material"], []).append(it)
    out = []
    for material, its in sorted(groups.items()):
        # Uma única entrada visual por fabricante + cor + especificação do rolo.
        # As entradas físicas continuam preservadas no banco; a UI as expande
        # apenas quando o usuário precisa gerenciá-las individualmente.
        subgroups = {}
        for it in its:
            key = (
                (it.get("manufacturer") or "").strip().casefold(),
                (it.get("color_name") or "").strip().casefold(),
                (it.get("hex_color") or "").strip().casefold(),
                (it.get("finish") or "").strip().casefold(),
                int(it["weight_g"] if it.get("weight_g") is not None else 1000),
                it.get("variant_id"),
                (it.get("profile_name") or "").strip().casefold(),
            )
            subgroups.setdefault(key, []).append(it)

        cards = []
        for entries in subgroups.values():
            representative = dict(sorted(entries, key=lambda x: x["id"])[0])
            representative["spools"] = sum(int(x.get("spools") or 0) for x in entries)
            representative["entry_count"] = len(entries)
            representative["entry_ids"] = [x["id"] for x in entries]
            representative["entries"] = [dict(x) for x in sorted(entries, key=_sort_key_color)]
            cards.append(representative)

        cards.sort(key=_sort_key_color)
        out.append({
            "material": material,
            "total_spools": sum(i["spools"] for i in its),
            "colors_available": len({
                (i["color_name"], i["hex_color"]) for i in its if i["status"] != STATUS_EMPTY
            }),
            "items": cards,
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

    cfs_items = sorted(by_status(STATUS_CFS), key=_sort_key_color)
    spool_items = sorted(by_status(STATUS_SPOOL), key=_sort_key_color)
    drybox_items = sorted(by_status(STATUS_DRYBOX), key=_sort_key_color)
    open_items = sorted(by_status(STATUS_OPEN), key=_sort_key_color)
    sealed_items = by_status(STATUS_IN_STOCK)
    empty_items = sorted(by_status(STATUS_EMPTY), key=_sort_key_color)

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
