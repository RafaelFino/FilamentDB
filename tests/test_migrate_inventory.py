"""Testes de scripts/migrate_inventory.sh — só com fixtures em tmp_path.

Nunca tocam em data/inventory.db real: todo caso passa --db para uma cópia
temporária (e um catálogo temporário ao lado, via filament.db).
"""
import hashlib
import os
import shutil
import sqlite3
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "migrate_inventory.sh"

pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None, reason="bash ausente"
)

OLD_SCHEMA = """
CREATE TABLE inventory_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uid TEXT,
    material TEXT NOT NULL,
    manufacturer TEXT NOT NULL,
    color_name TEXT NOT NULL,
    hex_color TEXT,
    finish TEXT,
    weight_g INTEGER DEFAULT 1000,
    spools INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'in_stock',
    variant_id INTEGER,
    sku TEXT,
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

ITEMS = [
    # (uid, material, manufacturer, color_name, hex, spools, status, sku)
    ("u1", "PLA", "Sunlu", "Branco", "#FFFFFF", 1, "in_stock", "SKU-1"),
    ("u2", "PETG", "Voolt3D", "Preto Fosco", "#111111", 1, "cfs", None),
    ("u3", "PLA", "Elegoo", "Azul Céu", "#3366FF", 1, "open", None),
    ("u4", "PETG", "Futer3D", "Vermelho", "#CC0000", 1, "empty", None),
    ("u5", "PLA", "Creality", "Cinza", "#888888", 1, "drybox", None),
]


def _make_old_db(path: Path):
    conn = sqlite3.connect(path)
    conn.executescript(OLD_SCHEMA)
    for uid, mat, mfr, color, hexc, spools, status, sku in ITEMS:
        conn.execute(
            "INSERT INTO inventory_items(uid, material, manufacturer, color_name,"
            " hex_color, spools, status, sku, notes, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (uid, mat, mfr, color, hexc, spools, status, sku, f"nota {uid}",
             "2026-01-01T00:00:00+00:00", "2026-01-01T00:00:00+00:00"),
        )
    conn.commit()
    conn.close()


def _make_catalog(path: Path):
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE manufacturers (id INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE materials (id INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE filament_profiles (id INTEGER PRIMARY KEY, profile_name TEXT,
            commercial_name TEXT, manufacturer_id INTEGER, material_id INTEGER);
        CREATE TABLE filament_variants (id INTEGER PRIMARY KEY, filament_id INTEGER,
            sku TEXT, color_name TEXT, hex_color TEXT, finish TEXT);
        INSERT INTO manufacturers VALUES (1, 'Sunlu');
        INSERT INTO materials VALUES (1, 'PLA');
        INSERT INTO filament_profiles VALUES (1, 'Sunlu PLA High Speed', 'PLA HS', 1, 1);
        INSERT INTO filament_variants VALUES (1, 1, 'SKU-1', 'Branco', '#FFFFFF', NULL);
        """
    )
    conn.commit()
    conn.close()


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _cols(path: Path):
    conn = sqlite3.connect(path)
    try:
        return {r[1] for r in conn.execute("PRAGMA table_info(inventory_items)")}
    finally:
        conn.close()


def _rows(path: Path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM inventory_items ORDER BY id")]
    finally:
        conn.close()


@pytest.fixture
def env(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    db = data / "inventory.db"
    _make_old_db(db)
    _make_catalog(data / "filament.db")
    backups = tmp_path / "backups"
    cfg = tmp_path / "config.env"
    cfg.write_text("", encoding="utf-8")
    venv_py = ROOT / ".venv" / "bin" / "python"
    e = {k: v for k, v in os.environ.items()
         if not k.startswith(("FILAMENT", "MIGRATE_", "DB_PATH", "BACKUP_DIR"))}
    e.update({
        "BACKUP_DIR": str(backups),
        "CONFIG_ENV": str(cfg),
        "DB_PATH": str(data / "filament.db"),
        "PYTHON": str(venv_py) if venv_py.exists() else "python3",
    })
    return {"db": db, "backups": backups, "env": e}


def run(env, *args, extra_env=None):
    e = dict(env["env"])
    e.update(extra_env or {})
    return subprocess.run(
        ["bash", str(SCRIPT), "--db", str(env["db"]), *args],
        env=e, capture_output=True, text=True, timeout=120, stdin=subprocess.DEVNULL,
    )


def premigration_backups(env):
    if not env["backups"].exists():
        return []
    return sorted(env["backups"].glob("inventory_premigration_*.db"))


def test_dry_run_nao_altera_original(env):
    before = _sha(env["db"])
    r = run(env, "--dry-run")
    assert r.returncode == 0, r.stdout + r.stderr
    assert _sha(env["db"]) == before
    assert "profile_name" not in _cols(env["db"])
    assert "Total de itens" in r.stdout
    assert premigration_backups(env) == []


def test_execucao_real_adiciona_colunas_e_preserva_itens(env):
    antes = _rows(env["db"])
    r = run(env, "--yes")
    assert r.returncode == 0, r.stdout + r.stderr
    assert {"profile_name", "color_id"} <= _cols(env["db"])
    depois = {x["id"]: x for x in _rows(env["db"])}
    assert len(depois) == len(antes) == 5
    for a in antes:
        d = depois[a["id"]]
        for col in ("uid", "color_name", "hex_color", "weight_g", "status", "material",
                    "manufacturer", "notes", "sku", "created_at"):
            assert d[col] == a[col], col
    # inferência conservadora: só o u1 (sku único + mesma cor) ganha tipo
    por_uid = {x["uid"]: x for x in depois.values()}
    assert por_uid["u1"]["profile_name"] == "Sunlu PLA High Speed"
    assert all(por_uid[u]["profile_name"] is None for u in ("u2", "u3", "u4", "u5"))
    assert "type_missing (reclassificar na UI):  4" in r.stdout


def test_backup_criado(env):
    r = run(env, "--yes")
    assert r.returncode == 0, r.stdout + r.stderr
    bks = premigration_backups(env)
    assert len(bks) == 1
    assert "profile_name" not in _cols(bks[0])  # backup é o estado ANTIGO
    assert len(_rows(bks[0])) == 5


def test_segunda_execucao_idempotente(env):
    assert run(env, "--yes").returncode == 0
    snap = _rows(env["db"])
    r = run(env, "--yes")
    assert r.returncode == 0, r.stdout + r.stderr
    assert _rows(env["db"]) == snap
    assert "Idempotência confirmada" in r.stdout


def test_divergencia_retorna_1_e_mantem_backup(env):
    r = run(env, "--yes", extra_env={"MIGRATE_INVENTORY_FAULT": "delete_row"})
    assert r.returncode == 1, r.stdout + r.stderr
    assert "ROLLBACK" in r.stderr
    bks = premigration_backups(env)
    assert len(bks) == 1
    assert bks[0].exists() and str(bks[0]) in r.stderr
    assert len(_rows(bks[0])) == 5


def test_banco_inexistente_aborta(env):
    env["db"].unlink()
    r = run(env, "--dry-run")
    assert r.returncode != 0
    assert "não encontrado" in r.stderr


def test_sem_yes_e_sem_tty_aborta_sem_alterar(env):
    before = _sha(env["db"])
    r = run(env)
    assert r.returncode != 0
    assert _sha(env["db"]) == before
    assert premigration_backups(env) == []
