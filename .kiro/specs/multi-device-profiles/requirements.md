# Requirements — Perfis Multi-Device

## Introdução

Hoje o FilamentDB gera perfis de processo e filamento exclusivamente para a
**Creality K2** (0.4mm). A identidade da máquina está implícita e hardcoded em
vários pontos do `build.py`:

- `inherits` dos perfis de processo (Creality Print e Orca) aponta para a cadeia
  `"...@Creality K2 0.4 nozzle"`.
- `compatible_printers` dos perfis Orca é fixo em `["Creality K2 0.4 nozzle"]`.
- O sufixo `@K2` no nome do filamento Orca.
- Os caps físicos (600 mm/s extrusão, 800 mm/s travel, 20000 mm/s² aceleração)
  estão escritos à mão em `generate_process_profile`.
- As velocidades base por material (`process-base/materials/*.json`) representam
  o alvo Standard para a K2.

O objetivo é introduzir o **device** como dimensão de primeira classe no
pipeline (igual a material, profile_type e layer_height), permitindo gerar
perfis para múltiplas impressoras a partir da mesma base. O primeiro device
adicional é a **Elegoo Centauri Carbon 2 (CC2)** — CoreXY, Direct Drive, bico
0.4mm/350°C, volume 256×256×256mm, 500 mm/s / 20000 mm/s², firmware Klipper.

O caso de uso concreto: fatiar STLs no OrcaSlicer local e exportar `.3mf`
auto-contido (processo + filamento + máquina embutidos) para impressão remota na
CC2 de outra pessoa, sem reconfiguração manual.

Esta spec agrega ainda duas melhorias correlatas ao catálogo/UI, pedidas junto
com o multi-device:

- **Ordenação alfabética consistente** em todos os pontos que exibem
  fabricantes, materiais e tipos/modelos (especialmente combos/dropdowns da tela
  de inclusão), corrigindo o bug de fabricantes fora de ordem.
- **Curadoria de exportação ampliada**: marcar como padrão de exportação
  (`export: true`) todos os perfis PLA e PETG das marcas Elegoo, Voolt3D, Sunlu e
  Creality (todas as variações de cor/qualidade em estoque).

### Fonte de verdade confirmada

- Specs CC2: CoreXY 500 mm/s, 20000 mm/s², 256³mm, bico 350°C, enclosed, Klipper
  ([Elegoo](https://www.elegoo.com/products/centauri-carbon-2),
  [OrcaSlicer CC guide](https://orcaslicer.net/orcaslicer-elegoo-centauri-carbon/)).
  *Conteúdo reformulado para conformidade com restrições de licenciamento.*
- O nome exato do perfil de máquina CC2 no OrcaSlicer (para `inherits` e
  `compatible_printers`) **deve ser confirmado** na instalação alvo antes da
  implementação; a spec trata isso como parâmetro de configuração, não como
  valor adivinhado.

## Glossário

- **Device / printer target**: a impressora alvo (K2, CC2). Define caps físicos,
  cadeia de herança do slicer e `compatible_printers`.
- **Regressão zero (K2)**: após a refatoração, os perfis K2 gerados devem ser
  **byte-idênticos** aos atuais (nome, `inherits`, `compatible_printers`, campos
  e valores), exceto diferenças já intencionais previstas.

## Requisitos

### Requisito 1 — Device como dimensão de configuração

**User Story:** Como mantenedor do FilamentDB, quero descrever cada impressora em
um arquivo de configuração próprio, para que o pipeline gere perfis para
múltiplos devices sem duplicação manual.

#### Acceptance Criteria

1. WHEN o build é executado THEN o sistema SHALL carregar definições de device de
   `process-base/devices/<id>.json`.
2. O arquivo de device SHALL conter, no mínimo: `id`, `display_name`,
   `name_suffix`, caps físicos (`max_extrusion_speed`, `max_travel_speed`,
   `max_acceleration`), e os parâmetros de slicer (`compatible_printers`,
   cadeia de `inherits` por layer height para Orca e Creality Print, mapeamento
   de `filament_inherits` por material).
3. WHEN um campo opcional de device estiver ausente THEN o sistema SHALL aplicar
   um default documentado (ex.: caps da K2) em vez de falhar silenciosamente.
4. WHEN um device referenciado em `combinations.json` não tiver arquivo
   correspondente THEN o build SHALL falhar com erro explícito citando o `id`.

### Requisito 2 — Caps físicos derivados do device

**User Story:** Como mantenedor, quero que os limites de velocidade e aceleração
venham do device, para que cada impressora respeite seus próprios limites sem
código hardcoded.

#### Acceptance Criteria

1. WHEN `generate_process_profile` calcula velocidades THEN o cap de extrusão e
   de travel SHALL vir do device, não de constantes no código.
2. WHEN `generate_process_profile` calcula acelerações THEN o cap de aceleração
   SHALL vir do device.
3. WHEN o device CC2 é usado THEN as velocidades SHALL ser limitadas a 500 mm/s e
   a aceleração a 20000 mm/s², conforme spec.
4. O princípio existente SHALL ser preservado: o cap volumétrico (MVS) continua
   responsabilidade exclusiva do perfil de filamento, nunca do processo.

### Requisito 3 — Herança e compatibilidade por device (Orca e Creality Print)

**User Story:** Como usuário do OrcaSlicer, quero que os perfis apontem para a
máquina correta, para que a herança e a compatibilidade funcionem sem ajuste
manual.

#### Acceptance Criteria

1. WHEN um perfil de processo Orca é exportado para um device THEN seu `inherits`
   SHALL vir da cadeia de herança definida no device (resolvida por layer
   height) e `compatible_printers` SHALL vir do device.
2. WHEN um perfil de filamento Orca é exportado para um device THEN
   `compatible_printers` e o sufixo do nome SHALL vir do device.
3. WHEN um device não tiver cadeia de herança do Creality Print definida THEN o
   sistema SHALL omitir a exportação Creality Print para aquele device (CC2 não
   é suportada pelo Creality Print) sem quebrar o build.
4. O nome do perfil SHALL embutir o `display_name`/sufixo do device, evitando
   colisão entre perfis de devices diferentes.

### Requisito 4 — Combinações por device

**User Story:** Como mantenedor, quero controlar quais combinações
(profile_type × layer_height × material) são geradas por device, para gerar só o
que faz sentido para cada impressora.

#### Acceptance Criteria

1. WHEN `combinations.json` é lido THEN cada entrada de combinação SHALL aceitar
   uma lista `devices`.
2. WHEN uma combinação não especificar `devices` THEN o sistema SHALL assumir um
   device default documentado (K2), preservando o comportamento atual.
3. WHEN o build processa combinações THEN SHALL iterar
   `device × profile_type × layer_height × material`.

### Requisito 5 — Regressão zero para K2

**User Story:** Como mantenedor, quero garantir que a introdução do multi-device
não altere nenhum perfil K2 existente, para não quebrar quem já usa.

#### Acceptance Criteria

1. WHEN o build roda após a refatoração THEN os perfis K2 (Creality Print e Orca)
   SHALL ser idênticos aos gerados antes da mudança (nome, `inherits`,
   `compatible_printers`, conjunto de campos e valores).
2. WHEN os caps da K2 forem movidos para `devices/k2.json` THEN os valores SHALL
   ser exatamente 600/800/20000.
3. A spec SHALL incluir uma verificação de regressão (diff dos JSONs gerados
   antes/depois) como critério de aceite da implementação.

### Requisito 6 — Publicação por device

**User Story:** Como usuário, quero publicar os perfis de cada device em um local
previsível, para sincronizar com o slicer correto.

#### Acceptance Criteria

1. WHEN `publish.sh` roda THEN os perfis Orca de cada device SHALL ser publicados
   em subpastas por device sob `~/filament-db/orca/` (ex.:
   `orca/<device-id>/{filament,process}`), OU a estrutura atual SHALL ser
   mantida para K2 com os devices adicionais em subpastas — a decisão final fica
   no design.
2. WHEN o backup pré-publish roda THEN SHALL incluir os perfis de todos os
   devices.
3. A rotação de backups (últimos 10) SHALL ser preservada.

### Requisito 7 — Documentação atualizada

**User Story:** Como mantenedor futuro, quero a documentação refletindo o
conceito de device, para entender e estender o sistema.

#### Acceptance Criteria

1. WHEN a implementação terminar THEN o steering
   `.kiro/steering/filamentdb-rules.md` SHALL documentar o conceito de device,
   a estrutura `process-base/devices/`, e a separação device/material/processo.
2. WHEN a implementação terminar THEN o `README.md` SHALL descrever como adicionar
   um novo device.
3. A documentação SHALL registrar que a CC2 é Orca-only (sem Creality Print) e o
   requisito de confirmar o nome do perfil de máquina no slicer alvo.

### Requisito 8 — Testes

**User Story:** Como mantenedor, quero testes que protejam o contrato
multi-device, para pegar regressões no build.

#### Acceptance Criteria

1. WHEN a suíte roda THEN SHALL existir teste que valida que todo device
   referenciado em `combinations.json` tem arquivo em `devices/`.
2. WHEN a suíte roda THEN SHALL existir teste que valida, para um device dado,
   que os perfis gerados respeitam os caps do device (nenhuma velocidade/accel
   acima do limite).
3. WHEN a suíte roda THEN SHALL existir teste de regressão K2 (campos-chave do
   perfil Standard 0.20 PLA permanecem os valores atuais).
4. WHEN a suíte roda THEN SHALL existir teste que valida que perfis Orca de um
   device têm `compatible_printers` e `inherits` coerentes com a definição do
   device.
5. Os testes SHALL rodar offline, sem rede nem chaves de LLM, no mesmo job
   `test` do CI atual.

### Requisito 9 — Pipeline de build/CI

**User Story:** Como mantenedor, quero o CI exercitando a geração multi-device,
para que regressões apareçam no PR.

#### Acceptance Criteria

1. WHEN o CI roda o job `test` THEN o build multi-device SHALL ser exercitado
   (geração dos devices configurados) sem rede.
2. WHEN novos testes multi-device forem adicionados THEN SHALL ser executados
   pelo `pytest tests/` já invocado no CI, sem alterar a estrutura de jobs.
3. A mudança NÃO SHALL afetar o job `price-smoke` nem a separação de camadas do
   CI atual.

### Requisito 10 — Ordenação alfabética de fabricantes, materiais e tipos/modelos

**User Story:** Como usuário cadastrando materiais, quero que fabricantes,
materiais e tipos/modelos apareçam em ordem alfabética em toda a UI,
especialmente nos combos, para encontrar itens rapidamente.

#### Contexto do bug

A assimetria entre `build_tree()` e `build_process_tree()` em `src/database.py`
é a causa raiz: `build_process_tree()` reordena o dict de saída, mas
`build_tree()` confia na ordem de inserção do SQL. Além disso, o `ORDER BY name`
do SQLite usa collation binária por padrão (sensível a maiúsculas/acentos) e os
`.sort()` default em `static/main.js` ordenam por code-point, não
alfabeticamente. O combo `#mfr-select` (Filamentos) e os combos em cascata da
inclusão de estoque herdam essa ordem incorreta.

#### Acceptance Criteria

1. WHEN a UI exibe a lista de fabricantes (incluindo `#mfr-select` e os combos de
   inclusão) THEN os fabricantes SHALL aparecer em ordem alfabética
   case-insensitive.
2. WHEN a UI exibe materiais em combos THEN SHALL aparecer em ordem alfabética
   case-insensitive, exceto onde há uma ordenação de domínio deliberada
   (ex.: `MAT_ORDER`/`matRank` na tabela de catálogo), que SHALL ser preservada.
3. WHEN a UI exibe tipos/modelos (linha/variação) em combos THEN SHALL aparecer
   em ordem alfabética.
4. WHEN o combo em cascata de cores/variantes é populado THEN as cores SHALL
   aparecer em ordem alfabética.
5. WHEN as queries de listagem por nome rodam no SQLite THEN SHALL usar
   `COLLATE NOCASE` (ou equivalente) para ordenação case-insensitive em
   `list_manufacturers`, `list_materials` e nos `mf.name`/`m.name` de
   `build_tree()`.
6. WHEN `build_tree()` retorna o dict THEN SHALL reordenar a saída por chave
   (fabricante) de forma defensiva, análogo ao que `build_process_tree()` já
   faz, não dependendo apenas da ordem de inserção.
7. A ordenação de domínio existente (`MAT_ORDER` em `main.js`,
   `mat_rank` em `build_process_tree`) NÃO SHALL ser quebrada por esta mudança.

### Requisito 11 — Curadoria de exportação (lista específica de produtos em uso)

**User Story:** Como usuário, quero que exatamente os filamentos que uso de fato
sejam exportados para o OrcaSlicer e o Creality Print, para ter nos slicers só o
que imprimo, sem poluir com variações que não possuo.

#### Lista curada (fonte de verdade)

Exatamente estes perfis SHALL ter `export: true`, mapeados ao `profile_name` no
YAML:

| Produto | profile_name | YAML | Material | Status |
|---|---|---|---|---|
| Voolt3D PLA Velvet | `Voolt3D PLA Velvet` | voolt3d | PLA | já ✅ |
| Voolt3D PLA High Speed | `Voolt3D PLA High Speed` | voolt3d | PLA | adicionar |
| Voolt3D PLA Macaron | `Voolt3D PLA Macaron` | voolt3d | PLA | adicionar |
| Voolt3D PLA V-Silk | `Voolt3D PLA V-Silk` | voolt3d | PLA | já ✅ |
| Voolt3D PLA CF | `Voolt3D PLA CF` | voolt3d | PLA-CF | adicionar |
| Voolt3D PETG HF | `Voolt3D PETG HF` | voolt3d | PETG | já ✅ |
| Voolt3D ABS | `Voolt3D ABS` | voolt3d | ABS | adicionar |
| Voolt3D TPU | `Voolt3D TPU` | voolt3d | TPU | adicionar |
| Voolt3D PLA Premium Outlet | `Voolt3D PLA Premium Outlet` | voolt3d | PLA | **novo** (Req. 12) |
| Voolt3D PLA EVO | `Voolt3D PLA EVO` | voolt3d | PLA | **novo** (Req. 12) |
| Sunlu PLA High Speed | `Sunlu PLA High Speed` | sunlu | PLA | já ✅ |
| Sunlu PLA Matte | `Sunlu PLA Matte` | sunlu | PLA | adicionar |
| Sunlu PETG HS | `Sunlu PETG HS` | sunlu | PETG | já ✅ |
| Creality Hyper PLA | `Creality Hyper PLA` | creality | PLA | já ✅ |
| Creality CR PETG | `Creality CR PETG` | creality | PETG | já ✅ |
| Creality Hyper PETG | `Creality Hyper PETG` | creality | PETG | já ✅ |
| Elegoo PLA+ | `Elegoo PLA+` | elegoo | PLA | já ✅ |
| Elegoo PLA Pro | `Elegoo PLA Pro` | elegoo | PLA | já ✅ |

#### Acceptance Criteria

1. WHEN o build roda THEN exatamente os perfis da tabela acima SHALL ter
   `export_enabled = 1`; nenhum outro perfil SHALL ser marcado.
2. A flag SHALL ser adicionada/removida no nível do perfil individual
   (`materials.<MATERIAL>.profiles[]`), como irmã de `line`/`commercial_name`.
   Nenhuma mudança em `build.py` é necessária (a flag já é lida como
   `export_enabled`).
3. WHEN existir hoje `export: true` em perfil **fora** da lista curada THEN a
   flag SHALL ser removida, de modo que o conjunto exportado seja exatamente a
   lista. (No estado atual, todos os perfis com a flag estão na lista — Elegoo
   PLA Pro foi incluído — logo nenhuma remoção é necessária.)
4. A restrição de materiais especiais do steering (PLA-CF/ABS/TPU só geram
   **processo** em 0.20mm Standard) aplica-se ao perfil de **processo**; não
   impede a exportação do **filamento** (Voolt3D PLA CF, ABS, TPU).
5. WHEN `publish.sh --list` roda após a mudança THEN a lista exibida SHALL
   corresponder exatamente à tabela curada.
6. A documentação de curadoria (steering) SHALL ser atualizada substituindo a
   lista anterior de ~9 produtos pela nova lista curada.
7. Esta curadoria é uma decisão de produto deliberada e SHALL ser registrada
   como tal na spec.

### Requisito 12 — Novos materiais Voolt3D (PLA Premium Outlet e PLA EVO)

**User Story:** Como usuário, quero cadastrar os filamentos Voolt3D PLA Premium
Outlet e PLA EVO que também uso, para tê-los no catálogo e exportados aos
slicers.

#### Contexto (dados coletados)

- **PLA Premium Outlet**: produto de troca de cor da linha de produção
  (cor imprevisível, pode vir de qualquer linha Voolt3D). Mesma base dos PLA
  tradicionais; posicionado como linha **premium**. Specs oficiais: extrusão
  190-230°C, mesa 50-70°C, Tg ~55°C, MVS até 25 mm³/s, densidade 1,24 g/cm³,
  1,75mm ([Voolt3D](https://voolt3d.com.br/produtos/filamento-pla-outlet/)).
  *Conteúdo reformulado para conformidade com restrições de licenciamento.*
- **PLA EVO**: posicionado como **Standard+** (entre Standard e Premium) — PLA
  com formulação para maior aderência/resistência entre camadas, baixo warping,
  compatível com alta velocidade. Specs oficiais: extrusão 190-230°C, mesa
  50-70°C, Tg ~55°C, MVS até 25 mm³/s, densidade 1,24 g/cm³, 1,75mm, referência
  para bico 0.4mm ([Voolt3D PLA EVO](https://voolt3d.com.br/produtos/filamento-pla-branco-off-white-evo-1kg/)).
  *Conteúdo reformulado para conformidade com restrições de licenciamento.*

#### Acceptance Criteria

1. WHEN o catálogo é construído THEN SHALL existir uma linha (`lines[]`) e um
   perfil (`materials.PLA.profiles[]`) para **Voolt3D PLA Premium Outlet** em
   `filament-data/voolt3d.yaml`, com `profile_name: Voolt3D PLA Premium Outlet`,
   `tier: premium`, MVS 25, extrusão/mesa conforme specs oficiais, e `export: true`.
2. WHEN o catálogo é construído THEN SHALL existir uma linha e um perfil para
   **Voolt3D PLA EVO**, com `profile_name: Voolt3D PLA EVO`, posicionamento
   Standard+, extrusão 190-230°C (initial ~215), mesa 50-70°C, MVS 25, e
   `export: true`, conforme specs oficiais.
3. A `note` do PLA EVO SHALL registrar o diferencial do produto (maior aderência
   e resistência entre camadas, baixo warping, compatível com alta velocidade).
4. O PLA Premium Outlet SHALL registrar na `note` que a cor é indefinida
   (produto de troca de cor) e que linhas com aditivos (Stone/Wood/etc.) podem
   pedir bico ≥0.6mm — informativo, sem alterar o default 0.4mm.
5. Ambos SHALL seguir o schema de perfil existente (nozzle, bed, variants, MVS)
   para serem lidos por `build.py` sem alterações de código.
6. Como PLA puro, ambos SHALL estar disponíveis em todos os profile_types/layer
   heights, conforme a regra atual para PLA.
