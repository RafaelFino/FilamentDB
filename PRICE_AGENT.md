# PRICE_AGENT.md

## Papel

O agente de preços é responsável somente pela aquisição diária e publicação dos dados. A aplicação e o deploy são responsáveis pela projeção para SQLite.

```text
CATÁLOGO → PESQUISA WEB COM IA → SNAPSHOT JSON → API DE INGESTÃO → Git → DEPLOY → SQLite → UI
```

## Automação diária

A execução ocorre no GitHub Actions por `.github/workflows/price-collector.yml`, fora do servidor de produção. O workflow roda diariamente às 03:30 no horário de São Paulo (06:30 UTC) e também pode ser disparado manualmente.

O workflow:

1. faz checkout do repositório;
2. gera o catálogo com `build.py --only-db` em `data/filament.db` (não há `filament.db` versionado na raiz);
3. seleciona somente `filament_profiles.tracking = 1`;
4. consulta os provedores de IA configurados com pesquisa web;
5. pesquisa todas as fontes habilitadas em `data/price-sources.json`;
6. preserva todas as ofertas diretamente verificáveis, não apenas a vencedora;
7. registra resultados `found`, `not_found`, `partial` e `error`;
8. o agente acumula cada oferta completa em memória (via `submit_offer`) — **não** publica durante a coleta;
9. grava `data/price-data/YYYY-MM-DD.json` com as ofertas completas e autocontidas;
10. valida o snapshot offline (`validate_price_snapshot.py`): identidade, URL, preço, peso, quantidade e `total_price`;
11. publica cada oferta por `POST /v1/ingest/prices` (`publish_price_snapshot.py`), etapa separada e explícita;
12. somente depois faz commit e push do snapshot para `main`.

O agente não escreve diretamente em `price-history.db`. A API é a única porta de entrada para os preços produzidos pelo workflow. O snapshot é a fonte de verdade auditável: se a validação falhar, nada é publicado; se a publicação falhar, o snapshot não é commitado.

## Configuração do GitHub Actions

O repositório precisa destes valores:

### Secret

`FILAMENTDB_API_SECRET` — deve ser **exatamente o mesmo valor** usado no servidor em `FILAMENTDB_PROXY_SECRET`. Nunca coloque esse valor no código, em variáveis públicas, no snapshot ou nos commits.

### Variable

`FILAMENTDB_API_URL` — URL pública da API, normalmente:

`https://filamentdb-api.learnops.duckdns.org`

O workflow possui esse valor como fallback, então a variável só é necessária se a URL mudar.

As chaves dos provedores de IA continuam sendo secrets (`OPENAI_API_KEY`, `GROQ_API_KEY`, `GEMINI_API_KEY`, `OPENROUTER_API_KEY`, `Z_API_KEY`, etc.) e não são compartilhadas com o servidor.

## Configuração do servidor

Nenhuma nova chave secreta é necessária no `config.env`. A API reutiliza a variável existente:

```env
FILAMENTDB_PROXY_SECRET=um-segredo-forte-e-privado
```

O mesmo valor deve existir no GitHub Actions como `FILAMENTDB_API_SECRET`. A URL pública é configuração do cliente/workflow, não segredo do servidor.

O serviço da API usa `FILAMENTDB_API_HOST`/`FILAMENTDB_API_PORT` conforme o deployment atual e deve permanecer acessível localmente em `127.0.0.1:5001`, com Caddy fazendo o proxy do hostname público.

## Segurança

A API pública não fica atrás do Pangolin. Ela exige `X-Proxy-Secret` e compara o segredo em tempo constante. O workflow nunca imprime o segredo nos logs.

## Regra principal: todas as ofertas

A coleta não procura apenas o menor preço. Toda oferta relevante, verificável e diretamente vinculada ao produto deve entrar no snapshot. Isso inclui preço normal, promoção, cupom quando observável, kits, múltiplos rolos e faixas de atacado.

## Identidade e segurança

Antes de gravar uma oferta, validar:

- `filament_key` existe no catálogo;
- fabricante da oferta corresponde ao fabricante do catálogo;
- material e linha são compatíveis;
- cor é conhecida ou explicitamente marcada como não confirmada;
- URL aponta para a oferta/produto, e não para uma página genérica de busca;
- preço e moeda são claros.

Nunca associar uma oferta Elegoo a Voolt3D, 3D Lab ou outro fabricante apenas por similaridade textual.

## Quantidade e preço

Registrar sempre `quantity` e `unit_weight_g`. Registrar explicitamente `price_basis`: `unit` se o preço é por rolo/unidade e `total` se é o preço do pacote inteiro. Registrar também `total_price`.

## Resultado negativo

A coleta também registra o que não encontrou. Para cada fonte relevante, usa `collection` com `found`, `not_found`, `partial` ou `error` e explica a razão em `notes`.

`not_found` não significa que a busca não foi feita. Significa que a pesquisa foi realizada e não resultou em uma oferta direta confiável.

## Saída

Gerar exatamente um arquivo diário:

`data/price-data/YYYY-MM-DD.json`

O JSON contém `schema_version`, `snapshot_date`, `collected_at`, `collector`, `collector_version`, `scope`, `offers` e `collection`.

## Publicação pela API

Depois da validação, `scripts/publish_price_snapshot.py` lê o snapshot e envia cada item de `offers` para:

`POST ${FILAMENTDB_API_URL}/v1/ingest/prices`

com o header `X-Proxy-Secret`. O `collected_at` do snapshot é preservado na publicação.

A publicação ocorre antes do commit. Se uma oferta falhar, o workflow falha e o snapshot não é enviado ao Git como se estivesse completo. A API possui deduplicação, portanto uma repetição deliberada de uma publicação não cria duplicatas da mesma oferta.

## Pós-coleta

O servidor não pesquisa preços. `scripts/update-server.sh` executa `scripts/import_price_data.py` depois do build e antes do restart. O importer é idempotente e usa `data/price-data/*.json` como fonte de verdade.

## Integridade

`filament.db` continua sendo a autoridade sobre identidade de produtos. `price-history.db` é descartável/reconstruível. Snapshots são o histórico auditável e devem permanecer versionados no Git.
