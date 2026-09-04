# Auditoria de preços — FilamentDB

**Data da auditoria:** 03/09/2026
**Escopo:** comparação entre os preços coletados pelo pipeline (snapshots + `price-history.db`) e os preços reais observados nas mesmas URLs no dia da auditoria.
**Câmbio de referência no dia:** USD-BRL = 5,0998 (AwesomeAPI, campo `bid`).

## Sumário executivo

O cálculo de R$/kg da aplicação e os dados hoje persistidos no `price-history.db` estão coerentes (faixa R$77–142/kg). O problema dos "preços malucos" **não está no cálculo nem no armazenamento — está na aquisição**: os LLMs do job alucinam preço, disponibilidade e SKU quando a busca não devolve o dado concreto, e captam preços de sites internacionais em USD tratando-os como BRL. Nada no pipeline verificava a oferta contra a página real.

Esta auditoria comprovou o comportamento reproduzindo o job com os modelos reais e comparou os valores com o preço efetivamente praticado.

## Evidência: alucinação capturada ao vivo

Reproduzindo o job com o modelo `openai/gpt-oss-20b` (Groq), um dos provedores default do workflow, com busca web real:

| filament_key | Coletado pelo LLM | Real na página (03/09) | Erro |
|---|---|---|---|
| `petg\|3dlab\|petg line` | **R$29,90**, `available:"em estoque"`, `external_id:"3dlab-petg-black"` | R$107,88 Pix / R$119,87 cartão, em estoque | preço ~72% abaixo; SKU e título inventados |
| `pla\|voolt3d\|velvet line` | oscilou R$68,00 / R$84,90 | R$79,90 Pix / R$84,10 cartão, **sem estoque** | preço instável; disponibilidade falsa |

O modelo apontou a URL correta mas fabricou os números. Este é exatamente o sintoma relatado: "abro o site e o preço baixo não aparece".

## Comparação coletado × real (fontes verificáveis)

Preços reais lidos diretamente das páginas (lojas próprias) ou via busca de shopping BR (marketplaces bloqueiam scraping direto).

| Produto | Loja | Coletado | Real hoje (03/09) | Veredito |
|---|---|---|---|---|
| 3D Lab PLA Premium | 3D Lab | R$89,90 | R$89,90 Pix / R$99,89 cartão | ✅ correto (Pix) |
| 3D Lab PLA atacado (tiers) | 3D Lab | R$86,30 / 83,61 / … | confirma tabela real (10-19→86,30; 20-49→83,61) | ✅ correto |
| 3D Lab PETG | 3D Lab | R$97,89 | R$107,88 Pix / R$119,87 cartão | ❌ não bate com nenhum preço da página |
| Voolt3D PLA Velvet 1kg | Voolt3D | R$84,90, "em estoque" | R$79,90 Pix / R$84,10 cartão, **sem estoque** | ❌ preço de cartão em vez de Pix; estoque falso |
| Creality Hyper PETG | Creality Brasil | R$109,00 | R$109,00 Pix / R$121,11 cartão, **esgotado** | ⚠️ preço certo, mas esgotado (não deveria contar) |
| Elegoo PLA Matte 1kg | Mercado Livre | R$139,90 | mercado real ~R$87–99 (Translaser R$87,21) | ❌ ~40–60% acima do real |
| Elegoo PLA Matte 1kg | Shopee | R$125,40 | idem acima | ❌ acima do real |
| Voolt3D PLA Velvet 1kg | Mercado Livre | R$117,70 | mercado real R$79,90–89,37 | ❌ bem acima do real |
| SUNLU Meta PLA 1kg | Amazon | R$141,87 | amazon.com global: **US$13,98** (≈R$71 convertido) | ⚠️ provável preço internacional em USD |
| SUNLU PETG HS 2kg | Amazon | R$190,80 | amazon.com global: **US$13,99/kg** | ⚠️ provável preço internacional em USD |
| PETG 500g | Loja 3D House | R$79,90 (500g → R$159,80/kg) | 500g confirmado | ⚠️ meio-rolo real infla o R$/kg |
| PETG 1kg | Loja 3D House | R$119,90, URL `/3d-lab` | R$107,91 cartão / **R$103,59 Pix**; URL é vitrine | ❌ preço errado + URL de listagem |
| F3D PLA / PETG | F3D | R$89,91 / R$80,99 | preço via JS, não exposto na página estática | ⚠️ URL não expõe preço → risco de valor inventado |

## Padrões de erro identificados

1. **Alucinação de preço/estoque/SKU** (mais grave). O LLM preenche campos com valores plausíveis mas falsos quando a busca não traz o dado. Sem verificação contra a página, o valor entra no snapshot.
2. **Moeda USD tratada como BRL.** A busca frequentemente retorna o marketplace global (amazon.com) em dólar; o número é gravado como se fosse real. Ex.: US$13,99 → "R$13,99".
3. **Preço de cartão vs Pix vs atacado.** As lojas exibem 3+ preços; o agente escolhia qualquer um, sem critério consistente.
4. **Disponibilidade inventada.** Produtos esgotados (Voolt Velvet, Creality Hyper) registrados como disponíveis.
5. **URL de listagem/vitrine em vez de página de produto.** Ex.: `mercadolivre.com.br/loja/voolt3d?...recos_listing=true` e `loja3dhouse.com.br/3d-lab`. Impede reverificação.
6. **Peso/`price_basis` inconsistentes.** Meia-bobina (500g) misturada com rolo cheio distorce a comparação de R$/kg.

## Correções implementadas

Regra central reforçada: **o preço de referência é sempre R$/kg de uma oferta válida** — disponível para venda **e** entregável em São Paulo/SP.

### Câmbio USD→BRL (`src/currency.py`)
Cotação USD-BRL da AwesomeAPI (campo `bid`), cache por processo, fallback via `FILAMENTDB_USD_BRL_FALLBACK`. Conversão aplicada no coletor, na API de ingestão e no import de snapshot. Metadados de auditoria (`fx_rate`, `fx_source`, `original_currency`, `original_price_value`) preservados.

### Regras de oferta válida (`src/offer_rules.py`) — fonte única
- **Detecção de moeda por domínio:** `amazon.com`/`aliexpress.com`/etc. → USD; `.co.uk` → GBP; `.de` → EUR. Corrige o preço internacional rotulado como BRL.
- **Classificação internacional:** oferta de site internacional recebe `international=true` e `price_pending_shipping_taxes=true` (preço sem frete e impostos de importação) — **não** serve como preço de referência.
- **Entrega em São Paulo:** `deliverable_to_sao_paulo`; ofertas que não entregam em SP não contam.
- **Disponibilidade normalizada:** `parse_availability` interpreta "em estoque"/"sem estoque"/bool/1-0. Só oferta disponível conta.
- **Rejeição de URL de listagem/busca:** busca, categoria, `/loja/`, `recos_listing=true`.

### Validador (`scripts/validate_price_snapshot.py`)
Além da consistência de `total_price`, agora:
- sanity check de R$/kg por material com **piso global de R$50/kg** (PLA/PETG/ABS/ASA 50–400/450/500, TPU 60–700, *-CF 120–900);
- exige `currency=BRL` e `price_basis` explícito;
- exige `available=true` (normalizado);
- rejeita oferta internacional / não entregável em SP;
- rejeita URL de listagem.

### Coletor e API
- `submit_offer` instrui o modelo a nunca inventar preço/estoque/SKU, usar a página do produto, informar a moeda real e `deliverable_to_sao_paulo`.
- API de ingestão e import de snapshot aplicam as mesmas regras (defesa em profundidade).

## Limitações conhecidas

- **Verificação de preço na página ainda não é feita** (o pipeline confia no que o LLM reporta). A mitigação atual é o sanity check de R$/kg + regras de validade, que barram os casos absurdos, mas não um erro "plausível" de ±20%. Próximo passo recomendado: fetch da página e confirmação do preço antes de aceitar (`price_verified`).
- **Vitrine de marca com slug ambíguo** (ex.: `loja3dhouse.com.br/3d-lab`) não é detectada como listagem sem risco de falso-positivo; depende de verificação de conteúdo.
- **Preço de cartão vs Pix** ainda não tem critério único forçado; recomenda-se padronizar no preço à vista/Pix e gravar o de cartão como `original_price`.

## Recomendações de próximos passos

1. Implementar verificação de preço na página (fetch + confirmação) e marcar `price_verified`.
2. Padronizar o preço de referência em à vista/Pix.
3. Adicionar faixa esperada de R$/kg por linha no catálogo (`filament-data`) para flag de desvio fino.
4. Provisionar chaves de LLM com cota adequada — no dia da auditoria, Groq esgotou o limite diário de tokens e Cerebras/Z.ai estavam sem saldo, o que reduz a cobertura do job.
