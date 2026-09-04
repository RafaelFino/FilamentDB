#!/usr/bin/env python3
"""Validate a FilamentDB daily price snapshot before it can be committed."""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import config  # noqa: E402
from src import offer_rules  # noqa: E402

config.load()
# Catalog DB lives in the data dir (resolved by config), the same file build.py writes.
# There is intentionally no filament.db at the repo root.
DB = Path(config.database_path("filament.db"))
DATA = ROOT / "data" / "price-data"

# Piso absoluto de preço de referência: nenhuma oferta válida de filamento no
# mercado brasileiro fica abaixo de R$50/kg. Qualquer valor abaixo disso é erro
# de coleta (basis/peso/moeda) ou preço inventado.
_PERKG_FLOOR = 50.0

# Faixas plausíveis de preço de referência em R$/kg por material no mercado
# brasileiro (base 2026), calculadas sobre o peso total da oferta. São limites
# de sanidade, não de mercado: propositalmente largos para não barrar promoções
# ou atacado reais, mas fechados o bastante para pegar erro de basis/peso/moeda
# ou preço inventado (ex.: preço unitário de lote dividido pelo peso do lote).
_PERKG_RANGE = {
    "PLA": (_PERKG_FLOOR, 400.0),
    "PETG": (_PERKG_FLOOR, 450.0),
    "ABS": (_PERKG_FLOOR, 450.0),
    "ASA": (_PERKG_FLOOR, 500.0),
    "TPU": (60.0, 700.0),
    "PLA-CF": (120.0, 900.0),
    "PETG-CF": (120.0, 900.0),
}
# Faixa genérica para materiais fora da tabela: larga o suficiente para não
# bloquear, mas ainda pega valores absurdos (abaixo do piso ou milhares).
_PERKG_DEFAULT = (_PERKG_FLOOR, 1500.0)


def _perkg_range(material):
    lo, hi = _PERKG_RANGE.get(str(material or "").upper().strip(), _PERKG_DEFAULT)
    # Garante o piso global mesmo para materiais com mínimo mais alto na tabela.
    return max(lo, _PERKG_FLOOR), hi


def main(path: Path):
    payload = json.loads(path.read_text(encoding="utf-8"))
    for key in ("schema_version", "snapshot_date", "collected_at", "collector", "offers", "collection"):
        if key not in payload:
            raise ValueError(f"Campo obrigatório ausente: {key}")
    conn = sqlite3.connect(DB)
    valid = {r[0]: r[1:] for r in conn.execute("""
        SELECT fp.filament_key, m.name, mf.name
        FROM filament_profiles fp
        JOIN materials m ON m.id=fp.material_id
        JOIN manufacturers mf ON mf.id=fp.manufacturer_id
        WHERE fp.active=1 AND fp.tracking=1
          AND fp.filament_key IS NOT NULL
          AND TRIM(fp.filament_key) <> ''
    """)}
    conn.close()
    seen = set()
    for i, x in enumerate(payload["offers"]):
        key = x.get("filament_key")
        material = valid[key][0].upper().strip() if key in valid else None
        if key not in valid:
            raise ValueError(f"Oferta {i}: filament_key não monitorado: {key}")
        if not x.get("url", "").startswith(("http://", "https://")):
            raise ValueError(f"Oferta {i}: URL inválida")
        # URL precisa ser uma página de produto verificável, não busca/listagem.
        if offer_rules.is_listing_url(x["url"]):
            raise ValueError(f"Oferta {i}: URL de listagem/busca não é oferta verificável: {x['url']}")
        # Disponibilidade é obrigatória: só ofertas comprovadamente disponíveis
        # entram no snapshot (evita registrar preço de produto esgotado como se
        # fosse comprável). Aceita bool, 1/0 e strings ('em estoque'/'sem estoque').
        avail = offer_rules.parse_availability(x.get("available"))
        if avail is not True:
            reason = "indisponível" if avail is False else "disponibilidade ausente/desconhecida"
            raise ValueError(f"Oferta {i}: {reason} ({x.get('available')!r}); apenas ofertas disponíveis são aceitas")
        # Só entra como preço quem entrega em São Paulo. Ofertas internacionais têm
        # preço incompleto (sem frete/impostos) e não servem de referência.
        if x.get("deliverable_to_sao_paulo") is False:
            raise ValueError(f"Oferta {i}: não entrega em São Paulo")
        if x.get("international") or x.get("price_pending_shipping_taxes"):
            raise ValueError(f"Oferta {i}: oferta internacional (preço sem frete/impostos) não é preço de referência: {x['url']}")
        quantity = int(x.get("quantity", 0))
        unit_weight_g = float(x.get("unit_weight_g", 0))
        if float(x.get("price", 0)) <= 0 or unit_weight_g <= 0 or quantity <= 0:
            raise ValueError(f"Oferta {i}: preço/peso/quantidade inválidos")

        # O preço de referência do FilamentDB é sempre BRL. O coletor já converte
        # USD->BRL antes de gravar o snapshot; qualquer oferta que chegue aqui em
        # outra moeda é um erro de coleta, não algo a normalizar tarde demais.
        cur = str(x.get("currency", "BRL")).strip().upper()
        if cur != "BRL":
            raise ValueError(f"Oferta {i}: currency deve ser BRL no snapshot (recebido {cur!r})")

        # price_basis é obrigatório e explícito: adivinhar por texto no import é
        # justamente uma das causas de R$/kg maluco. Exigir o campo elimina isso.
        basis = x.get("price_basis")
        if basis not in ("unit", "total"):
            raise ValueError(f"Oferta {i}: price_basis obrigatório e deve ser 'unit' ou 'total' (recebido {basis!r})")

        expected = float(x["price"]) * quantity if basis == "unit" else float(x["price"])
        total_price = float(x.get("total_price", 0))
        if abs(total_price - expected) > 0.02:
            raise ValueError(f"Oferta {i}: total_price inconsistente")

        # Sanity check do preço de referência (R$/kg sobre o peso total da oferta).
        # Pega tanto o preço baixo irreal (basis/peso errados, promo inventada)
        # quanto o alto absurdo, antes de publicar.
        total_g = unit_weight_g * quantity
        price_per_kg = total_price / total_g * 1000
        lo, hi = _perkg_range(material)
        if not (lo <= price_per_kg <= hi):
            raise ValueError(
                f"Oferta {i}: R$/kg fora da faixa plausível para {material}: "
                f"R$ {price_per_kg:.2f}/kg (faixa {lo:.0f}-{hi:.0f}); "
                f"price={x.get('price')} total={total_price} qty={quantity} "
                f"unit_weight_g={unit_weight_g} basis={basis} | {x.get('url')}"
            )

        dedupe = (key, x.get("store"), x.get("url"), x.get("quantity"), x.get("unit_weight_g"), basis)
        if dedupe in seen:
            raise ValueError(f"Oferta duplicada: {dedupe}")
        seen.add(dedupe)
    print(f"[OK] Snapshot válido: {path.name} | ofertas={len(payload['offers'])} | resultados={len(payload['collection'])}")


if __name__ == "__main__":
    files = [Path(sys.argv[1])] if len(sys.argv) > 1 else sorted(DATA.glob("*.json"))[-1:]
    if not files:
        raise SystemExit("Nenhum snapshot encontrado")
    for f in files:
        main(f)
