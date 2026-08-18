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

## Hierarquia de Perfis de Processo

Do mais rápido ao mais caprichado:

```
Fast → Economy → Standard → Strong → Detail → Safe
```

- **Fast**: Velocidade máxima. O mais rápido possível — aceita redução de qualidade em troca de tempo. 3 walls, 12% infill grid, inner-first.
- **Economy**: Economia de filamento. Estrutura mínima viável — 2 walls, 8% grid, inner-first. Velocidade igual Standard — a economia vem da estrutura reduzida, não da velocidade. Ideal para protótipos descartáveis e peças não-estruturais.
- **Standard**: Equilíbrio geral, padrão de uso diário. 4 walls, 15% gyroid, outer-first, bom acabamento. Nome obrigatório — Creality Print requer um perfil "Standard" para iniciar.
- **Strong**: Resistência mecânica (6 walls, 50% infill gyroid). Mais lento, peças funcionais.
- **Detail**: Qualidade visual máxima. Layer heights baixos (0.08-0.16mm), 5 walls, 20% infill.
- **Safe**: Ultra-conservador para primeira impressão ou materiais desconhecidos. Lento mas confiável.

### Multiplicadores por Profile Type

```
Fast:     speed=1.50x  accel=1.50x
Economy:  speed=1.00x  accel=1.00x  (economia via estrutura, não velocidade)
Standard: speed=1.00x  accel=1.00x
Strong:   speed=0.85x  accel=0.80x
Detail:   speed=0.80x  accel=0.75x  quality_speed=0.45x (outer/top/1st layer)
Safe:     speed=0.70x  accel=0.60x  quality_speed=0.50x (outer/top/1st layer)
```

Os perfis Detail e Safe usam multiplicadores **assimétricos**: campos que afetam qualidade visual (outer wall, top surface, primeira camada) recebem o `quality_speed` mais baixo, enquanto campos internos (inner wall, infill, travel, support) usam o `speed` regular mais alto. Isso permite imprimir rápido onde não importa e lento apenas onde melhora a qualidade ou confiabilidade.

### Limites Físicos da Máquina (caps no build.py)

- Velocidade de extrusão: 600 mm/s (spec K2)
- Travel: 800 mm/s
- Aceleração: 20000 mm/s²

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

| Material | speed_mult | accel_mult | default_accel | inner_wall base | Racional |
|----------|-----------|-----------|---------------|-----------------|----------|
| PLA      | 1.00      | 1.00      | 18000         | 450             | K2 max — filamento limita via MVS |
| PETG     | 1.00      | 1.00      | 15000         | 380             | Levemente conservador por cooling/stringing |
| ABS      | 1.00      | 1.00      | 12000         | 300             | Menor por warping — sem dupla penalização |
| PLA-CF   | 1.00      | 1.00      | 10000         | 280             | Rigidez da fibra + desgaste do nozzle |
| PETG-CF  | 1.00      | 1.00      | 9000          | 240             | Fibra + PETG — material mais difícil |
| TPU      | 1.00      | 1.00      | 4000          | 120             | Flexível — Direct Drive ajuda, mas tem limites |

## Restrições de Materiais Especiais

- **ABS, TPU, PLA-CF, PETG-CF**: Apenas em **0.20mm Standard**. Não gerar outros layer heights ou profile types para esses materiais.
- **PLA e PETG**: Disponíveis em todos os profile types e layer heights definidos no combinations.json.

## Fabricantes para Exportação

Apenas exportar perfis de filamento dos seguintes fabricantes:

- Voolt3D
- Sunlu
- Creality

Os demais fabricantes ficam no banco (filament-data/) para referência mas não são exportados para Creality-Print/.

## Publicação Local

Destino: `~/filament-db/` com subpastas por slicer:

```
~/filament-db/
├── creality-print/
│   ├── filament/   ← .json + .info
│   └── process/    ← apenas .json
├── orca/
│   ├── filament/   ← .json
│   └── process/    ← .json
├── backups/        ← zips com timestamp (últimos 10)
└── diff/           ← perfis órfãos arquivados pelos scripts de inicialização
```

O `publish.sh` faz backup automático antes de sobrescrever: gera um zip com todos os perfis atuais (ambos slicers, filamentos + processos) em `~/filament-db/backups/profiles_YYYYMMDD_HHMMSS.zip`, mantendo os últimos 10 backups.

O `publish.sh` executa o pipeline local: build → backup → publish para ~/filament-db/.

Ao publicar para a pasta local, copiar apenas os perfis filtrados (fabricantes habilitados, combinações válidas).

## Inicialização dos Slicers

Cada slicer tem um script em `~/run-<slicer>.sh` que sincroniza perfis de `~/filament-db/<slicer>/` para o diretório do usuário do slicer, arquiva perfis órfãos em `~/filament-db/diff/` e abre o aplicativo.

### Creality Print

- Script: `~/run-creality-print.sh`
- Origem: `~/filament-db/creality-print/{filament,process}`
- Destino: `~/.config/Creality/Creality Print/7.0/user/8401264742/{filament,process}`
- `filament/` — recebe .json + .info
- `process/` — recebe apenas .json

### Orca Slicer

- Script: `~/run-orca-slicer.sh`
- Origem: `~/filament-db/orca/{filament,process}`
- Destino: `~/.config/OrcaSlicer/user/default/{filament,process}`
- Ambos recebem apenas .json

## Estrutura de Dados

- `filament-data/*.yaml` — fonte de verdade para filamentos (inclui `max_volumetric_speed` por perfil)
- `process-base/` — sistema de herança para perfis de processo
- `process-base/materials/` — velocidades base por tipo de material (sem MVS)
- `process-base/profile_types/` — parâmetros estruturais por profile type
- `process-base/layer_heights/` — overrides por layer height
- `process-base/combinations.json` — define quais combinações são geradas
- `build.py` — pipeline que gera banco SQLite + exporta para Creality-Print/
- `Creality-Print/` — output final para importar no slicer
- `publish.sh` — build + copia para ~/filament-db/
