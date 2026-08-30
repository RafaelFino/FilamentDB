# PRICE-COLLECTOR.md — contrato do agente de coleta

Este documento define o comportamento do agente que faz a coleta diária. O agente não escreve `price-history.db`. Ele lê o catálogo, pesquisa as fontes e publica um snapshot JSON no Git.

## Execução

A implementação está em `scripts/collect_prices_ai.py` e é executada pelo workflow `.github/workflows/price-collector.yml`.

O workflow usa a OpenAI Responses API com Web Search e Structured Outputs. O modelo padrão é `gpt-5.6-luna`; pode ser alterado por `OPENAI_PRICE_MODEL`.

## Entrada

1. Ler `filament.db`.
2. Selecionar somente `filament_profiles.tracking = 1`.
3. Usar exatamente o `filament_key` existente.
4. Consultar variantes/cores relevantes.
5. Consultar as fontes habilitadas em `data/price-sources.json`.

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

O código também rejeita ofertas com `filament_key` desconhecido, preço/peso/quantidade inválidos ou fabricante incompatível.

## Quantidade e preço

Registrar sempre `quantity` e `unit_weight_g`. Registrar explicitamente `price_basis`: `unit` se o preço é por rolo/unidade e `total` se é o preço do pacote inteiro. Registrar também `total_price`.

Nunca converter um preço por uma constante arbitrária. O agente deve preservar o preço observado e o peso observado; o cálculo de R$/kg pertence à aplicação.

## Resultado negativo

A coleta também registra o que não encontrou. Para cada fonte relevante, usar `collection` com `found`, `not_found`, `partial` ou `error` e explicar a razão em `notes`.

## Saída

Gerar exatamente um arquivo diário:

`data/price-data/YYYY-MM-DD.json`

Validar JSON, chaves, duplicidades, URLs, fabricante, preço, quantidade, peso e `total_price` antes do commit.

## O agente não deve

- editar `price-history.db`;
- apagar snapshots anteriores;
- inventar preços ou links;
- substituir todas as ofertas pela vencedora;
- criar novos `filament_key`;
- confundir Meta com Matte;
- confundir fabricante da oferta com fabricante da loja/marketplace;
- usar página de resultados de busca como URL da oferta.
