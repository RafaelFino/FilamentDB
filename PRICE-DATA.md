# Arquitetura de dados de preços

## Objetivo

O monitor de preços do FilamentDB deve preservar a massa de dados bruta de cada coleta para permitir análise de promoções, variações, médias, medianas e oportunidades ao longo do tempo. A aplicação não deve depender de uma única oferta vencedora.

## Fontes de verdade

### `filament.db`
Catálogo canônico e regenerável. A identidade é `filament_key`, derivada de material + fabricante + modelo/linha, normalizada em lowercase. A correlação de preços **sempre** usa essa chave. Cor é uma dimensão 1:N do filamento e é registrada na oferta por `variant_id`/nome de cor.

### `data/price-data/*.json`
Fonte histórica primária das coletas. Cada arquivo representa uma coleta diária e é imutável depois de publicado. Contém todas as ofertas encontradas e o resultado explícito das pesquisas, inclusive fontes sem resultado. Deve ser versionado no Git.

### `data/price-history.db`
Projeção operacional consultada pela aplicação. Pode ser reconstruída a partir de `price-data/*.json`; portanto, não é a fonte de verdade da coleta. O histórico não deve ser apagado durante deploy.

## Fluxo

```text
price agent
  -> pesquisa fontes
  -> valida identidade/link/preço
  -> gera data/price-data/YYYY-MM-DD.json
  -> commit + push

servidor
  -> git pull
  -> importação idempotente dos snapshots
  -> price-history.db
  -> aplicação
```

O `update-server.sh` do ambiente de produção deve executar o importador depois do `git pull`/atualização do código. O repositório fornece `scripts/import_price_data.py` para esse hook. O `run.sh` também sincroniza snapshots ao iniciar a aplicação, servindo como fallback para ambientes locais.

## Modelo comercial

Uma oferta é identificada operacionalmente pela loja + URL. A mesma oferta pode aparecer em vários snapshots e recebe vários `price_snapshots`. Quantidade e peso fazem parte da oferta: `3 x 1 kg por R$ 299` não deve ser transformado em `R$ 299` sem contexto. A UI calcula o custo normalizado por kg.

Todas as ofertas permanecem no banco. `current_offers` mostra a observação mais recente de cada oferta ativa; `price_snapshots` mantém a série completa.

## Coleta

O escopo atual prioriza PLA/PETG de linhas premium, matte/velvet e fabricantes monitorados. As fontes incluem lojas oficiais e marketplaces definidos no catálogo de fontes. Uma fonte pode ter `found` ou `not_found`; `not_found` não significa erro e deve trazer uma nota quando a busca não produziu um link direto confiável.

O agente deve preferir links diretos da oferta. Resultados de busca, páginas intermediárias ou links que não permitam identificar claramente produto/fabricante não devem ser registrados como oferta apenas para aumentar a quantidade de dados.

## Idempotência e integridade

- Cada snapshot possui `snapshot_file` e SHA-256.
- Reimportar o mesmo arquivo não duplica dados.
- Falha de um snapshot não deve apagar snapshots anteriores.
- O fabricante da oferta deve ser compatível com `filament_key`.
- Loja oficial de um fabricante não pode representar outro fabricante. Marketplaces podem vender qualquer fabricante.
- JSON inválido gera uma execução marcada como `error`, sem destruir o histórico existente.

## UI

A página de preços exibe todos os filamentos monitorados, todas as ofertas atuais conhecidas e métricas derivadas. Abaixo do relatório existe um log das coletas recentes, mostrando snapshot, status, quantidade de ofertas e resultados por fonte, inclusive o que não foi encontrado.
