# PRICE_AGENT.md

## Papel

O agente de preços é responsável somente pela aquisição diária e publicação dos dados. A aplicação e o deploy são responsáveis pela projeção para SQLite.

```text
CATÁLOGO → PESQUISA WEB COM IA → SNAPSHOT JSON → Git → DEPLOY → SQLite → UI
```

## Automação diária

A execução ocorre no GitHub Actions por `.github/workflows/price-collector.yml`, fora do servidor de produção. O workflow roda diariamente às 03:30 no horário de São Paulo (06:30 UTC) e também pode ser disparado manualmente.

O workflow:

1. faz checkout do repositório;
2. lê o `filament.db` versionado;
3. seleciona somente `filament_profiles.tracking = 1`;
4. consulta a Web Search da OpenAI por meio da Responses API;
5. pesquisa todas as fontes habilitadas em `data/price-sources.json`;
6. preserva todas as ofertas diretamente verificáveis, não apenas a vencedora;
7. registra resultados `found`, `not_found`, `partial` e `error`;
8. valida identidade, URL, preço, peso, quantidade e `total_price`;
9. gera `data/price-data/YYYY-MM-DD.json`;
10. faz commit e push do snapshot para `main`.

A API usa Structured Outputs para manter o formato do JSON estável e a ferramenta Web Search para obter dados atuais. O modelo padrão é `gpt-5.6-luna`, configurável pela variável de repositório `OPENAI_PRICE_MODEL`.

## Segredo necessário

O repositório precisa ter o secret `OPENAI_API_KEY`. A chave nunca deve ser gravada no código, nos snapshots ou em arquivos do projeto.

## Escopo

Priorizar PLA e PETG de alta qualidade, incluindo Premium, Matte/Velvet e linhas High Speed/High Fluidity equivalentes. Fabricantes prioritários: Voolt3D, 3D Lab, F3D, SUNLU, eSUN, Elegoo e Creality.

Para SUNLU, `Meta`, `Matte`, `High Speed` e `High Speed Matte` são linhas distintas e nunca devem ser normalizadas entre si.

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

Exemplos:

- `1 × 1kg por R$ 109`: `quantity=1`, `price_basis=total`, `total_price=109`.
- `3 × 1kg por R$ 299`: `quantity=3`, `price_basis=total`, `total_price=299`.
- `10+ rolos a R$ 88,10 por rolo`: `quantity=10`, `price_basis=unit`, `total_price=881`.

## Resultado negativo

A coleta também registra o que não encontrou. Para cada fonte relevante, usa `collection` com `found`, `not_found`, `partial` ou `error` e explica a razão em `notes`.

`not_found` não significa que a busca não foi feita. Significa que a pesquisa foi realizada e não resultou em uma oferta direta confiável.

## Saída

Gerar exatamente um arquivo diário:

`data/price-data/YYYY-MM-DD.json`

O JSON contém `schema_version`, `snapshot_date`, `collected_at`, `collector`, `collector_version`, `scope`, `offers` e `collection`.

O workflow valida o snapshot antes do commit. O agente não escreve `price-history.db`.

## Pós-coleta

O servidor não pesquisa preços. `scripts/update-server.sh` executa `scripts/import_price_data.py` depois do build e antes do restart. O importer é idempotente e usa `data/price-data/*.json` como fonte de verdade.

## Integridade

`filament.db` continua sendo a autoridade sobre identidade de produtos. `price-history.db` é descartável/reconstruível. Snapshots são o histórico auditável e devem permanecer versionados no Git.
