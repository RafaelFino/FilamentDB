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


def _tool_definitions():
    return [
        {"type":"function","function":{"name":"search_web","description":"Search the web for current filament offers. Use multiple targeted searches if needed.","parameters":{"type":"object","properties":{"query":{"type":"string"},"max_results":{"type":"integer","minimum":1,"maximum":10}},"required":["query"]}}},
        {"type":"function","function":{"name":"submit_offer","description":"Submit a validated real offer to FilamentDB. Use the exact filament_key from the catalog and provide the source URL and price details.","parameters":{"type":"object","properties":{"filament_key":{"type":"string"},"store":{"type":"string"},"url":{"type":"string"},"title":{"type":"string"},"price":{"type":"number"},"original_price":{"type":["number","null"]},"shipping":{"type":["number","null"]},"total_price":{"type":["number","null"]},"currency":{"type":"string"},"availability":{"type":["string","null"]},"quantity":{"type":["number","null"]},"unit_weight_g":{"type":["number","null"]},"price_basis":{"type":["string","null"]},"seller":{"type":["string","null"]},"external_id":{"type":["string","null"]}},"required":["filament_key","store","url","title","price","currency"]}}}
    ]


class AgentProvider:
    def __init__(self, client, model):
        self.client = client
        self.model = model
        self.name = "agent"

    def run(self, item, today):
        instructions = api_call("GET", "/v1/agent/instructions?filament_key=" + urllib.parse.quote(item["filament_key"]))
        system = instructions.get("system_prompt", "")
        user = instructions.get("user_prompt", "")
        messages = [{"role":"system","content":system},{"role":"user","content":user}]
        offers=[]
        for turn in range(MAX_TURNS):
            response=self.client.chat.completions.create(model=self.model,messages=messages,tools=_tool_definitions(),tool_choice="auto")
            msg=response.choices[0].message
            messages.append(msg)
            calls=msg.tool_calls or []
            if not calls:
                print(f"[INFO] {self.name} terminou sem novas tool calls após {turn+1} ciclo(s).",flush=True)
                return offers
            for call in calls:
                name=call.function.name
                args=json.loads(call.function.arguments or "{}")
                if name=="search_web":
                    result=search_web(args.get("query", ""), args.get("max_results",8))
                elif name=="submit_offer":
                    args["filament_key"]=item["filament_key"]
                    result=api_call("POST","/v1/agent/offers",args)
                    offers.append(result.get("offer",result))
                    print(f"[OK] {self.name} publicou oferta: {args.get('filament_key')} | {args.get('store')} | R$ {args.get('total_price')}",flush=True)
                else:
                    raise ProviderError(f"{self.name}: ferramenta desconhecida: {name}")
                messages.append({"role":"tool","tool_call_id":call.id,"name":name,"content":json.dumps(result,ensure_ascii=False)})
        raise ProviderError(f"{self.name}: excedeu {MAX_TURNS} ciclos de ferramentas")


def providers():
    result=[]
    if os.getenv("MISTRAL_API_KEY"):
        result.append(AgentProvider(OpenAI(base_url="https://api.mistral.ai/v1",api_key=os.environ["MISTRAL_API_KEY"],timeout=180),MISTRAL_MODEL)); result[-1].name="mistral"
    if os.getenv("GEMINI_API_KEY"):
        result.append(AgentProvider(OpenAI(base_url="https://generativelanguage.googleapis.com/v1beta/openai/",api_key=os.environ["GEMINI_API_KEY"],timeout=180),GEMINI_MODEL)); result[-1].name="gemini"
    return result


def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--date"); args=parser.parse_args()
    today=args.date or datetime.now(TZ).date().isoformat(); catalog=load_catalog()
    limit=int(os.getenv("PRICE_AGENT_MAX_PROFILES","0") or "0")
    if limit>0: catalog=catalog[:limit]
    if not catalog: raise RuntimeError("Nenhum perfil PLA/PETG ativo foi encontrado")
    path=SNAPSHOT_DIR/f"{today}.json"
    if path.exists() and not os.getenv("ALLOW_SNAPSHOT_REPLACE"): raise RuntimeError(f"Snapshot já existe: {path}")
    order=[x.strip().casefold() for x in os.getenv("PRICE_AGENT_PROVIDERS","mistral,gemini").split(",") if x.strip()]
    available={p.name:p for p in providers()}; selected=[available[x] for x in order if x in available]
    if not selected: raise RuntimeError("Nenhum agente configurado com chave disponível")
    all_offers=[]; collection=[]
    print(f"[INFO] Catálogo monitorado: {len(catalog)} perfis; agentes: {', '.join(p.name for p in selected)}",flush=True)
    for index,item in enumerate(catalog,1):
        print(f"[INFO] Pesquisando {index}/{len(catalog)}: {item['filament_key']}",flush=True); last_error=None
        for provider in selected:
            try:
                print(f"[INFO]   -> agente {provider.name}",flush=True); offers=provider.run(item,today); all_offers.extend(offers)
                collection.append({"filament_key":item["filament_key"],"color":item.get("color"),"store":"agentic","status":"found" if offers else "not_found","offers_found":len(offers),"notes":f"Pesquisa agentic via {provider.name}; ofertas gravadas diretamente na API."}); last_error=None; break
            except ProviderError as exc:
                last_error=exc; print(f"[WARN]   -> {exc}",flush=True)
        else: raise RuntimeError(f"Todos os agentes falharam para {item['filament_key']}: {last_error}")
    SNAPSHOT_DIR.mkdir(parents=True,exist_ok=True)
    payload={"schema_version":2,"snapshot_date":today,"collected_at":datetime.now(TZ).isoformat(),"collector":"FilamentDB API-driven AI Price Agent","collector_version":"2.0","scope":{"tracked_profiles":len(catalog),"sources":"API /v1/agent/instructions"},"collection":collection,"offers":all_offers,"notes":"Ofertas publicadas pelo agente diretamente na API; o snapshot é apenas a auditoria versionada da coleta."}
    path.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8"); print(f"[OK] Snapshot escrito: {path}; ofertas={len(all_offers)}",flush=True)

if __name__ == "__main__":
    try: main()
    except Exception as exc: print(f"[ERROR] {exc}",file=sys.stderr); raise
