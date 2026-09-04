#!/usr/bin/env python3
"""
offer_rules.py — Regras de validade de oferta compartilhadas pelo pipeline.

Uma oferta só serve como preço de referência do FilamentDB quando é uma
**oferta válida**: o produto está disponível para venda E é entregável no
endereço-alvo (São Paulo/SP). Ofertas indisponíveis ou não entregáveis podem
ser registradas para histórico/auditoria, mas não devem virar o preço de
referência de mercado.

Ofertas de sites internacionais têm um preço incompleto: o valor mostrado não
inclui frete internacional nem impostos de importação, então é marcado como
`price_pending_shipping_taxes` e não deve ser comparado de igual para igual com
uma oferta nacional já com tudo embutido.

Este módulo é a fonte única dessas heurísticas para coletor, API e validador.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

# Cidade/estado alvo de entrega. Regra de negócio atual do projeto.
TARGET_CITY = "São Paulo"
TARGET_STATE = "SP"

# Domínios/mercados nacionais conhecidos (entregam no Brasil por padrão).
# Marketplaces globais em .com (sem .br) são tratados como internacionais.
_BR_TLDS = (".com.br", ".br")
_KNOWN_BR_DOMAINS = {
    "3dlab.com.br", "voolt3d.com.br", "filamentos3dbrasil.com.br",
    "crealitybrasil.com.br", "loja3dhouse.com.br", "mercadolivre.com.br",
    "shopee.com.br", "amazon.com.br", "magazineluiza.com.br", "americanas.com.br",
}
# Domínios internacionais comuns nesse mercado (preço tende a vir em moeda
# estrangeira e sem frete/impostos para o Brasil).
_INTL_DOMAINS = {
    "amazon.com", "aliexpress.com", "ebay.com", "sunlu.com", "elegoo.com",
    "polymaker.com", "matterhackers.com", "amazon.co.uk", "amazon.de",
}
# Moeda inferida por TLD/domínio quando a oferta não declara moeda confiável.
_DOMAIN_CURRENCY = {
    "amazon.com": "USD", "aliexpress.com": "USD", "ebay.com": "USD",
    "sunlu.com": "USD", "elegoo.com": "USD", "polymaker.com": "USD",
    "matterhackers.com": "USD", "amazon.co.uk": "GBP", "amazon.de": "EUR",
}

# Padrões de URL que NÃO são página de produto: busca, listagem de categoria,
# vitrine de loja. Uma oferta precisa de uma URL de produto verificável.
_LISTING_PATTERNS = (
    re.compile(r"/search\b", re.I),
    re.compile(r"[?&](q|query|busca|search|k)=", re.I),
    re.compile(r"recos_listing=true", re.I),
    re.compile(r"/(categoria|categories|category|colecoes|collections|marca|brands?)/", re.I),
    re.compile(r"/loja/", re.I),
)


def domain_of(url: str) -> str:
    try:
        net = urlparse(url).netloc.lower()
    except Exception:
        return ""
    return net[4:] if net.startswith("www.") else net


def is_brazilian_domain(url: str) -> bool:
    d = domain_of(url)
    if not d:
        return False
    if d in _KNOWN_BR_DOMAINS:
        return True
    if d in _INTL_DOMAINS:
        return False
    return d.endswith(_BR_TLDS)


def is_international_domain(url: str) -> bool:
    d = domain_of(url)
    if not d:
        return False
    if d in _INTL_DOMAINS:
        return True
    # .com puro (sem .br) e não reconhecido como nacional → tratar como internacional.
    return not is_brazilian_domain(url)


def currency_for_domain(url: str) -> str | None:
    """Moeda inferida pelo domínio, quando a oferta não trouxe moeda confiável."""
    return _DOMAIN_CURRENCY.get(domain_of(url))


def is_listing_url(url: str) -> bool:
    """True se a URL parece ser busca/listagem/vitrine em vez de página de produto."""
    if not url:
        return True
    return any(p.search(url) for p in _LISTING_PATTERNS)


# Termos que indicam indisponibilidade explícita numa string de disponibilidade.
_UNAVAILABLE_TERMS = (
    "sem estoque", "esgotado", "indisponivel", "indisponível", "out of stock",
    "unavailable", "sold out", "fora de estoque",
)
_AVAILABLE_TERMS = (
    "em estoque", "disponivel", "disponível", "in stock", "available",
    "pronta entrega", "true", "sim",
)


def parse_availability(value) -> bool | None:
    """Interpreta o campo de disponibilidade da oferta.

    Retorna True (disponível), False (indisponível) ou None (desconhecido).
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return bool(value)
    s = str(value).strip().casefold()
    if not s:
        return None
    if any(t in s for t in _UNAVAILABLE_TERMS):
        return False
    if any(t in s for t in _AVAILABLE_TERMS):
        return True
    return None


def is_valid_reference_offer(offer: dict) -> tuple[bool, str]:
    """Uma oferta é válida como PREÇO DE REFERÊNCIA quando:
    - está disponível (available is True), e
    - é entregável em São Paulo (deliverable_to_sao_paulo is True).

    Ofertas internacionais podem ser entregáveis, mas seu preço é incompleto
    (sem frete/impostos), então NÃO são preço de referência — entram apenas como
    contexto. Retorna (é_valida, motivo).
    """
    if offer.get("available") is False:
        return False, "indisponível"
    if offer.get("available") is None:
        return False, "disponibilidade desconhecida"
    if offer.get("deliverable_to_sao_paulo") is False:
        return False, "não entrega em São Paulo"
    if offer.get("international"):
        return False, "internacional (preço sem frete/impostos)"
    if offer.get("price_pending_shipping_taxes"):
        return False, "preço pendente de frete/impostos"
    return True, "ok"


def classify_offer_geography(offer: dict) -> dict:
    """Preenche international / price_pending_shipping_taxes / deliverable_to_sao_paulo
    a partir do domínio da URL e dos campos já presentes. Não sobrescreve valores
    já definidos explicitamente pela oferta (o coletor pode ter observado a página).
    """
    url = offer.get("url", "")
    intl = is_international_domain(url)
    out = dict(offer)
    if "international" not in out:
        out["international"] = bool(intl)
    # Preço internacional é sempre incompleto para o comprador em SP.
    if out.get("international"):
        out["price_pending_shipping_taxes"] = True
        # Sem confirmação explícita, assumimos que um site internacional pode não
        # entregar em SP — deixa como desconhecido (None) em vez de True.
        out.setdefault("deliverable_to_sao_paulo", None)
    else:
        out.setdefault("price_pending_shipping_taxes", False)
        # Loja nacional reconhecida: assume entregável em SP salvo indicação contrária.
        out.setdefault("deliverable_to_sao_paulo", True if is_brazilian_domain(url) else None)
    return out
