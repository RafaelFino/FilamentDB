"""
palette.py — Paleta de cores básicas (sólidas) para cadastro de filamentos.

Fonte única: src/color_palette.json (versionado). Cada cor tem id estável
(slug), nome pt-BR e hex canônico. O backend valida sempre contra esta lista;
a UI a consome via GET /api/color-palette.
"""

import json
import re
from pathlib import Path

PALETTE_PATH = Path(__file__).resolve().parent / "color_palette.json"

_ID_RE = re.compile(r"^[a-z]+(-[a-z]+)*$")
_HEX_RE = re.compile(r"^#[0-9A-F]{6}$")

_cache = None


def load():
    """Carrega (com cache) e valida a estrutura da paleta."""
    global _cache
    if _cache is None:
        with open(PALETTE_PATH, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data.get("version"), int):
            raise ValueError("color_palette.json: 'version' deve ser inteiro")
        seen = set()
        for c in data.get("colors", []):
            if not _ID_RE.match(c.get("id", "")) or not c.get("name") \
                    or not _HEX_RE.match(c.get("hex", "")):
                raise ValueError(f"color_palette.json: cor inválida: {c!r}")
            if c["id"] in seen:
                raise ValueError(f"color_palette.json: id duplicado: {c['id']}")
            seen.add(c["id"])
        _cache = data
    return _cache


def list_colors():
    return list(load()["colors"])


def get_color(color_id):
    """Retorna a cor (dict) ou None se o id não pertence à paleta."""
    if not isinstance(color_id, str):
        return None
    for c in load()["colors"]:
        if c["id"] == color_id:
            return c
    return None


def is_valid_id(color_id):
    return get_color(color_id) is not None
