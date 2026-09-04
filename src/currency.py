#!/usr/bin/env python3
"""
currency.py — Conversão de moeda para normalizar preços em BRL.

O preço de referência do FilamentDB é sempre em BRL (e, no fim, R$/kg). Ofertas
observadas em USD precisam ser convertidas usando uma cotação coerente. A fonte
oficial é a AwesomeAPI:

    https://economia.awesomeapi.com.br/last/USD-BRL

Resposta (exemplo):

    {"USDBRL": {"code": "USD", "codein": "BRL", "bid": "5.0998",
                "ask": "5.1002", "create_date": "2026-09-03 19:30:06", ...}}

Regras de projeto:

- Usamos o campo `bid` (preço de compra do dólar), que é a cotação de referência
  para converter um preço em USD para BRL.
- A cotação é buscada uma vez por processo e mantida em cache em memória: o job
  de coleta roda uma vez por dia e não precisa martelar a API a cada oferta.
- Se a API falhar, usamos um fallback configurável via `FILAMENTDB_USD_BRL_FALLBACK`
  (config.env / ambiente). Sem fallback e sem rede, a conversão levanta erro em
  vez de gravar um preço em USD disfarçado de BRL.
- Sem dependências externas: usa apenas urllib, coerente com o resto do projeto.
"""
from __future__ import annotations

import json
import urllib.request
import urllib.error

from src import config

AWESOME_API_URL = "https://economia.awesomeapi.com.br/last/USD-BRL"
# Timeout curto: é uma chamada de conveniência num job batch; se demorar, cai no
# fallback em vez de segurar a coleta inteira.
FX_TIMEOUT = 15
# Faixa de sanidade da própria cotação: rejeita respostas absurdas (ex.: 0 ou um
# número deslocado por erro de parsing) que produziriam preços convertidos loucos.
FX_MIN = 1.0
FX_MAX = 20.0


class CurrencyError(RuntimeError):
    """Falha ao obter uma cotação utilizável."""


# Cache em memória por processo: (rate, source).
_cache: tuple[float, str] | None = None


def _parse_rate(raw: str) -> float:
    payload = json.loads(raw)
    quote = payload.get("USDBRL")
    if not isinstance(quote, dict):
        raise CurrencyError("resposta da AwesomeAPI sem bloco USDBRL")
    bid = quote.get("bid")
    if bid is None:
        raise CurrencyError("resposta da AwesomeAPI sem campo bid")
    rate = float(bid)
    if not (FX_MIN <= rate <= FX_MAX):
        raise CurrencyError(f"cotação USD-BRL fora da faixa plausível: {rate}")
    return rate


def _fetch_from_api() -> float:
    req = urllib.request.Request(
        AWESOME_API_URL,
        headers={"Accept": "application/json", "User-Agent": "FilamentDB-PriceAgent/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=FX_TIMEOUT) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
        raise CurrencyError(f"AwesomeAPI indisponível: {exc}") from exc
    return _parse_rate(raw)


def _fallback_rate() -> float | None:
    raw = config.get("FILAMENTDB_USD_BRL_FALLBACK", "")
    if not raw:
        return None
    try:
        rate = float(str(raw).strip().replace(",", "."))
    except (TypeError, ValueError):
        return None
    return rate if FX_MIN <= rate <= FX_MAX else None


def get_usd_brl(*, force: bool = False) -> tuple[float, str]:
    """Retorna (cotação, fonte). Cacheia por processo. Cai no fallback em erro.

    fonte é 'awesomeapi' quando vem da API e 'fallback' quando vem da env var.
    Levanta CurrencyError se não houver cotação utilizável de nenhuma fonte.
    """
    global _cache
    if _cache is not None and not force:
        return _cache
    try:
        rate = _fetch_from_api()
        _cache = (rate, "awesomeapi")
        return _cache
    except CurrencyError:
        fallback = _fallback_rate()
        if fallback is not None:
            _cache = (fallback, "fallback")
            return _cache
        raise


def is_brl(currency: str | None) -> bool:
    return str(currency or "BRL").strip().upper() in {"BRL", "R$", "REAL", "REAIS", "RS"}


def is_usd(currency: str | None) -> bool:
    return str(currency or "").strip().upper() in {"USD", "US$", "$", "DOLAR", "DÓLAR"}


def is_supported_currency(currency: str | None) -> bool:
    """True se a moeda é uma que sabemos converter (BRL ou USD). Vazio conta como
    BRL. Serve para o import distinguir 'moeda estrangeira legítima' de 'lixo no
    campo currency' (ex.: um ASIN da Amazon gravado por engano pelo agente)."""
    return is_brl(currency) or is_usd(currency)


def to_brl(value, currency: str | None) -> tuple[float | None, dict]:
    """Converte `value` para BRL segundo `currency`.

    Retorna (valor_em_brl, meta). `meta` traz os dados de auditoria da conversão
    (só preenchidos quando houve conversão de fato):
        {"fx_rate": float, "fx_source": str, "original_currency": "USD"}

    - BRL (ou vazio): devolve o próprio valor, meta vazio.
    - USD: multiplica pela cotação USD-BRL.
    - Outras moedas: levanta CurrencyError (não inventamos taxa).
    - value None: devolve (None, {}).
    """
    if value is None:
        return None, {}
    val = float(value)
    if is_brl(currency):
        return val, {}
    if is_usd(currency):
        rate, source = get_usd_brl()
        return round(val * rate, 2), {
            "fx_rate": rate,
            "fx_source": source,
            "original_currency": "USD",
        }
    raise CurrencyError(f"moeda não suportada para conversão: {currency!r}")
