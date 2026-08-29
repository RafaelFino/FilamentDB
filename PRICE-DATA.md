# Arquitetura de preços e snapshots

## Objetivo

O módulo de preços do FilamentDB é uma camada de inteligência de mercado separada do catálogo de filamentos. O catálogo (`filament.db`) continua sendo a fonte de verdade dos produtos monitorados; os preços são observações externas e devem permanecer historicamente reproduzíveis.

## Fontes de verdade

- `data/filament-data/*.yaml` e o `filament.db`: catálogo, fabricantes, materiais, linhas, perfis e `tracking`.
- `data/price-data/YYYY-MM-DD.json`: snapshots diários versionados no Git. Esta é a fonte de verdade dos dados de coleta.
- `data/price-history.db`: projeção SQLite dos snapshots para consultas rápidas da aplicação. Pode ser reconstruído a partir de `price-data/*.json`.

O banco de preços não deve ser tratado como a fonte primária da coleta. Se ele for perdido, a reconstrução deve ser feita executando `python3 scripts/import_price_data.py`.

## Fluxo de deploy

```text
GitHub
  │
  ├── data/price-data/*.json
  │
  ▼
git pull
  │
  ├── build.py → filament.db
  │
  ├── scripts/import_price_data.py → price-history.db
  │
  └── systemctl restart
```

`update-server.sh` fica em `scripts/update-server.sh` e deve importar os snapshots antes de reiniciar o serviço. O banco de preços também recebe backup antes das alterações do deploy. Se build ou import falhar, o serviço não é reiniciado.

## Snapshots

Um snapshot representa o resultado completo de uma coleta. Não deve conter somente a melhor oferta. Todas as ofertas relevantes e verificáveis devem ser preservadas para permitir análise de promoções, dispersão de preços e variação histórica.

Nome recomendado: `data/price-data/YYYY-MM-DD.json`.

Campos importantes de uma oferta:

- `filament_key`: chave canônica do catálogo em minúsculas: `material|fabricante|modelo/linha`.
- `color_name`: cor observada.
- `store` e `domain`: fonte.
- `url`: link direto da oferta, quando disponível.
- `seller`: vendedor.
- `quantity`: quantidade de rolos na oferta.
- `unit_weight_g`: peso de cada rolo.
- `price`: preço observado, cuja interpretação é definida por `price_basis`.
- `price_basis`: `unit` quando o preço é por rolo/unidade; `total` quando é o preço do kit/pacote inteiro.
- `total_price`: valor total da oferta, normalizado pelo coletor.
- `shipping`: frete quando conhecido.
- `available`: disponibilidade.
- `original_price`: preço de referência quando conhecido.
- `notes`: contexto da observação.

### Quantidade e preço

Quantidade é uma dimensão da oferta. Uma oferta de 1 kg por R$109 e uma oferta de 3 kg por R$299 são ofertas diferentes.

O preço por kg é calculado sempre sobre o peso total da oferta:

`peso_total = quantity × unit_weight_g`

`R$/kg = total_price ÷ peso_total × 1000`

Para ofertas cujo preço publicado é por rolo, `price_basis=unit` e `total_price=price×quantity`. Para kits/pacotes, `price_basis=total` e `total_price=price`.

Isso evita o erro clássico de dividir um preço unitário de atacado pelo peso total do lote e produzir um valor artificialmente 10x/100x menor.

### Ofertas no mesmo URL

O mesmo URL pode conter faixas de quantidade diferentes, especialmente em lojas oficiais. Portanto URL não identifica sozinha uma oferta. A identidade operacional é `store + url + quantity + unit_weight_g + price_basis`, armazenada como `offer_key`.

## Correlação com o catálogo

O coletor deve usar obrigatoriamente `filament_key` existente no catálogo. Nunca deve inferir que dois fabricantes são equivalentes porque o nome comercial parece parecido. Uma oferta Elegoo nunca deve ser relacionada a Voolt3D, por exemplo.

Cor não faz parte da identidade do perfil: é uma dimensão 1:N das variantes e da oferta.

## Linhas SUNLU

`Meta` e `Matte` são linhas diferentes. Para o monitoramento, também são distintas as linhas High Speed e High Speed Matte quando existirem separadamente. Exemplos: `pla|sunlu|meta`, `pla|sunlu|matte`, `pla|sunlu|high speed`, `pla|sunlu|high speed matte`.

## Importação

`src/prices.py` não importa snapshots durante uma requisição HTTP. A leitura da UI é somente leitura.

O importador explícito é:

```bash
python3 scripts/import_price_data.py
```

A importação é idempotente por arquivo/hash. Um snapshot inalterado não gera duplicação. Se um arquivo existente for deliberadamente corrigido e o hash mudar, a execução permite reprocessar o metadata da coleta; as linhas históricas existentes permanecem preservadas.

## Log de coleta

Cada snapshot pode conter resultados de coleta mesmo quando nenhuma oferta foi encontrada. A aplicação mostra esse log para diferenciar:

- fonte consultada com ofertas;
- fonte consultada sem oferta;
- fonte com resultado parcial;
- erro/limitação de obtenção de link direto.

O objetivo é permitir auditoria da coleta e impedir que `nenhum preço` seja confundido com `nenhuma busca foi feita`.

## Interface

A tela de preços deve funcionar em desktop, tablet e celular.

No desktop, a comparação usa uma tabela com grupos por material → fabricante e todas as ofertas. Em telas menores, cada filamento vira um card e as ofertas passam a ocupar blocos empilhados. Filtros ocupam largura total no celular. O log de coletas também é responsivo.

Indicadores da última coleta mostram snapshot, status, quantidade de ofertas e fontes com/sem resultado.

## Regras para o futuro agente coletor

1. Ler apenas perfis com `tracking=1`.
2. Respeitar exatamente o `filament_key` do catálogo.
3. Pesquisar todas as fontes habilitadas em `data/price-sources.json`.
4. Preservar todas as ofertas relevantes encontradas, não somente a vencedora.
5. Priorizar links diretos verificáveis.
6. Registrar cor, quantidade, peso, preço, frete, disponibilidade e vendedor quando disponíveis.
7. Declarar `price_basis` explicitamente.
8. Registrar também o que não foi encontrado no bloco `collection`.
9. Não inventar correspondências entre fabricantes, linhas ou materiais.
10. Gerar um snapshot diário e fazer commit/push do JSON.

A automação diária do agente de aquisição é deliberadamente separada desta camada de aplicação e será implementada posteriormente.
