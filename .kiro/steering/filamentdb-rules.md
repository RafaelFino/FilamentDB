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
Fast → Standard → Strong → Detail → Safe
```

- **Fast**: Velocidade máxima. O mais rápido possível — aceita redução de qualidade em troca de tempo. 3 walls, 12% infill grid, inner-first.
- **Standard**: Equilíbrio geral, padrão de uso diário. 4 walls, 15% gyroid, outer-first, bom acabamento. Nome obrigatório — Creality Print requer um perfil "Standard" para iniciar.
- **Strong**: Resistência mecânica (6 walls, 55% infill). Mais lento, peças funcionais.
- **Detail**: Qualidade visual máxima. Layer heights baixos (0.08-0.16mm), 5 walls, 20% infill.
- **Safe**: Ultra-conservador para primeira impressão ou materiais desconhecidos. Lento mas confiável.

### Multiplicadores por Profile Type

```
Fast:     speed=1.70x  accel=2.00x
Standard: speed=1.00x  accel=1.00x
Strong:   speed=0.70x  accel=0.60x
Detail:   speed=0.55x  accel=0.45x
Safe:     speed=0.40x  accel=0.30x
```

### Limites Físicos da Máquina (caps no build.py)

- Velocidade de extrusão: 500 mm/s
- Travel: 800 mm/s
- Aceleração: 20000 mm/s²

## Materiais — Velocidades Base (process-base/materials/)

Os arquivos de material definem velocidades base que representam o alvo **Standard** para aquele tipo de material na K2. Referência: perfis do Orca Slicer para K2 0.4mm.

O `speed_multiplier` ajusta proporcionalmente as velocidades vs. PLA (referência 1.0):

| Material | speed_mult | accel_mult | default_accel | Racional |
|----------|-----------|-----------|---------------|----------|
| PLA      | 1.00      | 1.00      | 12000         | Referência Orca — velocidades alvo da K2 |
| PETG     | 0.85      | 0.85      | 10000         | Levemente menor por stringing/cooling |
| ABS      | 0.75      | 0.75      | 8000          | Menor por warping/enclosure |
| PLA-CF   | 0.70      | 0.75      | 8000          | Menor por abrasividade/rigidez |
| PETG-CF  | 0.60      | 0.70      | 7000          | Mais conservador — fibra + PETG |
| TPU      | 0.20      | 0.25      | 2500          | Flexível, velocidade muito baixa |

## Restrições de Materiais Especiais

- **ABS, TPU, PLA-CF, PETG-CF**: Apenas em **0.20mm Standard**. Não gerar outros layer heights ou profile types para esses materiais.
- **PLA e PETG**: Disponíveis em todos os profile types e layer heights definidos no combinations.json.

## Fabricantes para Exportação

Apenas exportar perfis de filamento dos seguintes fabricantes:

- Voolt3D
- Creality
- Sunlu
- F3D
- Elegoo

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
└── diff/           ← perfis órfãos arquivados pelos scripts de inicialização
```

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
- `publish.sh` — copia perfis para ~/filament-db/ (publicação local)
