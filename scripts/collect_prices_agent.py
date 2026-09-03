#!/usr/bin/env python3
"""API-driven agentic price collector for FilamentDB."""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from openai import OpenAI

ROOT = Path(__file__).resolve().parents[1]
CATALOG_DB = ROOT / "data" / "filament.db"
SNAPSHOT_DIR = ROOT / "data" / "price-data"
TZ = ZoneInfo("America/Sao_Paulo")
API_URL = os.getenv("FILAMENTDB_API_URL", "https://filamentdb-api.learnops.duckdns.org").rstrip("/")
API_SECRET = os.getenv("FILAMENTDB_API_SECRET", "")
MISTRAL_MODEL = os.getenv("MISTRAL_MODEL", "mistral-small-latest")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.7-flash")
MAX_TURNS = int(os.getenv("PRICE_AGENT_MAX_TURNS", "30"))

class ProviderError(RuntimeError):
    pass


def api_call(method: str, path: str, payload=None):
    if not API_SECRET:
        raise ProviderError("FILAMENTDB_API_SECRET não configurado")
    body = None
    headers = {"Accept": "application/json", "X-Proxy-Secret": API_SECRET}
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(API_URL + path, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            raw = response.read().decode("utf-8", errors="replace")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        raise ProviderError(f"FilamentDB API HTTP {exc.code}: {raw[:1000]}") from exc
    except urllib.error.URLError as exc:
        raise ProviderError(f"FilamentDB API connection failed: {exc.reason}") from exc


def load_catalog():
    conn = sqlite3.connect(CATALOG_DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT fp.filament_key, fp.tracking, fp.commercial_name,
               fp.line, fp.color, fp.line_positioning, fp.line_tier, fp.line_category,
               fp.line_finish, fp.line_target_use, fp.surface_finish,
               m.name AS material_name, mf.name AS manufacturer_name,
               GROUP_CONCAT(DISTINCT fv.color_name) AS variant_colors,
               GROUP_CONCAT(DISTINCT CAST(fv.weight_g AS TEXT)) AS variant_weights
        FROM filament_profiles fp
        JOIN materials m ON m.id = fp.material_id
        JOIN manufacturers mf ON mf.id = fp.manufacturer_id
        LEFT JOIN filament_variants fv ON fv.filament_id = fp.id
        WHERE fp.active = 1 AND fp.tracking = 1
          AND UPPER(TRIM(m.name)) IN ('PLA','PETG')
          AND fp.filament_key IS NOT NULL AND TRIM(fp.filament_key) <> ''
        GROUP BY m.name, mf.name, fp.line
        ORDER BY m.name, mf.name, fp.line
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def search_web(query: str, max_results: int = 8):
    """Search the web without turning an empty/blocked backend into an agent failure."""
    from ddgs import DDGS

    limit = max(1, min(max_results, 10))
    attempts = [
        {"region": "br-pt", "safesearch": "off"},
        {"region": "wt-wt", "safesearch": "off"},
    ]
    errors = []
    for options in attempts:
        try:
            results = DDGS(timeout=60).text(query, max_results=limit, **options)
            if results:
                return [{"title": r.get("title", ""), "url": r.get("href", ""), "snippet": r.get("body", "")} for r in results]
        except Exception as exc:
            errors.append(str(exc))
    if errors:
        print(f"[WARN] busca web indisponível: {errors[-1]}", flush=True)
    return []


def make_tools(item):
    return [
        {"type": "function", "function": {"name": "search_web", "description": "Search the web for current filament offers.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}, "max_results": {"type": "integer"}}, "required": ["query"]}}},
        {"type": "function", "function": {"name": "submit_offer", "description": "Record a real, verified offer for the current filament_key. The offer is accumulated into the daily snapshot; it is validated and published afterwards. Always include unit_weight_g (grams per roll) and quantity (number of rolls). Use price_basis='unit' when price is per roll, 'total' when it is the whole package.", "parameters": {"type": "object", "properties": {"filament_key": {"type": "string"}, "store": {"type": "string"}, "url": {"type": "string"}, "title": {"type": "string"}, "price": {"type": "number"}, "original_price": {"type": ["number", "null"]}, "shipping": {"type": ["number", "null"]}, "total_price": {"type": ["number", "null"]}, "currency": {"type": "string"}, "availability": {"type": ["string", "null"]}, "quantity": {"type": ["number", "null"]}, "unit_weight_g": {"type": ["number", "null"]}, "price_basis": {"type": ["string", "null"]}, "seller": {"type": ["string", "null"]}, "external_id": {"type": ["string", "null"]}}, "required": ["filament_key", "store", "url", "title", "price", "currency"]}}}
    ]


def _to_number(value):
    """Best-effort numeric coercion tolerant of common LLM string formats."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        import re
        s = re.sub(r"[^0-9,.-]", "", s)
        if not s:
            return None
        if "," in s and "." in s:
            s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
        elif "," in s:
            parts = s.split(",")
            s = s.replace(",", ".") if len(parts[-1]) in (1, 2) else s.replace(",", "")
        try:
            return float(s)
        except ValueError:
            return None
    return None


def normalize_offer(args, filament_key):
    """Build a complete, self-contained offer dict matching the ingest/validator contract.

    The agent only accumulates offers in memory; publication happens later via
    publish_price_snapshot.py. This keeps the snapshot as the source of truth.
    """
    price = _to_number(args.get("price"))
    if price is None or price <= 0:
        raise ProviderError(f"submit_offer com preço inválido: {args.get('price')!r}")

    quantity = _to_number(args.get("quantity"))
    quantity = int(quantity) if quantity and quantity >= 1 else 1

    unit_weight_g = _to_number(args.get("unit_weight_g"))
    if unit_weight_g is None or unit_weight_g <= 0:
        raise ProviderError(f"submit_offer sem unit_weight_g válido: {args.get('unit_weight_g')!r}")

    basis = str(args.get("price_basis") or "total").strip().casefold()
    basis = "unit" if basis in {"unit", "unidade", "unitario", "unitário", "por_unidade", "each", "per_unit"} else "total"

    total_price = _to_number(args.get("total_price"))
    if total_price is None or total_price <= 0:
        total_price = round(price * quantity, 2) if basis == "unit" else price

    url = str(args.get("url") or "").strip()
    if not url.startswith(("http://", "https://")):
        raise ProviderError(f"submit_offer com URL inválida: {url!r}")

    currency = str(args.get("currency") or "BRL").strip().upper() or "BRL"

    offer = {
        "filament_key": filament_key,
        "store": str(args.get("store") or "").strip(),
        "url": url,
        "title": str(args.get("title") or "").strip(),
        "price": round(price, 2),
        "currency": currency,
        "quantity": quantity,
        "unit_weight_g": round(unit_weight_g, 2),
        "price_basis": basis,
        "total_price": round(total_price, 2),
    }
    if not offer["store"]:
        raise ProviderError("submit_offer sem store")
    if not offer["title"]:
        raise ProviderError("submit_offer sem title")

    # Optional fields preserved when present.
    for src, dst in (("original_price", "original_price"), ("shipping", "shipping"), ("seller", "seller"), ("color_name", "color_name"), ("external_id", "external_id"), ("coupon", "coupon")):
        val = args.get(src)
        if val is not None and str(val).strip() != "":
            offer[dst] = _to_number(val) if src in ("original_price", "shipping") else str(val).strip()
    avail = args.get("availability", args.get("available"))
    if avail is not None:
        offer["available"] = avail
    offer["source"] = str(args.get("store") or "agentic").strip()
    return offer


def _offer_dedupe_key(offer):
    """Offer identity, mirroring the API's offer_key (store|url|qty|weight|basis).

    Two offers with the same identity are the same product listing; the newer
    one supersedes the older so re-runs update instead of duplicating.
    """
    return (
        str(offer.get("store", "")).strip().casefold(),
        str(offer.get("url", "")).strip(),
        int(offer.get("quantity", 1) or 1),
        round(float(offer.get("unit_weight_g", 0) or 0), 2),
        str(offer.get("price_basis", "total")).strip().casefold(),
    )


def merge_offers(existing, fresh):
    """Merge two offer lists deduplicating by offer identity.

    Fresh offers win over existing ones with the same identity (a re-run picks
    up the latest observed price/availability). Order is stable: existing first,
    then any genuinely new offers.
    """
    by_key = {}
    order = []
    for offer in list(existing) + list(fresh):
        try:
            key = _offer_dedupe_key(offer)
        except (TypeError, ValueError):
            continue
        if key not in by_key:
            order.append(key)
        by_key[key] = offer  # later (fresh) wins
    return [by_key[k] for k in order]


class AgentProvider:
    def __init__(self, client, model):
        self.client = client
        self.model = model
        self.name = "agent"

    def run(self, item, today):
        try:
            instructions = api_call("GET", "/v1/agent/instructions?filament_key=" + urllib.parse.quote(item["filament_key"]))
        except ProviderError as exc:
            # The instructions endpoint is a convenience, not a hard dependency.
            # If it is unavailable, fall back to local prompts instead of aborting
            # the whole collection.
            print(f"[WARN] {self.name}: /v1/agent/instructions indisponível ({exc}); usando fallback local.", flush=True)
            instructions = {}
        system_prompt = instructions.get("system_prompt", "").strip()
        user_prompt = instructions.get("user_prompt", "").strip()
        if not system_prompt or not user_prompt:
            rules = instructions.get("rules") or []
            system_prompt = (
                "Você é um agente de pesquisa de preços do FilamentDB. "
                "Encontre ofertas reais e atuais no Brasil, verifique as páginas diretamente "
                "e nunca invente dados. Use exatamente o filament_key fornecido."
            )
            user_prompt = (
                f"Pesquise ofertas atuais para o filament_key exato: {item['filament_key']}. "
                "Use as ferramentas disponíveis e publique somente ofertas verificáveis. "
                + (" Regras: " + "; ".join(str(r) for r in rules) if rules else "")
            )
            print(f"[WARN] {self.name}: API não retornou prompts; usando fallback local.", flush=True)
        messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]
        offers = []
        for turn in range(MAX_TURNS):
            response = self.client.chat.completions.create(model=self.model, messages=messages, tools=make_tools(item), tool_choice="auto")
            msg = response.choices[0].message
            messages.append(msg)
            calls = msg.tool_calls or []
            if not calls:
                print(f"[INFO] {self.name} terminou sem novas tool calls após {turn + 1} ciclo(s).", flush=True)
                return offers
            for call in calls:
                name = call.function.name
                args = json.loads(call.function.arguments or "{}")
                if name == "search_web":
                    result = search_web(args.get("query", ""), args.get("max_results", 8))
                elif name == "submit_offer":
                    try:
                        offer = normalize_offer(args, item["filament_key"])
                        offers.append(offer)
                        result = {"ok": True, "status": "recorded", "offer": offer}
                        print(f"[OK] {self.name} registrou oferta: {offer['filament_key']} | {offer['store']} | R$ {offer['total_price']}", flush=True)
                    except ProviderError as exc:
                        # Do not kill the whole run for one malformed offer; tell the model to fix it.
                        result = {"ok": False, "error": str(exc)}
                        print(f"[WARN] {self.name}: oferta rejeitada localmente: {exc}", flush=True)
                else:
                    raise ProviderError(f"{self.name}: ferramenta desconhecida: {name}")
                messages.append({"role": "tool", "tool_call_id": call.id, "name": name, "content": json.dumps(result, ensure_ascii=False)})
        raise ProviderError(f"{self.name}: excedeu {MAX_TURNS} ciclos de ferramentas")


def providers():
    result = []
    if os.getenv("MISTRAL_API_KEY"):
        result.append(AgentProvider(OpenAI(base_url="https://api.mistral.ai/v1", api_key=os.environ["MISTRAL_API_KEY"], timeout=180), MISTRAL_MODEL))
        result[-1].name = "mistral"
    if os.getenv("GEMINI_API_KEY"):
        result.append(AgentProvider(OpenAI(base_url="https://generativelanguage.googleapis.com/v1beta/openai/", api_key=os.environ["GEMINI_API_KEY"], timeout=180), GEMINI_MODEL))
        result[-1].name = "gemini"
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date")
    args = parser.parse_args()
    today = args.date or datetime.now(TZ).date().isoformat()
    catalog = load_catalog()
    limit = int(os.getenv("PRICE_AGENT_MAX_PROFILES", "0") or "0")
    if limit > 0:
        catalog = catalog[:limit]
    if not catalog:
        raise RuntimeError("Nenhum perfil PLA/PETG ativo foi encontrado")
    path = SNAPSHOT_DIR / f"{today}.json"
    # Re-running on the same day is idempotent: instead of failing or blindly
    # overwriting, we merge into the existing snapshot (dedupe by offer identity,
    # fresh wins). ALLOW_SNAPSHOT_REPLACE=1 forces a clean slate (ignore existing).
    existing_offers = []
    if path.exists() and not os.getenv("ALLOW_SNAPSHOT_REPLACE"):
        try:
            prev = json.loads(path.read_text(encoding="utf-8"))
            existing_offers = prev.get("offers", []) if isinstance(prev, dict) else []
            print(f"[INFO] Snapshot do dia já existe com {len(existing_offers)} oferta(s); nova coleta fará merge idempotente.", flush=True)
        except (ValueError, OSError) as exc:
            print(f"[WARN] Não foi possível ler snapshot existente ({exc}); recomeçando do zero.", flush=True)
            existing_offers = []
    order = [x.strip().casefold() for x in os.getenv("PRICE_AGENT_PROVIDERS", "mistral,gemini").split(",") if x.strip()]
    available = {p.name: p for p in providers()}
    selected = [available[x] for x in order if x in available]
    if not selected:
        raise RuntimeError("Nenhum agente configurado com chave disponível")
    all_offers = []
    collection = []
    print(f"[INFO] Catálogo monitorado: {len(catalog)} perfis; agentes: {', '.join(p.name for p in selected)}", flush=True)
    for index, item in enumerate(catalog, 1):
        print(f"[INFO] Pesquisando {index}/{len(catalog)}: {item['filament_key']}", flush=True)
        last_error = None
        for provider in selected:
            try:
                print(f"[INFO]   -> agente {provider.name}", flush=True)
                offers = provider.run(item, today)
                all_offers.extend(offers)
                collection.append({"filament_key": item["filament_key"], "color": item.get("color"), "store": "agentic", "status": "found" if offers else "not_found", "offers_found": len(offers), "notes": f"Pesquisa agentic via {provider.name}; ofertas gravadas diretamente na API."})
                last_error = None
                break
            except ProviderError as exc:
                last_error = exc
                print(f"[WARN]   -> {exc}", flush=True)
        else:
            raise RuntimeError(f"Todos os agentes falharam para {item['filament_key']}: {last_error}")
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    merged_offers = merge_offers(existing_offers, all_offers)
    payload = {"schema_version": 2, "snapshot_date": today, "collected_at": datetime.now(TZ).isoformat(), "collector": "FilamentDB API-driven AI Price Agent", "collector_version": "2.0", "scope": {"tracked_profiles": len(catalog), "sources": "API /v1/agent/instructions"}, "collection": collection, "offers": merged_offers, "notes": "Snapshot é a fonte de verdade: ofertas coletadas pelos agentes, validadas offline e publicadas na API por publish_price_snapshot.py."}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    added = len(merged_offers) - len(existing_offers)
    print(f"[OK] Snapshot escrito: {path}; ofertas={len(merged_offers)} (novas nesta coleta: {len(all_offers)}, líquidas após merge: {added})", flush=True)

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        raise
