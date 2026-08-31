#!/usr/bin/env python3
"""API-driven agentic price collector for FilamentDB."""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from openai import OpenAI

ROOT = Path(__file__).resolve().parents[1]
CATALOG_DB = ROOT / "filament.db"
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
            errors.append(type(exc).__name__)

    # Fallback to Bing's public HTML endpoint when DDGS has no usable backend.
    try:
        from urllib.parse import quote_plus
        from urllib.request import Request, urlopen
        from html import unescape
        import re
        req = Request(
            "https://www.bing.com/search?q=" + quote_plus(query) + "&count=" + str(limit),
            headers={"User-Agent": "Mozilla/5.0"},
        )
        html = urlopen(req, timeout=60).read().decode("utf-8", "ignore")
        found = []
        for block in re.findall(r'<li class="b_algo".*?</li>', html, flags=re.I | re.S):
            m = re.search(r'<h2[^>]*>\s*<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', block, flags=re.I | re.S)
            if not m:
                continue
            url, title = m.groups()
            snippet_m = re.search(r'<p[^>]*>(.*?)</p>', block, flags=re.I | re.S)
            clean = lambda s: re.sub(r"<[^>]+>", "", unescape(s or "")).strip()
            found.append({"title": clean(title), "url": unescape(url), "snippet": clean(snippet_m.group(1) if snippet_m else "")})
            if len(found) >= limit:
                break
        if found:
            return found
    except Exception as exc:
        errors.append(type(exc).__name__)

    # A failed search is useful information for the agent, not a fatal collector error.
    return {
        "ok": False,
        "query": query,
        "results": [],
        "error": "No web results were available for this query.",
        "backend_errors": errors,
        "hint": "Try a different query, a site-specific query, or continue with another configured source.",
    }


def open_url(url: str):
    from ddgs import DDGS
    raw = DDGS(timeout=60).extract(url, fmt="text_rich")
    if isinstance(raw, str):
        text = raw
    elif isinstance(raw, dict):
        text = raw.get("text") or raw.get("content") or raw.get("body") or json.dumps(raw, ensure_ascii=False)
    elif isinstance(raw, list):
        text = "\n".join(str(x) for x in raw)
    else:
        text = str(raw or "")
    return {"url": url, "content": text[:16000]}


def tool_definitions():
    nullable_number = {"type": ["number", "null"]}
    nullable_int = {"type": ["integer", "null"]}
    nullable_string = {"type": ["string", "null"]}
    offer_props = {
        "filament_key": {"type":"string"}, "material": {"type":"string"}, "manufacturer": {"type":"string"},
        "line": {"type":"string"}, "store": {"type":"string"}, "domain": {"type":"string"},
        "marketplace": {"type":"boolean"}, "url": {"type":"string"}, "title": {"type":"string"},
        "price": {"type":"number"}, "original_price": nullable_number, "shipping": nullable_number,
        "currency": {"type":"string"}, "available": {"type": ["boolean", "null"]}, "coupon": nullable_string,
        "color_name": nullable_string, "seller": nullable_string, "quantity": {"type":"integer","minimum":1},
        "unit_weight_g": {"type":"number","minimum":1}, "price_basis": {"type":"string","enum":["unit","total"]},
        "total_price": {"type":"number","minimum":0.01}, "external_id": nullable_string,
        "source": {"type":"string"}, "notes": nullable_string,
    }
    required = list(offer_props)
    def fn(name, description, properties, required_fields):
        return {"type":"function","function":{"name":name,"strict":True,"description":description,
                "parameters":{"type":"object","properties":properties,"required":required_fields,"additionalProperties":False}}}
    return [
        fn("get_instructions", "Obtém da API as regras oficiais e todas as fontes que este agente deve pesquisar.", {}, []),
        fn("get_catalog", "Obtém da API o item de catálogo atribuído ao agente. Nunca invente filament_key.", {}, []),
        fn("search_web", "Pesquisa ofertas atuais na web. Faça buscas específicas por fabricante, linha, peso, cor e fonte.", {"query":{"type":"string"},"max_results":{"type":"integer","minimum":1,"maximum":10}}, ["query","max_results"]),
        fn("open_url", "Abre uma página direta de produto/oferta para verificar preço, identidade, peso e quantidade.", {"url":{"type":"string"}}, ["url"]),
        fn("submit_offer", "Publica uma oferta diretamente na API FilamentDB. Só use depois de verificar a página direta; nunca invente dados.", offer_props, required),
    ]


def assistant_message(msg):
    calls = []
    for call in (getattr(msg, "tool_calls", None) or []):
        entry = {"id": call.id, "type": "function", "function": {"name": call.function.name, "arguments": call.function.arguments or "{}"}}
        extra_content = getattr(call, "extra_content", None)
        if extra_content:
            entry["extra_content"] = extra_content
        calls.append(entry)
    return {"role":"assistant", "content": msg.content if isinstance(msg.content, str) else None, "tool_calls": calls}


class AgentProvider:
    name = "agent"
    def __init__(self, client, model):
        self.client, self.model = client, model
    def available(self):
        return self.client is not None
    def run(self, item, today):
        submitted = []
        instructions_cache = None
        catalog_cache = None
        nudges = 0
        tools = tool_definitions()
        system = ("You are the FilamentDB price acquisition agent. Use tools, not prose. "
                  "First call get_instructions and get_catalog. Then research EVERY configured source for the assigned item. "
                  "Use search_web and open_url to verify current direct product pages. "
                  "Publish EVERY directly verifiable offer with submit_offer. Never invent data. "
                  "Do not return a JSON report: submit_offer is the authoritative write path. "
                  f"Assigned catalog item: {json.dumps(item, ensure_ascii=False)}. Today: {today} America/Sao_Paulo.")
        messages = [{"role":"system","content":system}, {"role":"user","content":"Research the assigned FilamentDB item now. Keep the prompt small; obtain rules and catalog data through the tools."}]
        for turn in range(MAX_TURNS):
            try:
                response = self.client.chat.completions.create(model=self.model, messages=messages, tools=tools,
                                                               parallel_tool_calls=False, max_tokens=5000)
            except Exception as exc:
                raise ProviderError(f"{self.name}: {exc}") from exc
            msg = response.choices[0].message
            calls = getattr(msg, "tool_calls", None) or []
            if not calls:
                print(f"[INFO] {self.name} terminou sem novas tool calls após {turn+1} ciclo(s).", flush=True)
                return submitted
            messages.append(assistant_message(msg))
            for call in calls:
                name = call.function.name
                try:
                    args = json.loads(call.function.arguments or "{}")
                except json.JSONDecodeError as exc:
                    raise ProviderError(f"{self.name}: argumentos inválidos para {name}: {exc}") from exc
                if name == "get_instructions":
                    result = instructions_cache if instructions_cache is not None else api_call("GET", "/v1/agent/instructions")
                    instructions_cache = result
                elif name == "get_catalog":
                    if catalog_cache is None:
                        full = api_call("GET", "/v1/catalog/filaments")
                        if isinstance(full, dict) and isinstance(full.get("filaments"), list):
                            rows = full["filaments"]
                        elif isinstance(full, dict) and isinstance(full.get("items"), list):
                            rows = full["items"]
                        elif isinstance(full, list):
                            rows = full
                        else:
                            rows = full.get("catalog", []) if isinstance(full, dict) else []
                        catalog_cache = [r for r in rows if r.get("filament_key") == item["filament_key"]]
                    result = {"filaments": catalog_cache}
                elif name == "search_web":
                    result = search_web(args["query"], args.get("max_results", 8))
                elif name == "open_url":
                    result = open_url(args["url"])
                elif name == "submit_offer":
                    if "available" in args and args["available"] is not None and not isinstance(args["available"], bool):
                        raw_available = args["available"]
                        if isinstance(raw_available, (int, float)) and raw_available in (0, 1):
                            args["available"] = bool(raw_available)
                        else:
                            normalized = str(raw_available).strip().lower()
                            if normalized in ("true", "yes", "sim", "available", "in_stock", "instock"):
                                args["available"] = True
                            elif normalized in ("false", "no", "não", "nao", "unavailable", "out_of_stock", "outofstock"):
                                args["available"] = False
                            else:
                                args["available"] = None
                    result = api_call("POST", "/v1/agent/offers", args)
                    status = result.get("status") if isinstance(result, dict) else None
                    if status not in ("accepted", "duplicate") and result.get("ok") is not True:
                        raise ProviderError(f"{self.name}: API rejeitou oferta: {result}")
                    submitted.append(args)
                    print(f"[OK] {self.name} publicou oferta: {args.get('filament_key')} | {args.get('store')} | R$ {args.get('total_price')}", flush=True)
                else:
                    raise ProviderError(f"{self.name}: ferramenta desconhecida: {name}")
                messages.append({"role":"tool","tool_call_id":call.id,"name":name,"content":json.dumps(result, ensure_ascii=False)})
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
    if path.exists() and not os.getenv("ALLOW_SNAPSHOT_REPLACE"):
        raise RuntimeError(f"Snapshot já existe: {path}")
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
    payload = {"schema_version":2,"snapshot_date":today,"collected_at":datetime.now(TZ).isoformat(),
               "collector":"FilamentDB API-driven AI Price Agent","collector_version":"2.0",
               "scope":{"tracked_profiles":len(catalog),"sources":"API /v1/agent/instructions"},
               "collection":collection,"offers":all_offers,
               "notes":"Ofertas publicadas pelo agente diretamente na API; o snapshot é apenas a auditoria versionada da coleta."}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[OK] Snapshot escrito: {path}; ofertas={len(all_offers)}", flush=True)

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        raise
