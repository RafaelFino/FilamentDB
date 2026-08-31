"""Public, ingest-only HTTP API for FilamentDB price offers."""
from __future__ import annotations

import hmac
import math
from datetime import datetime, timezone
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


def _number(data, name, minimum, maximum):
    value = data.get(name)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number")
    value = float(value)
    if not math.isfinite(value) or value < minimum or value > maximum:
        raise ValueError(f"{name} is out of range")
    return value


def _integer(data, name, minimum, maximum, default=None):
    value = data.get(name, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    if value < minimum or value > maximum:
        raise ValueError(f"{name} is out of range")
    return value


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
    unit_weight_g = _number(data, "unit_weight_g", 1, 100_000)
    basis = data.get("price_basis", "total")
    if basis not in {"unit", "total"}:
        raise ValueError("price_basis must be 'unit' or 'total'")

    currency = data.get("currency", "BRL")
    if not isinstance(currency, str) or len(currency.strip()) != 3:
        raise ValueError("currency must be a 3-letter code")
    currency = currency.strip().upper()

    available = data.get("available")
    if available is not None and not isinstance(available, bool):
        raise ValueError("available must be boolean or null")

    marketplace = data.get("marketplace", False)
    if not isinstance(marketplace, bool):
        raise ValueError("marketplace must be boolean")

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
        "original_price": data.get("original_price"),
        "shipping": data.get("shipping"),
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
            "SELECT fp.filament_key, fp.commercial_name, fp.line, m.name AS material, mf.name AS manufacturer "
            "FROM filament_profiles fp JOIN materials m ON m.id=fp.material_id "
            "JOIN manufacturers mf ON mf.id=fp.manufacturer_id "
            "WHERE fp.active=1 AND fp.tracking=1 ORDER BY m.name,mf.name,fp.line"
        ).fetchall()
        return jsonify({"ok": True, "filaments": [dict(r) for r in rows]})
    finally:
        conn.close()


@bp.post("/ingest/prices")
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
