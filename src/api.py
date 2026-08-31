"""Public, ingest-only HTTP API for FilamentDB price offers."""
from __future__ import annotations

import hmac
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from flask import Blueprint, Flask, jsonify, request

from src import config, database, prices

bp = Blueprint("public_api", __name__, url_prefix="/v1")
MAX_BODY_BYTES = 32 * 1024
SECRET_HEADER = "X-Proxy-Secret"


def _unauthorized():
    return jsonify({"ok": False, "error": "unauthorized"}), 401


def _authorized():
    expected = config.get("FILAMENTDB_PROXY_SECRET", "")
    supplied = request.headers.get(SECRET_HEADER, "")
    return bool(expected) and bool(supplied) and hmac.compare_digest(supplied, expected)


def _json_error(message, status=400, field=None):
    body = {"ok": False, "error": message}
    if field:
        body["field"] = field
    return jsonify(body), status


def _required_string(data, name, max_len):
    value = data.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} is required")
    value = value.strip()
    if len(value) > max_len:
        raise ValueError(f"{name} is too long")
    return value


def _optional_string(data, name, max_len):
    value = data.get(name)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string")
    value = value.strip()
    if len(value) > max_len:
        raise ValueError(f"{name} is too long")
    return value or None


def _clean_number(value):
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        s = re.sub(r"[^0-9,.-]", "", s)
        if not s:
            return None
        if "," in s and "." in s:
            if s.rfind(",") > s.rfind("."):
                s = s.replace(".", "").replace(",", ".")
            else:
                s = s.replace(",", "")
        elif "," in s:
            parts = s.split(",")
            s = s.replace(",", ".") if len(parts[-1]) in (1, 2) else s.replace(",", "")
        elif s.count(".") > 1:
            parts = s.split(".")
            s = "".join(parts[:-1]) + "." + parts[-1]
        try:
            return float(s)
        except ValueError:
            return None
    return None


def _number(data, name, minimum, maximum, default=None):
    raw = data.get(name, default)
    value = _clean_number(raw)
    if value is None:
        raise ValueError(f"{name} must be a number")
    if not math.isfinite(value) or value < minimum or value > maximum:
        raise ValueError(f"{name} is out of range")
    return value


def _weight_g(value):
    if isinstance(value, str):
        s = value.strip().casefold().replace(",", ".")
        m = re.search(r"([-+]?\d+(?:\.\d+)?)\s*(kg|kgs|quilo|quilos|g|gr|grama|gramas)?\b", s)
        if m:
            n = float(m.group(1))
            unit = m.group(2) or "g"
            if unit in {"kg", "kgs", "quilo", "quilos"}:
                n *= 1000
            return n
    return _clean_number(value)


def _clean_integer(value):
    n = _clean_number(value)
    if n is None or not math.isfinite(n) or not n.is_integer():
        return None
    return int(n)


def _integer(data, name, minimum, maximum, default=None):
    value = _clean_integer(data.get(name, default))
    if value is None:
        raise ValueError(f"{name} must be an integer")
    if value < minimum or value > maximum:
        raise ValueError(f"{name} is out of range")
    return value


def _boolean(value, default=None):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        s = value.strip().casefold()
        if s in {"true", "1", "yes", "y", "sim", "s", "available", "disponivel", "disponível", "in stock", "instock"}:
            return True
        if s in {"false", "0", "no", "n", "nao", "não", "unavailable", "indisponivel", "indisponível", "out of stock", "outofstock"}:
            return False
        if s in {"", "null", "none", "unknown", "desconhecido", "indeterminado"}:
            return default
    return default


def _currency(value, default="BRL"):
    if value is None or not str(value).strip():
        return default
    s = str(value).strip().upper()
    aliases = {"R$": "BRL", "REAL": "BRL", "REAIS": "BRL", "RS": "BRL", "$": "USD", "US$": "USD"}
    s = aliases.get(s, s)
    return s if re.fullmatch(r"[A-Z]{3}", s) else default


def _basis(value, default="total"):
    if value is None or not str(value).strip():
        return default
    s = str(value).strip().casefold().replace("-", "_").replace(" ", "_")
    if s in {"unit", "unidade", "unitario", "unitário", "por_unidade", "each", "per_unit"}:
        return "unit"
    if s in {"total", "kit", "bundle", "package", "pacote", "conjunto"}:
        return "total"
    return default


def _validate_offer(data):
    if not isinstance(data, dict):
        raise ValueError("JSON body must be an object")

    key = _required_string(data, "filament_key", 240)
    store = _required_string(data, "store", 120)
    url = _required_string(data, "url", 2048)
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("url must be an absolute http(s) URL")

    price = _number(data, "price", 0.01, 10_000_000)
    quantity = _integer(data, "quantity", 1, 10_000, 1)
    unit_weight_g = _weight_g(data.get("unit_weight_g"))
    if unit_weight_g is None or not math.isfinite(unit_weight_g) or unit_weight_g < 1 or unit_weight_g > 100_000:
        raise ValueError("unit_weight_g must be a number")
    basis = _basis(data.get("price_basis"), "total")
    currency = _currency(data.get("currency"), "BRL")
    available = _boolean(data.get("available"), None)
    marketplace = _boolean(data.get("marketplace"), False)

    total_price = data.get("total_price")
    if total_price is None:
        total_price = price * quantity if basis == "unit" else price
    else:
        total_price = _number({"value": total_price}, "value", 0.01, 10_000_000)

    collected_at = data.get("collected_at")
    if collected_at is None:
        collected_at = datetime.now(timezone.utc).isoformat()
    elif not isinstance(collected_at, str) or len(collected_at) > 80:
        raise ValueError("collected_at must be an ISO-8601 string")
    else:
        try:
            datetime.fromisoformat(collected_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("collected_at must be ISO-8601") from exc

    return {
        "filament_key": key,
        "store": store,
        "domain": parsed.netloc.lower(),
        "marketplace": marketplace,
        "url": url,
        "title": _required_string(data, "title", 500),
        "price": price,
        "original_price": (_clean_number(data.get("original_price")) if data.get("original_price") is not None else None),
        "shipping": (_clean_number(data.get("shipping")) if data.get("shipping") is not None else None),
        "currency": currency,
        "available": available,
        "coupon": _optional_string(data, "coupon", 500),
        "color_name": _optional_string(data, "color_name", 160),
        "seller": _optional_string(data, "seller", 240),
        "quantity": quantity,
        "unit_weight_g": unit_weight_g,
        "price_basis": basis,
        "total_price": total_price,
        "external_id": _optional_string(data, "external_id", 240),
        "source": _optional_string(data, "source", 120) or "api",
        "notes": _optional_string(data, "notes", 2000),
    }, None


@bp.get("/health")
def health():
    return jsonify({"status": "ok", "service": "filamentdb-api"})


def ready():
    if not config.get("FILAMENTDB_PROXY_SECRET", ""):
        return jsonify({"status": "not_ready", "service": "filamentdb-api", "reason": "secret_not_configured"}), 503

    conn = None
    try:
        conn = database.get_db_connection()
        conn.execute("SELECT 1 FROM filament_profiles LIMIT 1").fetchone()
        return jsonify({"status": "ready", "service": "filamentdb-api"}), 200
    except Exception:
        return jsonify({"status": "not_ready", "service": "filamentdb-api", "reason": "database_unavailable"}), 503
    finally:
        if conn is not None:
            conn.close()


bp.add_url_rule("/health", endpoint="v1_health", view_func=health, methods=["GET"])
bp.add_url_rule("/health/ready", endpoint="v1_ready", view_func=ready, methods=["GET"])


@bp.get("/catalog/filaments")
def catalog_filaments():
    if not _authorized():
        return _unauthorized()
    conn = database.get_db_connection()
    try:
        rows = conn.execute(
            "SELECT "
            "CAST(fp.id AS TEXT) AS technical_key, "
            "fp.filament_key AS filament_key, fp.tracking, "
            "fp.commercial_name, fp.line, m.name AS material, mf.name AS manufacturer "
            "FROM filament_profiles fp JOIN materials m ON m.id=fp.material_id "
            "JOIN manufacturers mf ON mf.id=fp.manufacturer_id "
            "WHERE fp.active=1 AND fp.tracking=1 "
            "AND UPPER(TRIM(m.name)) IN ('PLA','PETG') "
            "AND fp.filament_key IS NOT NULL AND TRIM(fp.filament_key) <> '' "
            "ORDER BY m.name,mf.name,fp.line"
        ).fetchall()
        return jsonify({"ok": True, "filaments": [dict(r) for r in rows]})
    finally:
        conn.close()


@bp.get("/agent/instructions")
def agent_instructions():
    if not _authorized():
        return _unauthorized()
    root = Path(__file__).resolve().parents[1]
    sources_path = root / "data" / "price-sources.json"
    try:
        sources = json.loads(sources_path.read_text(encoding="utf-8"))
        sources = [{"name": s.get("name"), "domain": s.get("domain"), "marketplace": bool(s.get("marketplace"))} for s in sources if s.get("enabled", True)]
    except Exception:
        sources = []
    allowed_domains = sorted({s["domain"].lower() for s in sources if s.get("domain")})
    input_schema = {
        "type": "object",
        "required": ["filament_key", "store", "url", "title", "price", "unit_weight_g"],
        "properties": {
            "filament_key": {"type": "string"}, "store": {"type": "string"},
            "url": {"type": "string", "format": "uri", "description": "Direct product/offer URL; HTTP(S) only."},
            "title": {"type": "string"}, "price": {"type": ["number", "string"]},
            "original_price": {"type": ["number", "string", "null"]},
            "shipping": {"type": ["number", "string", "null"]},
            "currency": {"type": ["string", "null"], "default": "BRL"},
            "available": {"type": ["boolean", "string", "number", "null"]},
            "marketplace": {"type": ["boolean", "string", "number", "null"]},
            "quantity": {"type": ["integer", "number", "string"]},
            "unit_weight_g": {"type": ["number", "string"]},
            "price_basis": {"type": ["string", "null"], "enum": ["unit", "total", "unidade", "unitario", "unitário", "por_unidade", "total", "kit", "bundle"]},
            "total_price": {"type": ["number", "string", "null"]},
            "coupon": {"type": ["string", "null"]}, "color_name": {"type": ["string", "null"]},
            "seller": {"type": ["string", "null"]}, "external_id": {"type": ["string", "null"]},
            "source": {"type": ["string", "null"]}, "notes": {"type": ["string", "null"]}
        },
        "allowed_url_domains": allowed_domains,
        "normalization": "The API tolerates common LLM representations for booleans, numbers, currency, price basis, and optional null/empty values; it never invents missing facts."
    }
    return jsonify({
        "ok": True,
        "version": 2,
        "mission": "Pesquisar preços atuais de filamentos PLA e PETG no Brasil e publicar somente ofertas diretamente verificáveis.",
        "catalog_endpoint": "/v1/catalog/filaments",
        "offer_endpoint": "/v1/agent/offers",
        "input_schema": input_schema,
        "allowed_domains": allowed_domains,
        "sources": sources,
        "rules": [
            "Use o filament_key exatamente como fornecido pelo catálogo; nunca invente uma chave.",
            "O produto precisa corresponder a fabricante, material e linha/modelo do catálogo.",
            "Busque cada fonte configurada e preserve todas as ofertas verificáveis, não apenas a mais barata.",
            "Use URL direta da página do produto/oferta, nunca página de resultados.",
            "Registre preço observado, moeda, quantidade e peso por rolo sem conversões inventadas.",
            "Para kits, quantity é o número de rolos e total_price é o preço total do kit.",
            "Para preço por unidade, price_basis=unit e total_price=price*quantity.",
            "Não fabrique disponibilidade, vendedor, SKU, preço, cupom ou URL.",
            "Se não houver oferta confiável, não publique uma oferta.",
        ],
    })


@bp.post("/ingest/prices")
@bp.post("/agent/offers")
def ingest_price():
    if not _authorized():
        return _unauthorized()
    if request.content_length and request.content_length > MAX_BODY_BYTES:
        return _json_error("request too large", 413)
    if not request.is_json:
        return _json_error("Content-Type must be application/json", 415)

    try:
        payload = request.get_json(silent=False)
        offer, _ = _validate_offer(payload)
    except (ValueError, TypeError) as exc:
        return _json_error(str(exc), 400)
    except Exception:
        return _json_error("invalid JSON", 400)

    key = prices._snapshot_key(offer)
    catalog = prices._catalog_map()
    if key not in catalog:
        return _json_error("unknown_or_untracked_filament", 404, "filament_key")

    conn = None
    try:
        conn = prices.get_connection()
        accepted = prices._upsert_snapshot_offer(
            conn,
            offer,
            catalog,
            offer["collected_at"],
            offer["source"],
        )
        if not accepted:
            conn.rollback()
            return _json_error("offer could not be imported", 422)

        row = conn.execute(
            "SELECT id FROM offers WHERE filament_key=? AND store_id=(SELECT id FROM stores WHERE name=?) "
            "AND url=? AND quantity=? AND unit_weight_g=? AND price_basis=? LIMIT 1",
            (key, offer["store"], offer["url"], offer["quantity"], offer["unit_weight_g"], offer["price_basis"]),
        ).fetchone()
        conn.commit()
        return jsonify({"ok": True, "status": "accepted", "offer_id": row[0] if row else None}), 201
    except Exception as exc:
        if conn is not None:
            conn.rollback()
        print(f"[ERROR] price ingest failed: {type(exc).__name__}: {exc}")
        return _json_error("import_failed", 500)
    finally:
        if conn is not None:
            conn.close()


def register_public_api(app: Flask):
    app.config["MAX_CONTENT_LENGTH"] = MAX_BODY_BYTES
    app.register_blueprint(bp)
    # The public service exposes only these two unauthenticated operational endpoints
    # at the root. Pangolin protects the normal web application separately.
    app.add_url_rule("/health", endpoint="public_api_health", view_func=health, methods=["GET"])
    app.add_url_rule("/health/ready", endpoint="public_api_ready", view_func=ready, methods=["GET"])
