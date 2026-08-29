# PRICE-COLLECTOR.md — contrato do agente de coleta

Este documento define o comportamento do agente que, futuramente, fará a coleta diária. O agente **não escreve `price-history.db`**. Ele lê o catálogo, pesquisa as fontes e publica um snapshot JSON no Git.

## Entrada

1. Ler `filament.db`.
2. Selecionar somente `filament_profiles.tracking = 1`.
3. Usar exatamente o `filament_key` existente.
4. Consultar variantes/cores relevantes.
5. Consultar as fontes habilitadas em `data/price-sources.json`.

## Escopo atual

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

A coleta também deve registrar o que não encontrou. Para cada fonte relevante, usar `collection` com `found`, `not_found`, `partial` ou `error` e explicar a razão em `notes`.

`not_found` não significa que a busca não foi feita. Significa que a pesquisa foi realizada e não resultou em uma oferta direta confiável.

## Saída

Gerar exatamente um arquivo diário:

`data/price-data/YYYY-MM-DD.json`

O JSON deve conter `schema_version`, `snapshot_date`, `collected_at`, `collector`, `offers` e `collection`. Validar JSON, chaves, duplicidades e URLs antes do commit.

O agente deve fazer commit/push apenas depois de validar o snapshot. O servidor fará o restante no deploy.

## O agente não deve

- editar `price-history.db`;
- apagar snapshots anteriores;
- inventar preços ou links;
- substituir todas as ofertas pela vencedora;
- criar novos `filament_key`;
- confundir Meta com Matte;
- confundir fabricante da oferta com fabricante da loja/marketplace.
