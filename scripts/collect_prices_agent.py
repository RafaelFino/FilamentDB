#!/usr/bin/env python3
"""API-driven agentic price collector for FilamentDB."""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
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
CEREBRAS_MODEL = os.getenv("CEREBRAS_MODEL", "gpt-oss-120b")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")
ZAI_MODEL = os.getenv("ZAI_MODEL", "glm-4.6")
MAX_TURNS = int(os.getenv("PRICE_AGENT_MAX_TURNS", "30"))
# Bounded retry for transient LLM errors (429 rate limit, 5xx). After these run
# out, the provider raises ProviderError and the caller falls back to the next LLM.
LLM_MAX_RETRIES = int(os.getenv("PRICE_AGENT_LLM_RETRIES", "3"))
LLM_BACKOFF_BASE = float(os.getenv("PRICE_AGENT_LLM_BACKOFF", "5"))

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


# Web-search engines to use, in order. ddgs (>=9) is a METAsearch lib whose
# "auto" backend also tries wikipedia/grokipedia — which fail with DNS errors on
# CI runners and never return shopping results. We pin real web engines and try
# them in order, skipping any that error out. Override via PRICE_AGENT_SEARCH_BACKENDS.
SEARCH_BACKENDS = [
    b.strip() for b in os.getenv(
        "PRICE_AGENT_SEARCH_BACKENDS", "duckduckgo,bing,brave,google,mojeek,startpage"
    ).split(",") if b.strip()
]
SEARCH_REGION = os.getenv("PRICE_AGENT_SEARCH_REGION", "us-en")


# Keep web-search results compact: they accumulate in the message history every
# turn and blow the per-minute token budget on free tiers (e.g. Groq TPM=8000).
SEARCH_MAX_RESULTS = int(os.getenv("PRICE_AGENT_SEARCH_MAX_RESULTS", "5"))
SEARCH_SNIPPET_CHARS = int(os.getenv("PRICE_AGENT_SEARCH_SNIPPET_CHARS", "300"))


def search_web(query: str, max_results: int = None):
    """Search the web across real engines; never turn a blocked/empty backend
    into an agent failure (returns [] so the model can try another query).

    Results are trimmed (count + snippet length) to keep the running message
    history within tight per-minute token limits of free provider tiers."""
    from ddgs import DDGS

    cap = max_results if max_results is not None else SEARCH_MAX_RESULTS
    limit = max(1, min(int(cap or SEARCH_MAX_RESULTS), SEARCH_MAX_RESULTS))
    errors = []
    for backend in SEARCH_BACKENDS:
        try:
            results = DDGS(timeout=60).text(
                query, region=SEARCH_REGION, safesearch="off",
                max_results=limit, backend=backend,
            )
            if results:
                return [{
                    "title": (r.get("title") or "")[:160],
                    "url": r.get("href", ""),
                    "snippet": (r.get("body") or "")[:SEARCH_SNIPPET_CHARS],
                } for r in results[:limit]]
        except Exception as exc:
            errors.append(f"{backend}: {exc}")
    if errors:
        print(f"[WARN] busca web sem resultados (últimos erros: {'; '.join(errors[-2:])})", flush=True)
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

    def _complete(self, messages, tools):
        """Call the LLM with bounded retry on transient errors (429/5xx).

        Any error that survives the retries is converted into a ProviderError so
        the caller's provider loop can fall back to the next LLM instead of the
        whole run crashing on a raw openai exception (e.g. RateLimitError).
        """
        last_exc = None
        for attempt in range(LLM_MAX_RETRIES):
            try:
                return self.client.chat.completions.create(
                    model=self.model, messages=messages, tools=tools, tool_choice="auto"
                )
            except Exception as exc:  # openai.RateLimitError, APIStatusError, timeouts, etc.
                last_exc = exc
                status = getattr(exc, "status_code", None)
                msg = str(exc).lower()
                # Some 400s are the MODEL's fault, not config: e.g. Groq validates
                # tool-call args server-side and returns 400 'tool_use_failed' when
                # the model emits a malformed call. That is retryable — the model
                # may get it right next turn. Real config 400s (and 401/402/403/
                # 404/422) are permanent and should fail fast to the next provider.
                model_glitch = "tool_use_failed" in msg or "did not match schema" in msg or "failed_generation" in msg
                # 413 with a per-minute token limit (Groq TPM) recovers after the
                # window resets — treat as transient with a long-ish wait.
                token_rate = status == 413 or ("tokens per minute" in msg) or ("tpm" in msg)
                permanent = (status in (401, 402, 403, 404, 422)) or (status == 400 and not model_glitch)
                transient = (not permanent) and (
                    model_glitch or token_rate or status in (429, 500, 502, 503, 504) or status is None
                )
                if not transient or attempt == LLM_MAX_RETRIES - 1:
                    break
                if model_glitch:
                    wait = 0
                elif token_rate:
                    wait = max(LLM_BACKOFF_BASE, 20) * (attempt + 1)  # let the per-minute window reset
                else:
                    wait = LLM_BACKOFF_BASE * (2 ** attempt)
                reason = ("tool-call malformado (modelo)" if model_glitch
                          else "limite de tokens/min" if token_rate
                          else f"erro transitório ({status or type(exc).__name__})")
                print(f"[WARN] {self.name}: {reason}; retry {attempt + 1}/{LLM_MAX_RETRIES - 1}"
                      + (f" em {wait:.0f}s" if wait else ""), flush=True)
                if wait:
                    time.sleep(wait)
        raise ProviderError(f"{self.name}: chamada ao LLM falhou: {last_exc}") from last_exc

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
            response = self._complete(messages, make_tools(item))
            msg = response.choices[0].message
            messages.append(msg)
            calls = msg.tool_calls or []
            if not calls:
                print(f"[INFO] {self.name} terminou sem novas tool calls após {turn + 1} ciclo(s).", flush=True)
                return offers
            for call in calls:
                name = call.function.name
                try:
                    args = json.loads(call.function.arguments or "{}")
                    if not isinstance(args, dict):
                        args = {}
                except (ValueError, TypeError):
                    args = {}
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
                    # Unknown tool (model hallucinated one): feed the error back so it
                    # can correct on the next turn, instead of aborting the provider.
                    result = {"ok": False, "error": f"ferramenta '{name}' não existe; use apenas search_web e submit_offer"}
                    print(f"[WARN] {self.name}: modelo chamou ferramenta inexistente '{name}'; devolvendo erro para correção.", flush=True)
                messages.append({"role": "tool", "tool_call_id": call.id, "name": name, "content": json.dumps(result, ensure_ascii=False)})
        # Hit the turn ceiling. Keep whatever was already collected rather than
        # discarding it — a chatty model that found real offers still produced value.
        if offers:
            print(f"[INFO] {self.name} atingiu {MAX_TURNS} ciclos; retornando {len(offers)} oferta(s) já coletada(s).", flush=True)
            return offers
        raise ProviderError(f"{self.name}: excedeu {MAX_TURNS} ciclos sem coletar ofertas")


def providers():
    # Provider registry: name -> (env key, base_url, model). All are OpenAI-compatible.
    # The actual order/selection is controlled by PRICE_AGENT_PROVIDERS in main().
    registry = {
        "mistral":    ("MISTRAL_API_KEY",    "https://api.mistral.ai/v1", MISTRAL_MODEL),
        "cerebras":   ("CEREBRAS_API_KEY",   "https://api.cerebras.ai/v1", CEREBRAS_MODEL),
        "groq":       ("GROQ_API_KEY",       "https://api.groq.com/openai/v1", GROQ_MODEL),
        "openai":     ("OPENAI_API_KEY",     "https://api.openai.com/v1", OPENAI_MODEL),
        "openrouter": ("OPENROUTER_API_KEY", "https://openrouter.ai/api/v1", OPENROUTER_MODEL),
        "z":          ("Z_API_KEY",          "https://api.z.ai/api/paas/v4", ZAI_MODEL),
        "gemini":     ("GEMINI_API_KEY",     "https://generativelanguage.googleapis.com/v1beta/openai/", GEMINI_MODEL),
    }
    result = []
    for name, (env_key, base_url, model) in registry.items():
        api_key = os.getenv(env_key)
        if not api_key:
            continue
        provider = AgentProvider(OpenAI(base_url=base_url, api_key=api_key, timeout=180), model)
        provider.name = name
        result.append(provider)
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
    order = [x.strip().casefold() for x in os.getenv("PRICE_AGENT_PROVIDERS", "cerebras,groq,mistral,openai,openrouter,z,gemini").split(",") if x.strip()]
    available = {p.name: p for p in providers()}
    selected = [available[x] for x in order if x in available]
    if not selected:
        raise RuntimeError("Nenhum agente configurado com chave disponível")
    all_offers = []
    collection = []
    # Providers that hit a hard rate limit are parked so we don't waste retries
    # on them for every remaining filament — the next collection/run resets this.
    exhausted = set()
    failures = 0
    print(f"[INFO] Catálogo monitorado: {len(catalog)} perfis; agentes: {', '.join(p.name for p in selected)}", flush=True)
    for index, item in enumerate(catalog, 1):
        print(f"[INFO] Pesquisando {index}/{len(catalog)}: {item['filament_key']}", flush=True)
        last_error = None
        used = None
        for provider in selected:
            if provider.name in exhausted:
                continue
            try:
                print(f"[INFO]   -> agente {provider.name}", flush=True)
                offers = provider.run(item, today)
                all_offers.extend(offers)
                used = provider.name
                collection.append({"filament_key": item["filament_key"], "color": item.get("color"), "store": "agentic", "status": "found" if offers else "not_found", "offers_found": len(offers), "notes": f"Pesquisa agentic via {provider.name}."})
                last_error = None
                break
            except ProviderError as exc:
                last_error = exc
                print(f"[WARN]   -> {exc}", flush=True)
                msg = str(exc).lower()
                # Park a provider for the rest of the run when the failure will
                # clearly repeat for every filament: rate limit (429), quota/
                # payment (402), auth (401/403) or missing model (404).
                if any(s in msg for s in ("rate limit", "429", "402", "payment", "quota",
                                          "401", "403", "404", "model_not_found",
                                          "insufficient", "does not exist")):
                    exhausted.add(provider.name)
                    print(f"[WARN]   -> {provider.name} marcado como indisponível nesta coleta (não será tentado de novo).", flush=True)
        if used is None:
            # Every provider failed for this filament. Do NOT abort the whole run:
            # record the failure, keep what we already collected, and move on.
            failures += 1
            collection.append({"filament_key": item["filament_key"], "color": item.get("color"), "store": "agentic", "status": "error", "offers_found": 0, "notes": f"Todos os agentes falharam: {last_error}"})
            print(f"[WARN]   -> nenhum agente disponível para {item['filament_key']}: {last_error}", flush=True)
            if len(exhausted) >= len(selected):
                print("[WARN] Todos os agentes esgotados; encerrando a coleta e salvando o que foi obtido.", flush=True)
                break
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    merged_offers = merge_offers(existing_offers, all_offers)
    payload = {"schema_version": 2, "snapshot_date": today, "collected_at": datetime.now(TZ).isoformat(), "collector": "FilamentDB API-driven AI Price Agent", "collector_version": "2.0", "scope": {"tracked_profiles": len(catalog), "sources": "API /v1/agent/instructions"}, "collection": collection, "offers": merged_offers, "notes": "Snapshot é a fonte de verdade: ofertas coletadas pelos agentes, validadas offline e publicadas na API por publish_price_snapshot.py."}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    added = len(merged_offers) - len(existing_offers)
    print(f"[OK] Snapshot escrito: {path}; ofertas={len(merged_offers)} (novas nesta coleta: {len(all_offers)}, líquidas após merge: {added})", flush=True)
    if failures:
        print(f"[INFO] {failures} filamento(s) sem coleta por falha de agente (registrados como 'error' no snapshot).", flush=True)
    if exhausted:
        print(f"[INFO] Agentes esgotados por rate limit nesta coleta: {', '.join(sorted(exhausted))}.", flush=True)

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        raise
