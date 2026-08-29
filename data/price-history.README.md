# Price History

Banco separado para inteligência de preços do FilamentDB.

## Baseline inicial

A baseline de 29/08/2026 contém somente ofertas com **URL direta verificável**. As ofertas são ligadas ao catálogo exclusivamente por `filament_id`; os nomes dos perfis são usados apenas pelo script para resolver o ID atual do `filament.db` durante a carga inicial.

Ofertas sem `filament_id` correspondente no catálogo não são inventadas nem inseridas. Isso é especialmente relevante para fontes como eSUN que ainda não possuem perfil no catálogo.

## Inicialização

```bash
python3 scripts/price_history.py
```

Somente schema:

```bash
python3 scripts/price_history.py --init-only
```

O `price-history.db` é runtime data e permanece fora do Git. A carga inicial versionada fica no código do script para ser reproduzível.

## Modelo

- `stores`: origem da oferta.
- `offers`: oferta persistente por loja/URL, ligada ao `filament_id`.
- `price_snapshots`: histórico imutável de observações.
- `collection_runs`: auditoria das coletas.
- `current_offers`: view do snapshot mais recente.

Não duplicamos marca, material, linha, acabamento, propriedades ou variantes do catálogo.
