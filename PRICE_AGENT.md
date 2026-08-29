# PRICE_AGENT.md

## Papel

O agente de preços é responsável somente pela aquisição diária e publicação dos dados. A aplicação e o deploy são responsáveis pela projeção para SQLite.

```text
CATÁLOGO → PESQUISA → SNAPSHOT JSON → Git → DEPLOY → SQLite → UI
```

## Execução futura

A execução diária deverá ocorrer fora do servidor de produção, preferencialmente em uma automação do GitHub. O agente deve:

1. ler `tracking=1`;
2. pesquisar todas as fontes habilitadas;
3. guardar todas as ofertas válidas;
4. registrar resultados negativos;
5. gerar o snapshot diário;
6. validar o arquivo;
7. fazer commit/push.

A automação diária ainda não faz parte desta etapa da implementação.

## Pós-coleta

O servidor não pesquisa preços. `scripts/update-server.sh` executa `scripts/import_price_data.py` depois do build e antes do restart. O importer é idempotente e usa `data/price-data/*.json` como fonte de verdade.

## Integridade

`filament.db` continua sendo a autoridade sobre identidade de produtos. `price-history.db` é descartável/reconstruível. Snapshots são o histórico auditável e devem permanecer versionados no Git.
