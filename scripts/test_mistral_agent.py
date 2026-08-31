#!/usr/bin/env python3
"""Minimal Mistral tool-calling smoke test for FilamentDB."""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

from openai import OpenAI

API_URL = os.getenv("FILAMENTDB_API_URL", "https://filamentdb-api.learnops.duckdns.org").rstrip("/")
API_SECRET = os.getenv("FILAMENTDB_API_SECRET", "")
MODEL = os.getenv("MISTRAL_MODEL", "mistral-small-latest")


def get_instructions():
    if not API_SECRET:
        raise RuntimeError("FILAMENTDB_API_SECRET is not configured")
    request = urllib.request.Request(
        API_URL + "/v1/agent/instructions",
        method="GET",
        headers={"Accept": "application/json", "X-Proxy-Secret": API_SECRET},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"FilamentDB API HTTP {exc.code}: {body[:500]}") from exc


def main():
    if not os.getenv("MISTRAL_API_KEY"):
        raise RuntimeError("MISTRAL_API_KEY is not configured")

    client = OpenAI(base_url="https://api.mistral.ai/v1", api_key=os.environ["MISTRAL_API_KEY"])
    tools = [{
        "type": "function",
        "function": {
            "name": "get_instructions",
            "strict": True,
            "description": "Obtém as instruções oficiais do agente FilamentDB pela API.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
                "additionalProperties": False,
            },
        },
    }]

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": "You are testing the FilamentDB agent integration. Do not answer from memory. Call get_instructions exactly once."},
            {"role": "user", "content": "Call the FilamentDB instructions tool now."},
        ],
        tools=tools,
        parallel_tool_calls=False,
        max_tokens=300,
    )
    message = response.choices[0].message
    if not message.tool_calls:
        raise RuntimeError(f"Mistral did not issue a tool call. Response: {message.content!r}")

    call = message.tool_calls[0]
    if call.function.name != "get_instructions":
        raise RuntimeError(f"Unexpected tool requested: {call.function.name}")

    instructions = get_instructions()
    print(f"[OK] Mistral model: {MODEL}")
    print("[OK] Mistral issued get_instructions tool call.")
    print(f"[OK] FilamentDB API responded to the tool call: {json.dumps(instructions, ensure_ascii=False)[:1000]}")
    print("[OK] Smoke test passed without invoking web search or publishing any price.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        raise
