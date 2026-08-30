#!/usr/bin/env python3
"""Collect tracked filament prices with an AI web-search agent.

The collector reads the authoritative filament.db catalog, searches configured
sources through the OpenAI Responses API web-search tool, writes one immutable
JSON snapshot, and never touches price-history.db.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from openai import OpenAI

ROOT = Path(__file__).resolve().parents[1]
CATALOG_DB = ROOT / "filament.db"
SOURCES_PATH = ROOT / "data" / "price-sources.json"
SNAPSHOT_DIR = ROOT / "data" / "price-data"
TZ = ZoneInfo("America/Sao_Paulo")
BATCH_SIZE = int(os.getenv("PRICE_AGENT_BATCH_SIZE", "2"))
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openrouter/free")


class ProviderError(RuntimeError):
    pass


class Provider:
    name = "unknown"
    def available(self):
        return False
    def collect(self, prompt):
        raise NotImplementedError


class GroqProvider(Provider):
    name = "groq"
    def __init__(self):
        key = os.getenv("GROQ_API_KEY")
        self.client = OpenAI(base_url="https://api.groq.com/openai/v1", api_key=key) if key else None
    def available(self):
        return self.client is not None
    def collect(self, prompt):
        try:
            response = self.client.chat.completions.create(model=GROQ_MODEL, messages=[{"role":"user","content":prompt}], tools=[{"type":"browser_search"}], tool_choice="required", response_format={"type":"json_object"}, reasoning_effort="low", max_completion_tokens=4000, temperature=0.2)
            content = response.choices[0].message.content
            if not content: raise ProviderError("Groq retornou resposta sem conteúdo")
            return json.loads(content)
        except Exception as exc:
            raise ProviderError(f"Groq: {exc}") from exc


class GeminiProvider(Provider):
    name = "gemini"
    def __init__(self):
        key = os.getenv("GEMINI_API_KEY")
        self.client = None
        if key:
            try:
                from google import genai
                from google.genai import types
                self.client = genai.Client(api_key=key)
                self.types = types
            except Exception as exc:
                print(f"[WARN] Gemini SDK indisponível: {exc}")
    def available(self):
        return self.client is not None
    def collect(self, prompt):
        try:
            config = self.types.GenerateContentConfig(tools=[self.types.Tool(google_search=self.types.GoogleSearch())], response_mime_type="application/json")
            response = self.client.models.generate_content(model=GEMINI_MODEL, contents=prompt, config=config)
            content = response.text
            if not content: raise ProviderError("Gemini retornou resposta sem conteúdo")
            return json.loads(content)
        except Exception as exc:
            raise ProviderError(f"Gemini: {exc}") from exc


class OpenRouterProvider(Provider):
    name = "openrouter"
    def __init__(self):
        key = os.getenv("OPENROUTER_API_KEY")
        self.enabled = os.getenv("OPENROUTER_ENABLE_WEB_SEARCH", "0") == "1"
        self.client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=key) if key and self.enabled else None
    def available(self):
        return self.client is not None
    def collect(self, prompt):
        try:
            response = self.client.chat.completions.create(model=OPENROUTER_MODEL, messages=[{"role":"user","content":prompt}], plugins=[{"id":"web","max_results":5}], response_format={"type":"json_object"}, max_tokens=4000, temperature=0.2)
            content = response.choices[0].message.content
            if not content: raise ProviderError("OpenRouter retornou resposta sem conteúdo")
            return json.loads(content)
        except Exception as exc:
            raise ProviderError(f"OpenRouter: {exc}") from exc


def providers():
    return [GroqProvider(), GeminiProvider(), OpenRouterProvider()]


def load_sources():
    sources = json.loads(SOURCES_PATH.read_text(encoding="utf-8"))
    return [s for s in sources if s.get("enabled", True)]


def load_catalog():
    if not CATALOG_DB.exists():
        raise RuntimeError(f"CatÃ¡logo ausente: {CATALOG_DB}")
    conn = sqlite3.connect(CATALOG_DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT
            LOWER(TRIM(m.name)) || '|' || LOWER(TRIM(mf.name)) || '|' || LOWER(TRIM(fp.line)) AS filament_key,
            fp.commercial_name, fp.profile_name,
            fp.line, fp.line_positioning, fp.line_tier, fp.line_category,
            fp.line_finish, fp.line_target_use, fp.color, fp.surface_finish,
            m.name AS material_name, mf.name AS manufacturer_name,
            GROUP_CONCAT(DISTINCT fv.color_name) AS variant_colors,
            GROUP_CONCAT(DISTINCT CAST(fv.weight_g AS TEXT)) AS variant_weights
        FROM filament_profiles fp
        JOIN materials m ON m.id = fp.material_id
        JOIN manufacturers mf ON mf.id = fp.manufacturer_id
        LEFT JOIN filament_variants fv ON fv.filament_id = fp.id
        WHERE fp.active = 1
          AND UPPER(TRIM(m.name)) IN ('PLA', 'PETG')
          AND fp.line IS NOT NULL
          AND TRIM(fp.line) <> ''
        GROUP BY m.name, mf.name, fp.line
        ORDER BY m.name, mf.name, fp.line
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def chunked(items, size):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def schema():
    nullable_number = {"type": ["number", "null"]}
    nullable_string = {"type": ["string", "null"]}
    offer = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "filament_key": {"type": "string"},
            "material": {"type": "string"},
            "manufacturer": {"type": "string"},
            "line": {"type": "string"},
            "store": {"type": "string"},
            "domain": {"type": "string"},
            "marketplace": {"type": "boolean"},
            "url": {"type": "string"},
            "title": {"type": "string"},
            "price": {"type": "number"},
            "original_price": nullable_number,
            "shipping": nullable_number,
            "currency": {"type": "string"},
            "available": {"type": ["integer", "null"]},
            "coupon": nullable_string,
            "color_name": nullable_string,
            "seller": nullable_string,
            "quantity": {"type": "integer"},
            "unit_weight_g": {"type": "number"},
            "price_basis": {"type": "string", "enum": ["unit", "total"]},
            "total_price": {"type": "number"},
            "external_id": nullable_string,
            "source": {"type": "string"},
            "notes": nullable_string,
        },
        "required": [
            "filament_key", "material", "manufacturer", "line", "store", "domain",
            "marketplace", "url", "title", "price", "original_price", "shipping",
            "currency", "available", "coupon", "color_name", "seller", "quantity",
            "unit_weight_g", "price_basis", "total_price", "external_id", "source", "notes"
        ],
    }
    result = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "offers": {"type": "array", "items": offer},
            "collection": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "filament_key": {"type": "string"},
                        "color": nullable_string,
                        "store": {"type": "string"},
                        "status": {"type": "string", "enum": ["found", "not_found", "partial", "error"]},
                        "offers_found": {"type": "integer"},
                        "notes": {"type": "string"},
                    },
                    "required": ["filament_key", "color", "store", "status", "offers_found", "notes"],
                },
            },
        },
        "required": ["offers", "collection"],
    }
    return result


def build_prompt(catalog, sources, today):
    source_lines = "\n".join(
        f"- {s['name']} | domain: {s['domain']} | marketplace: {bool(s.get('marketplace'))}"
        for s in sources
    )
    catalog_json = json.dumps(catalog, ensure_ascii=False, separators=(",", ":"))
    return f"""
You are the daily price-acquisition agent for FilamentDB. Today is {today} in America/Sao_Paulo.

MISSION
Research current Brazilian prices for EVERY tracked catalog item below and EVERY configured source. Do not return only the cheapest offer. Return every relevant, directly verifiable offer you can find during this run, including normal prices, promotions, coupons when observable, kits, multi-roll bundles, and wholesale tiers.

CONFIGURED SOURCES
{source_lines}

CATALOG IS AUTHORITATIVE
The catalog rows below are the only identities you may use. Preserve filament_key exactly. Never invent or normalize a new filament_key. Manufacturer, material, and line must match the catalog item. A marketplace seller may be a different company, but the product itself must match the catalog manufacturer.

IMPORTANT PRODUCT RULES
- PLA and PETG only; the tracked catalog already defines the scope.
- SUNLU Meta, Matte, High Speed and High Speed Matte are distinct lines. Never merge them.
- Premium, Matte/Velvet, High Speed/High Fluidity lines remain distinct when the catalog distinguishes them.
- Color matters. Search all colors explicitly present in the catalog and record additional colors only when a directly verified listing clearly exposes them for the same filament_key.
- A Voolt3D listing must never be assigned to an Elegoo, SUNLU, 3D Lab, F3D, eSUN or Creality filament_key merely because the material/price is similar.
- A marketplace result is valid only when the product identity is clear enough to verify manufacturer + material + line/model + weight.

OFFER RULES
- URL must be the direct product/offer page, never a search-results page.
- Prefer the Brazilian storefront/page and BRL price when available.
- quantity = number of rolls included or the minimum tier quantity.
- unit_weight_g = grams per roll.
- price_basis = total when the displayed price is for the whole package; unit when the displayed price is per roll, especially wholesale tiers.
- total_price must be the total price for the stated quantity. For price_basis=unit, calculate price * quantity.
- Never divide a price by 1000 or otherwise invent a currency/weight conversion. Preserve the observed price and weight, and let the application calculate R$/kg.
- Keep shipping separate when observable.
- If a coupon is required for the observed price, record it.
- If a source was searched but no reliable direct offer was found, record not_found. If only partial/ambiguous results were found, use partial and explain why.
- Do not fabricate availability, seller, SKU, price or URL.

RESEARCH METHOD
For each catalog item, search each configured source. Use multiple targeted searches when necessary, including manufacturer + line + weight + color and site/domain-specific queries. Open promising results when needed to verify the product page and current price. Continue until the marginal value of additional searching is low. Favor official manufacturer stores for manufacturer sources and direct marketplace product pages for marketplaces.

OUTPUT
Return JSON only according to the supplied schema. Include collection entries for the source/item combinations actually researched, including negative results. Include all valid offers found. The result will be merged into the daily immutable snapshot.

CATALOG
{catalog_json}
"""


def collect_batch(provider, catalog, sources, today):
    prompt = build_prompt(catalog, sources, today) + "\n\nJSON CONTRACT: Return one JSON object with exactly two top-level keys: offers (array) and collection (array). Each offer must contain the exact fields required by the FilamentDB schema; each collection item must contain filament_key, color, store, status, offers_found, and notes. Return JSON only."
    return provider.collect(prompt)


def validate_and_merge(parts, catalog, sources):
    valid_keys = {r["filament_key"]: r for r in catalog}
    source_map = {s["name"]: s for s in sources}
    offers, collection, seen = [], [], set()
    for part in parts:
        for x in part.get("offers", []):
            key = x.get("filament_key")
            if key not in valid_keys:
                continue
            if x.get("store") not in source_map:
                continue
            if not str(x.get("url", "")).startswith(("http://", "https://")):
                continue
            if float(x.get("price", 0)) <= 0 or float(x.get("unit_weight_g", 0)) <= 0:
                continue
            if int(x.get("quantity", 0)) <= 0:
                continue
            expected_total = float(x["price"]) * int(x["quantity"]) if x["price_basis"] == "unit" else float(x["price"])
            if abs(float(x["total_price"]) - expected_total) > 0.02:
                x["total_price"] = round(expected_total, 2)
            r = valid_keys[key]
            if x.get("manufacturer", "").strip().casefold() != r["manufacturer_name"].strip().casefold():
                continue
            dedupe = (key, x.get("store"), x.get("url"), x.get("quantity"), float(x.get("unit_weight_g")), x.get("price_basis"))
            if dedupe in seen:
                continue
            seen.add(dedupe)
            offers.append(x)
        collection.extend(part.get("collection", []))
    return offers, collection


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="YYYY-MM-DD, defaults to Sao Paulo today")
    args = parser.parse_args()
    now = datetime.now(TZ)
    today = args.date or now.date().isoformat()
    sources = load_sources()
    catalog = load_catalog()
    if not catalog:
        raise RuntimeError("Nenhum perfil PLA/PETG ativo foi encontrado no catÃ¡logo")
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    path = SNAPSHOT_DIR / f"{today}.json"
    if path.exists() and not os.getenv("ALLOW_SNAPSHOT_REPLACE"):
        raise RuntimeError(f"Snapshot jÃ¡ existe: {path}. Use ALLOW_SNAPSHOT_REPLACE=1 para correÃ§Ã£o deliberada.")
    parts = []
    provider_list = [p for p in providers() if p.available()]
    if not provider_list:
        raise RuntimeError("Nenhum provedor de IA com chave/configuração disponível")
    batches = list(chunked(catalog, BATCH_SIZE))
    print(f"[INFO] Catálogo monitorado: {len(catalog)} perfis; lotes: {len(batches)}; provedores: {', '.join(p.name for p in provider_list)}")
    for idx, batch in enumerate(batches, 1):
        print(f"[INFO] Pesquisando lote {idx}/{len(batches)}: {batch[0]['filament_key']} ... {batch[-1]['filament_key']}", flush=True)
        last_error = None
        start_idx = (idx - 1) % len(provider_list)
        ordered = provider_list[start_idx:] + provider_list[:start_idx]
        for provider in ordered:
            try:
                print(f"[INFO]   -> provedor {provider.name}", flush=True)
                parts.append(collect_batch(provider, batch, sources, today))
                break
            except ProviderError as exc:
                last_error = exc
                print(f"[WARN]   -> {exc}", flush=True)
        else:
            raise RuntimeError(f"Todos os provedores falharam no lote {idx}: {last_error}")
    offers, collection = validate_and_merge(parts, catalog, sources)
    payload = {
        "schema_version": 2,
        "snapshot_date": today,
        "collected_at": now.isoformat(),
        "collector": "FilamentDB AI Price Agent",
        "collector_version": "1.0",
        "scope": {"tracked_profiles": len(catalog), "sources": [s["name"] for s in sources]},
        "collection": collection,
        "offers": offers,
        "notes": "Coleta automatizada por pesquisa web com IA; somente ofertas diretamente verificÃ¡veis foram preservadas.",
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[INFO] Snapshot escrito: {path}")
    print(f"[INFO] Ofertas vÃ¡lidas: {len(offers)}; resultados de coleta: {len(collection)}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        raise
