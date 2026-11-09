# FilamentDB — Regras de Projeto

## Impressora e Setup

- Impressora: Creality K2 (CoreXY, Direct Drive)
- Nozzle: 0.4mm
- Filamentos de uso principal: Voolt3D Velvet, Sunlu High Speed
- PETG principal: Voolt3D HF, Sunlu PETG, Creality Hyper PETG

## Filosofia de Perfis: Separação de Responsabilidades

O sistema adota uma separação clara entre **perfil de processo** e **perfil de filamento**:

- **Perfil de processo** → define o que a *impressora* e o *profile type* tentam atingir (velocidades alvo, acelerações, estrutura da peça)
- **Perfil de filamento** → define o que o *material* aguenta (`filament_max_volumetric_speed`)
- **Slicer (Creality Print)** → combina os dois em runtime e aplica o menor limitador automaticamente

Isso garante que filamentos premium (Sunlu HS MVS=22; Voolt3D Velvet fica em MVS=8 por decisão de hardware, ver GUIA-CALIBRACAO) aproveitam o máximo da K2, enquanto filamentos mais limitados (Silk MVS=12, PETG genérico MVS=12) são automaticamente contidos sem penalizar os demais. Política: MVS = **menor valor entre fabricante, classe do material (Orca `mvs_default`) e histórico de impressão** — quando houver dúvida ou divergência entre fontes, usar o menor valor. MVS são **inteiros** (o export Orca faz `int()`). Valores acima da classe só com fonte registrada no YAML (hoje: Sunlu PLA HS 22 e Creality Hyper PLA 20). Tetos por classe travados em `tests/test_filament_mvs.py`: PLA ≤ 18, PETG ≤ 12 (Creality Hyper PETG 14), TPU ≤ 6, ABS/ASA/PLA-CF ≤ 12.

**Nunca** limitar velocidades no perfil de processo com base no MVS do material. O cap volumétrico é responsabilidade exclusiva do filamento.

### Recalibração: qualidade antes de velocidade

As velocidades base dos materiais (`process-base/materials/PLA.json`,
`PETG.json`) foram recalibradas para valores **conservadores e realistas** na
K2, priorizando qualidade e confiabilidade sobre tempo. O racional:

- **O número do perfil é a velocidade real.** Nada de inflar velocidades base
  contando com o cap do slicer para segurar — a base já reflete o que a peça
  deve imprimir com boa qualidade.
- Problemas de baixa extrusão e falhas (especialmente PETG de troca de cor)
  vêm de velocidades otimistas demais. Valores menores reduzem under-extrusion,
  stringing e falhas de camada.
- O cap volumétrico (MVS) do filamento continua sendo o limitador superior em
  runtime; a base conservadora apenas garante que, mesmo sem o cap morder, a
  qualidade se mantém.

Bases recalibradas (alvo Standard na K2, mm/s):

```
         inner outer sparse solid  top  init travel supp gap
PLA       300   150    350   250   130   50   700   200  200
PETG      240   120    280   200   110   40   500   160  160
```

ABS/TPU/PLA-CF/PETG-CF **não** foram tocados — já eram conservadores por
material.

## Hierarquia de Perfis de Processo

Do mais rápido ao mais caprichado, mais os tipos especializados:

```
Fast → Economy → Standard → Strong → Detail → Safe
                     ├── LW-Structure (aeromodelo: fuselagem/corpo)
                     └── LW-Extreme   (aeromodelo: asas)
```

> **Nota (overhaul de perfis):** o profile type `factory` foi **removido da
> matriz** de combinações a pedido do usuário. O arquivo
> `process-base/profile_types/factory.json` e a entrada em `PROFILE_MULTIPLIERS`
> **permanecem no repo** (órfãos, não referenciados) para não perder a fonte.

- **Fast**: o mais rápido relativo, dentro do que a K2 entrega (speed 1.15×, accel 1.25×, visíveis 0.75×) — aceita redução de qualidade em troca de tempo. 3 walls, 12% infill grid, inner-first.
- **Economy**: Economia de filamento. Estrutura mínima viável — 2 walls, 8% grid, inner-first. Velocidade igual Standard (inclusive nos campos visíveis, `quality_speed` 0.50) — a economia vem da estrutura reduzida, não da velocidade. Ideal para protótipos descartáveis e peças não-estruturais.
- **Factory** (ÓRFÃO — fora da matriz): perfil de fábrica conservador. Mantido como arquivo/multiplicador no repo, mas **não gerado** (removido de `combinations.json` no overhaul de perfis).
- **Standard**: Equilíbrio geral, padrão de uso diário. 4 walls, 15% gyroid, outer-first, bom acabamento. Usa `quality_speed` **0.50** nos campos visíveis (outer/top/1ª camada/gap) — baixado de 0.60 para melhorar o acabamento das paredes externas. Tem **ironing leve** no top (`ironing_type=top`, `ironing_flow=7%`, `ironing_spacing=0.12`, `ironing_speed=30`) — mantém a intenção leve, **sem** `ironing_pattern`/`ironing_angle` (exclusivos do Detail). Nome obrigatório — Creality Print requer um perfil "Standard" para iniciar.
- **Strong**: Resistência mecânica (6 walls, 50% infill gyroid). Mais lento (speed 0.60×, visíveis 0.45×, sparse 0.50×), peças funcionais. PETG 0.20: outer 54, inner 144, sparse 140 mm/s (fluxo alvo 13.0 mm³/s).
- **Detail**: Qualidade visual máxima. Layer heights baixos (0.12-0.16mm), 5 walls, 20% infill. `quality_speed` 0.45.
- **Safe**: Ultra-conservador para primeira impressão ou materiais desconhecidos (speed 0.55×, visíveis 0.40×, sparse 0.45×). Lento mas confiável; o mais lento de todos nos campos visíveis.
- **Detail**: Qualidade visual máxima. `quality_speed` 0.45. **Ironing completo (6 campos, Detail-only)**: `ironing_type=topmost`, `ironing_pattern=rectilinear` (**RESSALVA**: os presets stock do CP usam internamente `zig-zag`; o slicer pode normalizar/trocar o enum ao abrir o perfil — cosmético, o usuário confirma ao abrir), `ironing_speed=30`, `ironing_flow=50%` (acabamento mais pesado no top que o Standard 7%), `ironing_spacing=0.15`, `ironing_angle=90`. Só o `detail.json` declara `ironing_pattern`/`ironing_angle`; o export (CP e Orca) só os serializa dentro do guard de ironing ativo (`ironing_type != "no ironing"`). A coluna `ironing_flow` é **TEXT/percentual** (saiu de `FLOAT_COLUMNS` — `float("50%")` quebraria o build); `ironing_spacing` continua numérico e é emitido com 2 casas no Orca (o `set_val` padrão arredondaria a 1 casa e colapsaria 0.15→0.1). **ZAA / Z contouring foi REMOVIDO do Detail** (antes `zaa_enabled=1`): o Creality Print não aceita ZAA + ironing no mesmo objeto — com ambos ligados, o fatiador desabilita o ZAA e cai para fatiamento planar, emitindo aviso (`Object ... cannot use Z contouring because of IroningEnabled`). Como o ironing dá ganho de qualidade maior e consistente em topos planos (foco do Detail) e o ZAA nunca chegava a atuar (sempre perdia para o ironing), optou-se por manter ironing e remover os `zaa_*` do `detail.json`. Nenhum profile type declara `zaa_*`; o build mantém as colunas/guards `zaa_*` (serializam só se `zaa_enabled` truthy), mas na prática ficam sempre ausentes. Travado por teste (`ZAADisabledScopeTests` em `tests/test_multi_device.py`): Detail e Standard **não** emitem ZAA.
- **LW-Structure**: Peças leves de aeromodelo que ainda precisam de alguma resistência (fuselagem/corpo). 2 walls, 7% gyroid, top/bottom 3, inner-first, seam aligned, brim 5.0. Gerado só nos layer heights que fazem sentido (**0.16, 0.20**).
- **LW-Extreme**: Peças leves ao extremo (asas). 1 wall, 3% gyroid, top/bottom 1, inner-first, seam nearest, brim 4.0. Gerado só em **0.16 e 0.20**. Usar com PLA/PETG (ou os materiais de foaming PLA-LW/PETG-LW).

Os ids dos LW são **hifenizados em inglês** (`lw-extreme`, `lw-structure`); o
build mapeia para o display `LW-Extreme`/`LW-Structure`.

### Multiplicadores por Profile Type

```
Fast:         speed=1.15x  accel=1.25x  quality_speed=0.75x
Economy:      speed=1.00x  accel=1.00x  quality_speed=0.50x  (economia via estrutura; visíveis = Standard)
Factory:      speed=0.65x  accel=0.65x  (ÓRFÃO — fora da matriz)
Standard:     speed=1.00x  accel=1.00x  quality_speed=0.50x (outer/top/1st layer/gap)
Strong:       speed=0.60x  accel=0.75x  quality_speed=0.45x  sparse=0.50x
Detail:       speed=0.80x  accel=0.75x  quality_speed=0.45x (outer/top/1st layer/gap)
Safe:         speed=0.55x  accel=0.60x  quality_speed=0.40x  sparse=0.45x
LW-Structure: speed=0.60x  accel=0.75x  quality_speed=0.50x  sparse=0.50x
LW-Extreme:   speed=0.60x  accel=0.75x  quality_speed=0.50x  sparse=0.50x
```

`sparse=` é um `field_multipliers` (campo específico em `PROFILE_MULTIPLIERS`)
que sobrescreve o multiplicador de `sparse_infill_speed`: a base de sparse
(PETG 280) é maior que a de inner (240) e o gyroid contínuo é o maior consumidor
de volume em Strong/Safe/LW. `validate.py` (`check_multiplier_math`) conhece o
`field_multipliers`.

### Extensão da recalibração aos demais tipos (profile-speed-realism)

Standard e Detail foram validados em impressão na K2 (quality_speed baixo +
`speed_scale`). A causa-raiz do **sub-extrusão no Strong PETG** (Voolt3D HF) foi
o Strong não ter recebido essa recalibração: sem `quality_speed`, outer/top
rodavam a 0.85× da base (PETG 0.20: outer 102 mm/s = 9.2 mm³/s, 1.7× o Standard)
e o estrutural ficava sustentado no teto do MVS (6 walls + 50% gyroid). Mesma
visão aplicada a Fast, Economy, Safe e LW: **nenhum tipo (exceto Fast) tem
outer/top/1ª camada mais rápidos que o Standard**, e o fluxo volumétrico ALVO
(velocidade × 0.45 × altura) respeita tetos travados em
`VolumetricFlowRealismTests`: visíveis ≤ 7.1 mm³/s (PLA) / 5.7 (PETG), Fast
≤ 10.5 / 8.5, estrutural de Strong/Safe/LW ≤ 17.5 / 14.0. Bases PLA/PETG e
`speed_scale` (0.85/0.75) **não mudaram**. O número do perfil continua sendo a
velocidade real; nenhum clamp por MVS no processo.

### Redução de velocidade por altura de camada (`speed_scale`)

Para combater **sub-extrusão** em camadas altas (relatada inclusive com PETG
premium), os layer heights acima de 0.20 aplicam um `speed_scale` por layer
height, declarado em `layer_heights/<lh>.json` e aplicado no `build.py` a **todos
os `SPEED_FIELDS` exceto `travel_speed`** (movimento sem extrusão não causa
sub-extrusão), **antes** dos caps de device/layer:

```
0.24: speed_scale=0.85
0.28: speed_scale=0.75
≤0.20: sem speed_scale (=1.0)
```

Justificado pela **altura de camada** (o fluxo volumétrico por mm cresce com a
camada: +20% a 0.24, +40% a 0.28), **nunca** pelo MVS do material — o cap
volumétrico continua exclusivo do filamento. Ex. PLA 0.24 Standard inner = 300 ×
0.85 = 255; 0.28 = 300 × 0.75 = 225; travel permanece 700 nos dois.

Todos os tipos (exceto o órfão Factory) usam multiplicadores **assimétricos**: campos que afetam
qualidade visual (outer wall, top surface, primeira camada, gap infill) recebem o
`quality_speed` mais baixo, enquanto campos internos (inner wall, infill, travel,
support) usam o `speed` regular mais alto. Isso permite imprimir rápido onde não
importa e lento apenas onde melhora a qualidade ou confiabilidade. A diferença
entre os tipos está na estrutura (walls/infill) e no fator de velocidade.

`QUALITY_SPEED_FIELDS = {outer_wall_speed, top_surface_speed, initial_layer_speed, gap_infill_speed}`.

### Limites Físicos da Máquina (caps vêm do device)

Os caps não são mais hardcoded no `build.py` — vêm do arquivo do device
(`process-base/devices/<id>.json`, chave `limits`). Ver a seção **Devices**.

- K2: extrusão 600 mm/s, travel 800 mm/s, aceleração 20000 mm/s²
- CC2: extrusão 500 mm/s, travel 500 mm/s, aceleração 20000 mm/s²

Default documentado (quando o device não declara `limits`): os valores da K2
(600/800/20000).

## Devices (Printer Targets)

O **device** é a quarta dimensão de configuração do pipeline, ao lado de
material, profile_type e layer_height. Ele encapsula tudo que é específico da
impressora: caps físicos, cadeia de herança do slicer, `compatible_printers` e
sufixo de nome. Isso permite gerar perfis para múltiplas impressoras a partir da
mesma base, sem duplicação manual.

```
device × profile_type × layer_height × material
   │          │              │            │
caps,      estrutura,     geometria,   velocidades
inherits,  multiplic.     shells,      base, temps
compat.                   adhesion
```

### Separação device / material / processo

- **Device** → o que a *impressora* permite: caps físicos (velocidade/accel),
  herança do slicer, `compatible_printers`, sufixo de nome.
- **Processo** → o que o *profile type* tenta atingir: velocidades alvo,
  acelerações, estrutura da peça.
- **Material (processo)** → velocidades base por tipo de material (alvo Standard
  na referência K2).
- **Filamento** → o que o *material físico* aguenta (`max_volumetric_speed`).

O slicer combina tudo em runtime e aplica o menor limitador. O cap volumétrico
(MVS) continua **exclusivo do filamento** — nunca entra no processo. O cap de
velocidade/aceleração é **exclusivo do device**.

### Estrutura `process-base/devices/<id>.json`

Cada device é um JSON declarativo:

```json
{
  "id": "k2",
  "display_name": "Creality K2",
  "nozzle": "0.4",
  "orca_name_suffix": "K2",
  "name_template": "{layer}mm {type} @{display_name} {nozzle} nozzle - {material}",
  "limits": { "max_extrusion_speed": 600, "max_travel_speed": 800, "max_acceleration": 20000 },
  "slicers": {
    "orca": {
      "enabled": true,
      "compatible_printers": ["Creality K2 0.4 nozzle"],
      "process_inherits_by_layer": [ { "max": 0.22, "inherits": "0.20mm Standard @Creality K2 0.4 nozzle" }, ... ]
    },
    "creality_print": { "enabled": true, "process_inherits_by_layer": [ ... ] }
  }
}
```

- `name_template` monta o nome do perfil (placeholders `{layer}`, `{type}`,
  `{display_name}`, `{nozzle}`, `{material}`).
- `process_inherits_by_layer` é uma lista `{max, inherits}`; o build escolhe a
  primeira entrada cujo `max` ≥ layer height. `inherits` aceita placeholders
  `{layer}`/`{type}`.
- `slicers.<slicer>.enabled = false` desliga a exportação daquele slicer para o
  device.

### Devices atuais

- **K2** (`k2`): CoreXY, Direct Drive, bico 0.4mm. Suportada por **Orca e
  Creality Print**. Layout de export legado (K2 na raiz de `OrcaSlicer/` e
  `Creality-Print/`).
- **CC2** (`cc2`): Elegoo Centauri Carbon 2 — CoreXY, Direct Drive, bico 0.4mm,
  volume 256³mm, Klipper. Caps 500/500/20000. **Orca-only**
  (`creality_print.enabled = false`) — o Creality Print não suporta a CC2.
  **O nome exato do perfil de máquina CC2 no OrcaSlicer alvo deve ser confirmado
  na instalação** antes de usar os perfis (alimenta `compatible_printers` e os
  `inherits`); a herança falha silenciosamente no slicer se o nome não bater.

### Combinações por device

`combinations.json` aceita `devices` por combinação e `default_devices` no topo.
Combinação sem `devices` usa `default_devices` (`["k2"]`), preservando o
comportamento anterior. O build itera `device × profile_type × layer_height ×
material` e valida que todo device referenciado tem arquivo em `devices/`
(falha explícita citando o `id` ausente).

A herança do slicer (`process_inherits_by_layer`) é **por layer height**, não
por profile type. Novos profile types (factory, lw-extreme, lw-structure) são
gerados sem nenhuma alteração no device — herdam a cadeia do layer height
correspondente automaticamente.

### Nomes de display e capitalização

Os ids de profile type são **lowercase em inglês**; os hifenizados usam hífen
(`lw-extreme`, `lw-structure`). O build gera o nome de display via
`profile_type_display()`: ids com entrada em `PROFILE_TYPE_DISPLAY`
(`lw-extreme`→`LW-Extreme`, `lw-structure`→`LW-Structure`) usam o mapa; os demais
caem na capitalização por segmento (`-`), que para ids de palavra única equivale
a `.capitalize()` (zero regressão). Isso evita o `str.capitalize()` quebrar
`lw-extreme` em `Lw-extreme`.

### Matriz completa de combinações (device k2, salvo nota)

| Profile type | Layer heights                      | Materiais        |
|--------------|------------------------------------|------------------|
| standard     | 0.12, 0.16, 0.20, 0.24, 0.28       | PLA, PETG        |
| detail       | 0.12, 0.16, 0.20                   | PLA, PETG        |
| strong       | 0.16, 0.20, 0.24, 0.28             | PLA, PETG        |
| fast         | 0.16, 0.20                         | PLA, PETG        |
| economy      | 0.20                               | PLA, PETG        |
| safe         | 0.20                               | PLA, PETG        |
| lw-structure | 0.16, 0.20                         | PLA, PETG        |
| lw-extreme   | 0.16, 0.20                         | PLA, PETG        |
| standard     | 0.20                               | TPU, ABS, PLA-CF, PLA-LW, PETG-LW |
| standard     | 0.20 (**device cc2**)              | PLA, PETG        |

Total: **47** perfis de processo. Por tipo: standard 17 (10 PLA/PETG em 5 lh +
5 especiais em 0.20 + 2 cc2); detail 6; strong 8; fast 4; economy 2; safe 2;
lw-structure 4; lw-extreme 4. `default_devices = ["k2"]`. O device cc2 é
Orca-only, então o export **Creality Print tem 45 processos** (47 − 2 cc2) e o
**Orca tem 47**.

O layer height **0.08mm foi removido da matriz** por ser inseguro/marginal em
bico de 0.4mm: fica abaixo do piso prático de ~25% do diâmetro do nozzle
(≈0.10mm), com risco de sub-extrusão/fluxo baixo e ganho de detalhe
negligenciável. Detail/Standard partem agora de 0.12mm.

`factory` foi **removido da matriz** (arquivo/multiplicador órfãos, preservados).
`PETG-CF` foi **removido da matriz de especiais** (arquivo preservado em
`materials/PETG-CF.json` e `material-data/`); os especiais agora são
{TPU, ABS, PLA-CF, PLA-LW, PETG-LW}. Economy e Safe **só em 0.20**; LW (dois
types) **só em 0.16/0.20**.

## Família de layer heights (`process-base/layer_heights/<lh>.json`)

Os cinco arquivos de layer height (0.12/0.16/0.20/0.24/0.28) formam uma
**família consistente modelada no 0.16** (referência known-good). Regras:

- **INVARIANTE (fix do bug CFS/multicolor)**: `initial_layer_print_height ==
  layer_height` em **todos** os cinco arquivos. Com a prime tower ligada
  (`enable_prime_tower=1` em `base.json`), o Creality Print **perde o
  reconhecimento de CFS/multifilamento** quando a altura da primeira camada
  difere da altura de camada. Sintoma verificado: 0.12 Detail perdia as cores,
  0.16 funcionava. **Nunca** reintroduzir primeira camada dobrada. Travado por
  `check_layer_multiple` no build.
- **Compartilhamento total**: cada `layer_heights/<lh>.json` é usado por **todos**
  os profile types (Standard/Detail/Strong/Fast/Economy/Safe/LW-*). Nunca colocar
  tuning por tipo aqui — só o que escala legitimamente com a altura de camada
  (shells, distâncias de suporte, brim, `speed_scale`).
- **Rule A — `support_interface_top_layers = 2` em toda a família** (0.12
  baixou de 3→2). Ancorado no 0.16; interface mais fácil de remover (ver
  filosofia de suporte). A facilidade de remoção vem do gap vertical
  (`support_top_z_distance`, mantido ≥ layer e monotônico), não de empilhar mais
  camadas de interface.
- **Rule B — sem overrides avulsos de velocidade nos arquivos de layer height**:
  `initial_layer_speed`, `outer_wall_speed`, `top_surface_speed` foram
  **removidos** de 0.12/0.16. Velocidade de parede/primeira camada é
  governada uniformemente por `material_base × profile_type.quality_speed`.
  Quality-first: paredes **nunca** mais rápidas do que o 0.16 de referência
  implica. (Esses campos atuavam como `min(computed, layer_value)` no `build.py`
  — nos tipos de qualidade eram valores mortos; só limitavam o Fast em 0.16.)
  Único delta visível: Fast PLA 0.16 (outer 220→225, 1ª camada 60→75) — aceitável
  para o tipo speed-first. **Fallback documentado Rule B'** (não aplicado salvo
  decisão do usuário): manter um único `outer_wall_speed=220` apenas em 0.16/0.20
  (onde Fast existe) e remover nos demais.
- **Rule C — `top/bottom_shell_thickness` por arquivo e monotônico**, não forçado
  igual ao 0.16. Progressão existente (0.12→0.84, 0.16→0.96, 0.20→0.8,
  0.24→0.96, 0.28→1.12) mantida; loose-coupled aos `shell_layers` do profile type,
  `check_shell_thickness` é MÉDIA (nunca falha o build).
- **Rule D — suporte/brim ancorados no 0.16 e monotônicos**:
  `support_top_z_distance` ≥ layer e crescente (0.22/0.24/0.25/0.27/0.30);
  `support_interface_spacing` 0.5→1.0; `support_object_xy_distance` 0.45→0.55;
  `brim_width` 9/8 (só 0.12/0.16) e `brim_object_gap` atuam como piso de
  adesão (brim maior / gap menor vence em qualquer tipo).

## Defaults de Suporte e Multifilamento

Todos os perfis de processo incluem por padrão:

- **Suportes**: Habilitados com `support_critical_regions_only = 1` (apenas regiões críticas), tree(auto), apenas na build plate. **Invariante obrigatória**: suporte apenas em regiões críticas é padrão e **nenhum perfil pode desligá-lo** — o campo vem de `base.json`, nenhum profile_type/layer_height sobrescreve, é materializado explícito em todo JSON exportado (CP e Orca) e é **travado por teste** (`tests/test_multi_device.py`) sobre todos os processos de todos os devices (k2 + cc2).
- **Distâncias de suporte otimizadas para remoção fácil** (especialmente PETG):
  - `support_top_z_distance`: 0.25mm (0.20mm layer) / 0.30mm (0.28mm layer) — gap vertical maior evita fusão com PETG
  - `support_interface_spacing`: 0.8-1.0mm — interface espaçada para menos contato
  - `support_interface_top_layers`: 2 — menos camadas de interface = descola mais fácil
  - `support_object_xy_distance`: 0.5-0.55mm — distância lateral generosa
- **Prime Tower (multifilamento)**: Habilitada com largura mínima de 35mm para reduzir desperdício.
- **Flush/Purga**: `flush_multiplier = 0.8` (reduzido do padrão 1.3), `flush_into_infill = 1`, `flush_into_support = 1` — minimiza desperdício de material em trocas de cor. **Nota de compatibilidade:** `flush_multiplier` **não** é emitido no export de PROCESSO do Creality Print (o CP rejeita a chave em processo e invalida o preset) — ver steering `slicer-compat.md`.

### Overrides de processo por material (`process_overrides`)

Os arquivos `materials/<material>.json` podem conter uma chave
`process_overrides` (dict) que sobrescreve campos de PROCESSO **após** o merge do
profile_type. Serve para ajustes de acabamento/estrutura que dependem do material
e que o valor compartilhado do profile_type não transfere bem. O build só aplica
um override **se o campo já existe no perfil** (ou seja, o recurso está ativo
para aquele profile_type) — isso evita injetar recursos em types que não os usam.

- **PETG** — ajustes conservadores onde o comportamento do PLA não transfere:
  - `ironing_flow: "10%"` (PLA usa 50%; PETG é viscoso e adere ao bico, flow alto
    arrasta/cria textura em vez de alisar).
  - (O override `zaa_enabled: "0"` foi **removido** — o ZAA deixou de existir em
    qualquer profile type, então o override virou morto. Ver a nota de ZAA na
    descrição do Detail.)
- Regra geral: **PLA é o perfil de referência/agressivo; PETG recebe o ajuste
  conservador onde há incerteza.** Novos ajustes material-específicos entram via
  `process_overrides`, não duplicando profile_types.

### Materialização explícita do bloco CFS (fix de multifilamento)

**Causa-raiz do bug relatado** (perfis como Detail não reconhecidos como
multifilamento no Creality Print, enquanto Standard funcionava): os campos de
CFS que o slicer precisa — em especial `wiping_volumes_extruders` (matriz de
purga por tool) e `single_extruder_multi_material_priming` — chegavam ao perfil
**só por herança** do preset de sistema nomeado em `inherits`. Quando a
resolução de herança no runtime do CP falhava (preset de sistema editado/ausente,
divergência de nome após atualização do slicer, ordem de carga), o perfil ficava
sem a matriz de purga e o CFS deixava de ser reconhecido. Detail era o mais
exposto (o mais fino, presente em 0.12, e o que mais diverge do preset de sistema).

**Fix**: materializar os **9 campos de CFS** explicitamente em `base.json` (logo,
no merge → banco → export de TODO perfil), sem depender de herança:
`single_extruder_multi_material_priming`, `wiping_volumes_extruders`,
`wipe_tower_bridging`, `wipe_tower_cone_angle`, `wipe_tower_extra_spacing`,
`wipe_tower_no_sparse_layers`, `wipe_tower_rotation_angle`,
`prime_tower_enhance_type`, `ooze_prevention` (valores do preset de sistema da
K2). `support_filament`/`support_interface_filament` **não** são materializados
(são atribuição de tool por objeto, resolvida no slice — fixá-los em "0" quebra o
fluxo multi-material). O pipeline ganhou 9 colunas TEXT (sem DEFAULT) em
`process_profiles` + entradas no export CP (`field_map`) e Orca (`set_val`).
Invariante travada por teste: o conjunto estendido (8 prime-tower/flush + 9 CFS)
é idêntico entre todos os profile types em 0.20.

**Cadeia de `inherits` NÃO alterada**: os presets de sistema alvo
(`<lh>mm Standard @Creality K2 0.4 nozzle`) existem no CP em todos os layer
heights (verificado); a cadeia resolve corretamente e permanece como camada
secundária. A materialização explícita torna o perfil robusto mesmo se a herança
falhar. **Não reproduzível fora do slicer**: o reconhecimento real do CFS só se
confirma abrindo o Creality Print (o fix remove a dependência estrutural da
herança, que é a causa-raiz verificável a nível de campo).

**Nota sobre PETG e suportes**: PETG tem alta adesão entre camadas — os valores de distância de suporte são calibrados para que o suporte não funda com a peça, priorizando remoção limpa sobre acabamento da superfície suportada.

## Materiais — Velocidades Base (process-base/materials/)

Os arquivos de material definem velocidades base que representam o alvo **Standard** para aquele tipo de material na K2. Referência: perfis do Orca Slicer para K2 0.4mm.

O `speed_multiplier` no material é 1.0 por padrão — a diferença entre materiais já está encodada nas velocidades base. Isso evita dupla penalização.

As bases de PLA e PETG foram recalibradas para serem conservadoras (ver
**Recalibração: qualidade antes de velocidade**). O número do perfil é a
velocidade real — não se infla a base contando com o cap do slicer.

| Material | speed_mult | accel_mult | default_accel | inner_wall base | Racional |
|----------|-----------|-----------|---------------|-----------------|----------|
| PLA      | 1.00      | 1.00      | 18000         | 300             | Recalibrado conservador — filamento limita via MVS |
| PETG     | 1.00      | 1.00      | 15000         | 240             | Recalibrado conservador por cooling/stringing |
| ABS      | 1.00      | 1.00      | 12000         | 300             | Menor por warping — sem dupla penalização |
| PLA-CF   | 1.00      | 1.00      | 10000         | 280             | Rigidez da fibra + desgaste do nozzle |
| PETG-CF  | 1.00      | 1.00      | 9000          | 240             | Fibra + PETG — material mais difícil (fora da matriz) |
| TPU      | 1.00      | 1.00      | 4000          | 120             | Flexível — Direct Drive ajuda, mas tem limites |
| PLA-LW   | 1.00      | 1.00      | 5000          | 70              | Foaming: velocidade baixa para dar tempo de expandir |
| PETG-LW  | 1.00      | 1.00      | 4000          | 60              | Foaming + stringing do PETG — ainda mais lento |

**Materiais de processo LW (foaming)**: `PLA-LW.json`/`PETG-LW.json` definem
apenas velocidades/acelerações conservadoras (bem abaixo do PLA/PETG regular,
para dar tempo de o material expandir e evitar stringing). A **redução de flow
(~0.55) e a temperatura alta de foaming vivem no perfil de FILAMENTO**, não no de
processo. Só geram processo em 0.20mm Standard (ver restrições). Registrados em
`build.py` (`process_materials`) e em `material-data/materials.yaml`.

## Restrições de Materiais Especiais

- **ABS, TPU, PLA-CF, PLA-LW, PETG-LW**: Apenas em **0.20mm Standard**. Não gerar outros layer heights ou profile types para esses materiais. (`PETG-CF` foi removido da matriz de especiais no overhaul de perfis — arquivo preservado, mas não gera processo.)
- **PLA e PETG**: Disponíveis em todos os profile types e layer heights definidos no combinations.json.

## Produtos para Exportação

A exportação para os slicers é **curada por produto**, não por fabricante. Cada
perfil de filamento decide se é exportado via a flag `export: true` no YAML
(propagada para a coluna `export_enabled` no banco pelo build). Isso mantém a
curadoria junto da fonte de verdade e evita listas paralelas hardcoded.

Produtos atualmente habilitados para exportação (curadoria deliberada, baseada
no estoque físico real — **22 produtos**; contagem validada contra as flags
`export: true` dos YAMLs).

**Decisão (2026-11-06): Sunlu é a marca primária.** Após os problemas com a
Voolt3D (MVS sem embasamento, sub-extrusão), o usuário passou a tratar a Sunlu
como marca principal. Os 4 produtos Sunlu (PLA High Speed, PLA High Speed Matte,
PLA Matte, PETG HS) ficam exportados — o `Sunlu PLA High Speed Matte` foi
confirmado explicitamente. Os produtos Voolt3D seguem exportados por enquanto,
mas com MVS conservador. Ao escolher filamento de referência/default ou ao
priorizar calibração, preferir Sunlu.

| Produto | Material | YAML |
|---------|----------|------|
| Voolt3D PLA Velvet | PLA | voolt3d |
| Voolt3D PLA High Speed | PLA | voolt3d |
| Voolt3D PLA Macaron | PLA | voolt3d |
| Voolt3D PLA V-Silk | PLA | voolt3d |
| Voolt3D PLA Premium Outlet | PLA | voolt3d |
| Voolt3D PLA EVO | PLA | voolt3d |
| Voolt3D PLA CF | PLA-CF | voolt3d |
| Voolt3D PETG HF | PETG | voolt3d |
| Voolt3D PETG Outlet | PETG | voolt3d |
| Voolt3D ABS | ABS | voolt3d |
| Voolt3D TPU | TPU | voolt3d |
| Sunlu PLA High Speed | PLA | sunlu |
| Sunlu PLA High Speed Matte | PLA | sunlu |
| Sunlu PLA Matte | PLA | sunlu |
| Sunlu PETG HS (High Speed Matte) | PETG | sunlu |
| Creality Hyper PLA | PLA | creality |
| Creality CR PETG | PETG | creality |
| Creality Hyper PETG | PETG | creality |
| Elegoo PLA+ | PLA | elegoo |
| Elegoo PLA Pro | PLA | elegoo |
| Soleyin Ultra PLA | PLA | soleyin |
| Futer3D PETG Basic | PETG | futer3d |

### MVS dos produtos exportados (auditoria profile-speed-realism)

| Produto | MVS | Racional |
|---------|-----|----------|
| Voolt3D PETG HF | 11 | Ancorado no CR PETG (11), intermediário abaixo do teto. Ver revisão nov/2026 abaixo |
| Voolt3D PETG Outlet | 10 | Carretéis outlet variam por lote; mantido conservador (sem fonte p/ subir) |
| Voolt3D TPU | 4 | Orca TPU 3.2; sem TDS. Flexível — subir é arriscado; mantido |
| Sunlu PETG HS | 12 (era 18) | Sem MVS declarado (só 600 mm/s de marketing) |
| Creality CR PETG | 11 (era 15) | Sem fonte; classe PETG 10-12 |
| Creality Hyper PETG | 14 (era 18) | Perfil de fábrica da K2; sem fonte para 18 |
| Elegoo PLA Pro | 14 (era 16) | Sem fonte; nozzle initial 200 °C |
| Sunlu PLA High Speed | 22 (inalterado) | TDS; filamento premium validado pelo usuário |
| Creality Hyper PLA 20, Soleyin 8 | inalterados | Dentro da classe |

### Revisão de MVS Voolt3D — intermediário, ancorado na linha CR (nov/2026)

Filosofia final (decisão do usuário): 10 era conservador demais, mas **não colar
nos tetos** — usar valores **intermediários**, e tomar os filamentos de **entrada
da Creality (linha CR)** como REFERÊNCIA onde o material é similar. Não penalizar
todos os produtos por algo que pode ser ajuste mecânico (grip DXC2) ou umidade.

**Referência Creality (entrada), no nosso banco:** CR PLA 12 / Ender PLA 12;
CR PETG 11; Creality ABS 12; Creality ASA 12; Creality TPU 4. (Hyper PLA 20 e
Hyper PETG 14 são linhas premium/fábrica, não "entrada".)

**Sobre o teto PETG ≤ 12:** não é spec do polímero (MVS depende de hotend +
temp + material). É trava NOSSA, baseada na faixa física confiável de PETG num
hotend padrão de K2 (~10-14 mm³/s) + a política do menor valor. Com o critério
intermediário, o PETG Voolt fica ABAIXO do teto (ancorado no CR PETG 11).

| Produto | Material | MVS final | Racional (âncora CR / intermediário) |
|---------|----------|-----------|--------------------------------------|
| Voolt3D PLA High Speed    | PLA    | **16** | Linha high-speed real; único com argumento p/ valor alto (folga classe 18) |
| Voolt3D PLA V-Silk        | PLA    | **12** | = CR PLA entrada (12); intermediário |
| Voolt3D PLA Macaron       | PLA    | **12** | = CR PLA entrada (12) |
| Voolt3D PLA Premium Outlet | PLA   | 15 → **14** | Intermediário; acima do CR 12, sem colar no pico |
| Voolt3D PLA EVO           | PLA    | 15 → **14** | Idem |
| Voolt3D PLA Standard (export false) | PLA | 15 → **14** | Idem; referência |
| Voolt3D PETG HF           | PETG   | 12 → **11** | = CR PETG (11); intermediário, abaixo do teto 12 |
| Voolt3D PETG Outlet       | PETG   | **10** | Outlet varia por lote; conservador abaixo do CR |
| Voolt3D PETG CF (export false) | PETG | 10 → **11** | Faixa intermediária p/ CF (pedido do usuário); < teto 12 |
| Voolt3D ABS               | ABS    | 10 → **11** | Faixa intermediária p/ ABS; entre 10 e o CR ABS (12) |
| Voolt3D PLA-CF (export false) | PLA-CF | 10 → **11** | Faixa intermediária p/ CF; < teto 12 |
| **Voolt3D PLA Velvet**    | PLA    | **8 (MANTIDO)** | Sub-extrusão é MECÂNICA (grip DXC2 — teste dos 100 mm falha no Velvet, passa no Sunlu), não MVS. Não penalizar via config |
| Voolt3D TPU               | TPU    | **4 (MANTIDO)** | = CR TPU (4); flexível, subir é arriscado |

Princípio: ancorar no CR de entrada por similaridade de material, ficar em faixas
intermediárias (não nos tetos), e só usar valor alto onde há argumento real
(PLA High Speed). ABS/TPU/CF explicitamente em faixa intermediária a pedido do
usuário. Cada valor tem comentário `# MVS ...` no YAML.

Cada YAML alterado traz um comentário `# MVS A -> B: <fonte/justificativa>` acima do valor.

Nota: a restrição de materiais especiais (PLA-CF/ABS/TPU só geram **processo**
em 0.20mm Standard) aplica-se ao processo; não impede a exportação do
**filamento** (Voolt3D PLA CF, ABS e TPU são exportados como filamento).

**Soleyin** é sub-marca da Creality; o produto **Soleyin Ultra PLA** (linha Ultra,
compatível com CFS) é um dos produtos exportados (`filament-data/soleyin.yaml`,
`export: true`). Perfis de filamento **LW/foaming** foram adicionados a
eSUN (ePLA-LW), Sunlu (PLA Lightweight) e Prusament (PLA Lightweight / PolyLight)
mapeados para o material `PLA-LW`, todos `export: false` (ficam no banco para
referência, não vão para os slicers).

Todos os demais perfis (mesmo dos fabricantes acima) ficam no banco
(filament-data/) para referência, comparação e price tracking, mas **não** são
exportados para Creality-Print/ nem OrcaSlicer/.

Para habilitar/desabilitar um produto: adicione ou remova `export: true` no
profile correspondente em `filament-data/*.yaml` e rode o build. O override
`EXPORT_OVERRIDE=__ALL__` (variável de ambiente) força a exportação de todos os
perfis ativos, ignorando a flag — útil para inspeção pontual.

## Publicação Local

Destino: `~/filament-db/` com subpastas por slicer:

```
~/filament-db/
├── creality-print/
│   ├── filament/   ← .json + .info
│   └── process/    ← apenas .json
├── orca/
│   ├── filament/   ← .json (K2 — layout legado na raiz)
│   ├── process/    ← .json (K2 — layout legado na raiz)
│   └── cc2/        ← devices adicionais em subpasta por id
│       ├── filament/
│       └── process/
├── backups/        ← zips com timestamp (últimos 10)
└── diff/           ← perfis órfãos arquivados pelos scripts de inicialização
```

O `publish.sh` faz backup automático antes de sobrescrever: gera um zip com todos os perfis atuais (ambos slicers, filamentos + processos) em `~/filament-db/backups/profiles_YYYYMMDD_HHMMSS.zip`, mantendo os últimos 10 backups.

O `publish.sh` executa o pipeline local: build → backup → publish para ~/filament-db/.

Ao publicar para a pasta local, copiar apenas os perfis filtrados (fabricantes habilitados, combinações válidas).

## Instalação e Atualização dos Slicers (`install-slicers.sh` / `update-slicers.sh`)

Dois scripts versionados mantêm os slicers (Creality Print e OrcaSlicer) sempre
atualizados, sem intervenção manual. Compartilham a biblioteca `lib-slicers.sh`.

**Fonte: GitHub Releases oficiais** (URLs determinísticas e versionadas, o mesmo
binário do site oficial):
- Creality Print: `CrealityOfficial/CrealityPrint` — asset
  `CrealityPrint-V<ver>.<build>-x86_64-Release.AppImage`. A tag pode ter vários
  builds; o script escolhe o maior por `sort -V`.
- Orca Slicer: `SoftFever/OrcaSlicer` — asset
  `OrcaSlicer_Linux_AppImage_Ubuntu2404_V<ver>.AppImage` (exclui `aarch64`).

O site `creality.com/download` é dinâmico (sem URL estável) e **não** é usado —
não é automatizável de forma robusta. O GitHub oficial serve o mesmo AppImage.

**Layout de instalação** (sem sudo, sobrescrevível por env `SLICER_APPS_DIR` /
`SLICER_BIN_DIR`):
- AppImages em `~/Applications/` (versão anterior arquivada em `~/Applications/old/`).
- Symlinks estáveis no PATH: `~/.local/bin/creality-print` e
  `~/.local/bin/orca-slicer` → apontam para o AppImage da versão corrente.

**`install-slicers.sh`** — baixa e instala a versão mais recente dos dois numa
máquina nova. Idempotente: pula se já na latest (`--force` reinstala). Flags:
`--only creality|orca`, `--force`, `--dry-run`, `--no-structure`. Ao final chama
`install.sh --force` para criar a árvore e regenerar os runners.

**`update-slicers.sh`** — compara a versão instalada (lida do AppImage apontado
pelo symlink) com a latest e atualiza **só se houver versão nova**. A versão
anterior vai para `~/Applications/old/`. Flags: `--check` (só reporta, não
escreve), `--dry-run`, `--only`, `--no-structure`. Após atualizar, regenera os
runners via `install.sh`.

**Detecção da versão instalada (`lib_installed_version`)**: lê a versão do nome
do AppImage apontado pelo symlink; no fallback, varre `~/Applications`,
`~/Applications/old`, `~/orca`, `~/Downloads`, `/opt`. Isso detecta o **layout
legado** do Orca (`~/orca/*.AppImage`). O Creality legado (ELF em
`/usr/local/bin/creality-print`, sem versão no nome) aparece como `<nenhuma>` —
na primeira atualização ele é **migrado** para o AppImage versionado em
`~/.local/bin` (comportamento intencional de migração, não bug).

**Fluxo numa máquina nova**: `./install-slicers.sh` → `./publish.sh` →
`~/run-<slicer>.sh`. Para manter atualizado depois: `./update-slicers.sh` (ou
`--check` para só verificar).

## Estrutura Local (`install.sh`)

`install.sh` (na raiz do repo, **versionado**) faz o bootstrap da árvore
`~/filament-db/` e gera os inicializadores. É a **fonte de verdade** da lógica
dos inicializadores: os `~/run-<slicer>.sh` passam a ser **artefatos gerados**
por ele, não arquivos mantidos à mão. Chamado automaticamente por
`install-slicers.sh` e `update-slicers.sh`, mas também roda sozinho.

O que faz, de forma idempotente:

1. **Detecta os slicers** instalados (não-fatal se faltar um):
   - Creality Print: binário via `command -v creality-print` + candidatos
     (`/usr/local/bin`, `/usr/bin`, `/opt/...`).
   - Orca Slicer: AppImage via glob (`~/orca`, `~/Applications`, `~/.local/bin`,
     `~/Downloads`, `/opt`), escolhendo o mais novo por `sort -V` sobre a versão
     no nome; fallback para binário no PATH.
2. **Cria a árvore** `~/filament-db/{creality-print/{filament,process},orca/{filament,process},backups,diff}`.
   As subpastas de device do Orca (`orca/cc2/`, ...) são criadas pelo `publish.sh`,
   não pelo instalador.
3. **Gera os inicializadores** `~/run-creality-print.sh` e `~/run-orca-slicer.sh`
   via heredoc, injetando o caminho **resolvido** de cada executável (binário do
   Creality e AppImage do Orca) — o `exec` final não depende do PATH. A lógica de
   detecção dinâmica (versão/user do Creality, agregação K2+devices do Orca) vive
   embutida nos runners gerados.

Flags: `--dry-run` (mostra sem escrever), `--force` (sobrescreve runners sem
backup), `--help`. Var de ambiente: `FILAMENT_DB_ROOT` (default `~/filament-db`).

Comportamento seguro: faz backup do runner antigo (`.bak.YYYYMMDD_HHMMSS`) antes
de sobrescrever (salvo `--force`); gera apenas o runner do slicer detectado e
avisa sobre o ausente; falha explícita só se **nenhum** slicer for encontrado.

Fluxo típico: `install.sh` é chamado automaticamente pelos scripts de slicer.
Para só (re)gerar a estrutura/runners sem mexer nos binários: `./install.sh`.

## Inicialização dos Slicers

Cada slicer tem um script em `~/run-<slicer>.sh` (gerado pelo `install.sh`) que
sincroniza perfis de `~/filament-db/<slicer>/` para o diretório do usuário do
slicer, arquiva perfis órfãos em `~/filament-db/diff/` e abre o aplicativo. Ambos
os scripts **detectam o destino dinamicamente** — nada de caminhos hardcoded que
quebram a cada atualização do slicer.

### Creality Print

- Script: `~/run-creality-print.sh`
- Origem: `~/filament-db/creality-print/{filament,process}` (fonte única)
- Destino: **todos** os `~/.config/Creality/Creality Print/<versão>/user/<conta>/{filament,process}`
- **Sync em TODAS as versões × TODAS as contas reais**: o script enumera **todas** as versões `X.Y` instaladas (não só a mais recente) e, dentro de cada uma, **todas** as contas reais — ids numéricos **e** `default`. Evita perfil "lixo" preso numa versão antiga ou numa conta que não é a corrente.
- **Regra de conta real (pula scratch)**: um subdir de `<versão>/user/` é alvo **se já tiver um subdir `filament/` OU `process/`**. Isso casa com o que o slicer provisiona por conta real, pula dirs de scratch como `Temp` (só `AIRecommendation`/`sync_data.json`) e arquivos soltos (`hints.cereal`), e nunca cria pasta de perfil onde o slicer não criou.
- **Espelho exato por alvo**: para cada `(versão, conta)` o script arquiva órfãos **POR ALVO** (um perfil no destino que não exista na fonte vai para `~/filament-db/diff/` com sufixo de data), apaga o destino e recopia da fonte. Cada alvo vira um espelho **exato** de `~/filament-db/creality-print/{filament,process}`. O arquivamento de órfãos é sempre por `(versão, conta)` — **nunca** global.
- **Erro só se não houver nenhum alvo**: falha explícita (exit 1) se a base do CP não existir, se a fonte não existir, se **nenhuma** versão `X.Y` for encontrada ou se **nenhum** alvo `(versão, conta)` qualificar. Uma versão sem contas reais é **aviso** (continua), não fatal.
- Loga cada alvo sincronizado: `Alvo: versão <v>, user <conta>` + contagens de filamentos/processos, e no fim o total de alvos sincronizados.
- `filament/` — recebe .json + .info
- `process/` — recebe apenas .json

### Orca Slicer

- Script: `~/run-orca-slicer.sh`
- Origem: `~/filament-db/orca/{filament,process}` (K2, layout legado na raiz) **+** `~/filament-db/orca/<device>/{filament,process}` (devices adicionais, ex.: `cc2`)
- Destino: `~/.config/OrcaSlicer/user/default/{filament,process}` (único, achatado)
- Ambos recebem apenas .json
- **Sync agregado K2 + devices**: o Orca guarda todos os perfis achatados em um único diretório de usuário — ele distingue os perfis pelo nome (sufixo `@<device>`, ex.: `@CC2`) e pelo `compatible_printers`, não por subpasta. O script agrega a raiz (K2) e todas as subpastas de device (`orca/*/{filament,process}`) e copia tudo para o destino único.
- **Arquivamento de órfãos ciente de todas as fontes**: um perfil no destino só é arquivado em `diff/` se não existir em **nenhuma** fonte (raiz nem devices). Isso evita arquivar perfis de device válidos (`@CC2`) a cada execução.
- O destino do Orca não é versionado por pasta como o Creality — não precisa de detecção de versão.
- **Conta única por design**: o Orca usa um único diretório de usuário achatado (`user/default`), sem árvore versionada por conta como o CP. Por isso **não há** enumeração multi-conta no runner do Orca (ao contrário do CP) — o alvo é sempre `user/default`.

## Estrutura de Dados

- `filament-data/*.yaml` — fonte de verdade para filamentos (inclui `max_volumetric_speed` por perfil)
- `process-base/` — sistema de herança para perfis de processo
- `process-base/devices/` — definição de cada impressora (caps, herança do
  slicer, `compatible_printers`, sufixo de nome). Ver seção **Devices**.
- `process-base/materials/` — velocidades base por tipo de material (sem MVS)
- `process-base/profile_types/` — parâmetros estruturais por profile type
- `process-base/layer_heights/` — overrides por layer height
- `process-base/combinations.json` — define quais combinações são geradas (por device)
- `build.py` — pipeline que gera banco SQLite + exporta para Creality-Print/
- `Creality-Print/` — output final para importar no slicer
- `publish.sh` — build + copia para ~/filament-db/
