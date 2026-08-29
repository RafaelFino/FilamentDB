# Price data

Esta pasta contém os **snapshots imutáveis de coleta de preços**. Um arquivo JSON é criado por dia pelo agente de preços e versionado no Git.

## Convenção

`YYYY-MM-DD.json`

O snapshot deve conter:

- `schema_version`;
- `snapshot_date` e `collected_at`;
- identificação/versionamento do coletor;
- escopo da pesquisa;
- `offers`: **todas as ofertas encontradas**, não apenas a melhor;
- `collection`: resultado da pesquisa por fonte/escopo, inclusive `not_found`, com observações.

Cada oferta deve preservar `filament_key`, cor, loja, URL direta, vendedor, quantidade, peso unitário, preço, frete, preço total, moeda, disponibilidade e observações quando disponíveis. Kits e múltiplos rolos permanecem como uma única oferta comercial e são normalizados pela aplicação em R$/kg.

## Regra de persistência

Nunca editar ou apagar snapshots históricos para corrigir o banco. O banco `price-history.db` é uma projeção reconstruível. O importador é idempotente e identifica snapshots por arquivo/hash.

## Reconstrução

```bash
python scripts/import_price_data.py
```

O comando lê todos os `*.json` desta pasta e atualiza `data/price-history.db`.
