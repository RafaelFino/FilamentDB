# Price History

Banco separado para inteligência de preços do FilamentDB.

## Princípio

`filament.db` é a fonte canônica do catálogo. `price-history.db` guarda somente:

- lojas e marketplaces;
- ofertas e URLs diretas;
- snapshots de preço;
- disponibilidade, frete e cupons quando coletados;
- execuções/coletas.

A ligação é **exclusivamente por `filament_id`**, correspondente a `filament_profiles.id` no `filament.db`.

SQLite não permite uma foreign key entre dois arquivos de banco separados; por isso o vínculo é lógico e `scripts/price_history.py` valida que o ID existe e que `tracking=1` antes de inserir uma oferta.

## Inicialização

Depois de gerar o catálogo:

```bash
python3 scripts/price_history.py
```

Para criar somente o schema:

```bash
python3 scripts/price_history.py --init-only
```

O arquivo `price-history.db` é runtime data e não deve ser versionado no Git.

## Modelo

- `stores`: origem da oferta.
- `offers`: uma oferta persistente por URL/loja, ligada ao `filament_id`.
- `price_snapshots`: histórico imutável das observações de preço.
- `collection_runs`: auditoria das coletas.
- `current_offers`: view com o snapshot mais recente de cada oferta ativa.

Não duplicamos marca, material, linha, acabamento, propriedades ou variantes do catálogo.
