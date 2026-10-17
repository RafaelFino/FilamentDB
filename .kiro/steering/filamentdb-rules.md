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

Isso garante que filamentos premium (Voolt3D Velvet MVS=25, Sunlu HS MVS=22) aproveitam o máximo da K2, enquanto filamentos mais limitados (Silk MVS=12, PETG genérico MVS=12) são automaticamente contidos sem penalizar os demais.

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
Fast → Economy → Factory → Standard → Strong → Detail → Safe
                              ├── LW-Structure (aeromodelo: fuselagem/corpo)
                              └── LW-Extreme   (aeromodelo: asas)
```

- **Fast**: Velocidade máxima. O mais rápido possível — aceita redução de qualidade em troca de tempo. 3 walls, 12% infill grid, inner-first.
- **Economy**: Economia de filamento. Estrutura mínima viável — 2 walls, 8% grid, inner-first. Velocidade igual Standard — a economia vem da estrutura reduzida, não da velocidade. Ideal para protótipos descartáveis e peças não-estruturais.
- **Factory**: Perfil de fábrica conservador — espelha a estrutura do Standard (4 walls, 15% gyroid, outer-first, top 5/bottom 4) mas com velocidade reduzida (0.65x) e **BRIM sempre ligado** (`brim_width` 5.0, `brim_object_gap` 0.15). Suportes herdados da base (ligados, apenas regiões críticas). Variações apenas PLA/PETG.
- **Standard**: Equilíbrio geral, padrão de uso diário. 4 walls, 15% gyroid, outer-first, bom acabamento. Usa `quality_speed` 0.6 nos campos visíveis (outer/top/1ª camada). Nome obrigatório — Creality Print requer um perfil "Standard" para iniciar.
- **Strong**: Resistência mecânica (6 walls, 50% infill gyroid). Mais lento, peças funcionais.
- **Detail**: Qualidade visual máxima. Layer heights baixos (0.08-0.16mm), 5 walls, 20% infill. `quality_speed` 0.45.
- **Safe**: Ultra-conservador para primeira impressão ou materiais desconhecidos. Lento mas confiável.
- **LW-Structure**: Peças leves de aeromodelo que ainda precisam de alguma resistência (fuselagem/corpo). 2 walls, 7% gyroid, top/bottom 3, inner-first, seam aligned, brim 5.0. Gerado só nos layer heights que fazem sentido (0.16, 0.20).
- **LW-Extreme**: Peças leves ao extremo (asas). 1 wall, 3% gyroid, top/bottom 1, inner-first, seam nearest, brim 4.0. Gerado só em 0.20 e 0.24. Usar com PETG ou PLA (material LW ainda a definir).

Os ids dos LW são **hifenizados em inglês** (`lw-extreme`, `lw-structure`); o
build mapeia para o display `LW-Extreme`/`LW-Structure`.

### Multiplicadores por Profile Type

```
Fast:         speed=1.50x  accel=1.50x
Economy:      speed=1.00x  accel=1.00x  (economia via estrutura, não velocidade)
Factory:      speed=0.65x  accel=0.65x
Standard:     speed=1.00x  accel=1.00x  quality_speed=0.60x (outer/top/1st layer/gap)
Strong:       speed=0.85x  accel=0.80x
Detail:       speed=0.80x  accel=0.75x  quality_speed=0.45x (outer/top/1st layer/gap)
Safe:         speed=0.70x  accel=0.60x  quality_speed=0.50x (outer/top/1st layer/gap)
LW-Structure: speed=0.90x  accel=0.85x
LW-Extreme:   speed=0.90x  accel=0.85x
```

Standard, Detail e Safe usam multiplicadores **assimétricos**: campos que afetam
qualidade visual (outer wall, top surface, primeira camada, gap infill) recebem o
`quality_speed` mais baixo, enquanto campos internos (inner wall, infill, travel,
support) usam o `speed` regular mais alto. Isso permite imprimir rápido onde não
importa e lento apenas onde melhora a qualidade ou confiabilidade. Os LW não usam
`quality_speed` — a diferença entre eles está na estrutura (walls/infill), não na
velocidade.

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
| fast         | 0.12, 0.16, 0.20, 0.24, 0.28       | PLA, PETG        |
| economy      | 0.12, 0.16, 0.20, 0.24, 0.28       | PLA, PETG        |
| standard     | 0.12, 0.16, 0.20, 0.24, 0.28       | PLA, PETG        |
| strong       | 0.12, 0.16, 0.20, 0.24, 0.28       | PLA, PETG        |
| safe         | 0.12, 0.16, 0.20, 0.24, 0.28       | PLA, PETG        |
| factory      | 0.12, 0.16, 0.20, 0.24, 0.28       | PLA, PETG        |
| detail       | 0.08, 0.12, 0.16, 0.20, 0.24, 0.28 | PLA, PETG        |
| lw-extreme   | 0.20, 0.24                         | PLA, PETG        |
| lw-structure | 0.16, 0.20                         | PLA, PETG        |
| standard     | 0.20                               | TPU, ABS, PLA-CF, PETG-CF |
| standard     | 0.20 (**device cc2**)              | PLA, PETG        |

Total: **86** perfis de processo. Por tipo: detail 12; fast/economy/strong/
safe/factory 10 cada; standard 16 (10 PLA/PETG + 4 especiais + 2 cc2);
lw-extreme 4; lw-structure 4. `default_devices = ["k2"]`. O device cc2 é
Orca-only, então o export Creality Print tem 84 processos (86 − 2 cc2) e o Orca
tem 86.

## Defaults de Suporte e Multifilamento

Todos os perfis de processo incluem por padrão:

- **Suportes**: Habilitados com `support_critical_regions_only = 1` (apenas regiões críticas), tree(auto), apenas na build plate.
- **Distâncias de suporte otimizadas para remoção fácil** (especialmente PETG):
  - `support_top_z_distance`: 0.25mm (0.20mm layer) / 0.30mm (0.28mm layer) — gap vertical maior evita fusão com PETG
  - `support_interface_spacing`: 0.8-1.0mm — interface espaçada para menos contato
  - `support_interface_top_layers`: 2 — menos camadas de interface = descola mais fácil
  - `support_object_xy_distance`: 0.5-0.55mm — distância lateral generosa
- **Prime Tower (multifilamento)**: Habilitada com largura mínima de 35mm para reduzir desperdício.
- **Flush/Purga**: `flush_multiplier = 0.8` (reduzido do padrão 1.3), `flush_into_infill = 1`, `flush_into_support = 1` — minimiza desperdício de material em trocas de cor.

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
| PETG-CF  | 1.00      | 1.00      | 9000          | 240             | Fibra + PETG — material mais difícil |
| TPU      | 1.00      | 1.00      | 4000          | 120             | Flexível — Direct Drive ajuda, mas tem limites |

## Restrições de Materiais Especiais

- **ABS, TPU, PLA-CF, PETG-CF**: Apenas em **0.20mm Standard**. Não gerar outros layer heights ou profile types para esses materiais.
- **PLA e PETG**: Disponíveis em todos os profile types e layer heights definidos no combinations.json.

## Produtos para Exportação

A exportação para os slicers é **curada por produto**, não por fabricante. Cada
perfil de filamento decide se é exportado via a flag `export: true` no YAML
(propagada para a coluna `export_enabled` no banco pelo build). Isso mantém a
curadoria junto da fonte de verdade e evita listas paralelas hardcoded.

Produtos atualmente habilitados para exportação (curadoria deliberada, baseada
no estoque físico real — 18 produtos):

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
| Voolt3D ABS | ABS | voolt3d |
| Voolt3D TPU | TPU | voolt3d |
| Sunlu PLA High Speed | PLA | sunlu |
| Sunlu PLA Matte | PLA | sunlu |
| Sunlu PETG HS (High Speed Matte) | PETG | sunlu |
| Creality Hyper PLA | PLA | creality |
| Creality CR PETG | PETG | creality |
| Creality Hyper PETG | PETG | creality |
| Elegoo PLA+ | PLA | elegoo |
| Elegoo PLA Pro | PLA | elegoo |

Nota: a restrição de materiais especiais (PLA-CF/ABS/TPU só geram **processo**
em 0.20mm Standard) aplica-se ao processo; não impede a exportação do
**filamento** (Voolt3D PLA CF, ABS e TPU são exportados como filamento).

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

## Inicialização dos Slicers

Cada slicer tem um script em `~/run-<slicer>.sh` que sincroniza perfis de `~/filament-db/<slicer>/` para o diretório do usuário do slicer, arquiva perfis órfãos em `~/filament-db/diff/` e abre o aplicativo. Ambos os scripts **detectam o destino dinamicamente** — nada de caminhos hardcoded que quebram a cada atualização do slicer.

### Creality Print

- Script: `~/run-creality-print.sh`
- Origem: `~/filament-db/creality-print/{filament,process}`
- Destino: `~/.config/Creality/Creality Print/<versão>/user/<user_id>/{filament,process}`
- **Detecção de versão**: o script lista os diretórios `X.Y` em `~/.config/Creality/Creality Print/` e escolhe o maior via `sort -V`. Segue automaticamente futuras atualizações do slicer (ex.: 7.0 → 7.3) sem edição manual.
- **Detecção do user id**: pega o diretório numérico em `<versão>/user/`; se houver mais de um, usa o modificado mais recentemente. Nada de hardcode da conta.
- Falha explícita (mensagem clara, exit 1) se não encontrar a base, nenhuma versão `X.Y` ou nenhum user id.
- Loga o alvo escolhido no início: `Creality Print alvo: versão <v>, user <id>`.
- `filament/` — recebe .json + .info
- `process/` — recebe apenas .json
- Versões antigas do slicer (ex.: 7.0 após migrar para 7.3) ficam intocadas — o script só mira a versão corrente.

### Orca Slicer

- Script: `~/run-orca-slicer.sh`
- Origem: `~/filament-db/orca/{filament,process}` (K2, layout legado na raiz) **+** `~/filament-db/orca/<device>/{filament,process}` (devices adicionais, ex.: `cc2`)
- Destino: `~/.config/OrcaSlicer/user/default/{filament,process}` (único, achatado)
- Ambos recebem apenas .json
- **Sync agregado K2 + devices**: o Orca guarda todos os perfis achatados em um único diretório de usuário — ele distingue os perfis pelo nome (sufixo `@<device>`, ex.: `@CC2`) e pelo `compatible_printers`, não por subpasta. O script agrega a raiz (K2) e todas as subpastas de device (`orca/*/{filament,process}`) e copia tudo para o destino único.
- **Arquivamento de órfãos ciente de todas as fontes**: um perfil no destino só é arquivado em `diff/` se não existir em **nenhuma** fonte (raiz nem devices). Isso evita arquivar perfis de device válidos (`@CC2`) a cada execução.
- O destino do Orca não é versionado por pasta como o Creality — não precisa de detecção de versão.

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
