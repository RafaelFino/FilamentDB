# FilamentDB

Banco de dados de perfis de filamentos e configurações de processo para impressoras 3D, focado na **Creality K2 Combo** com o **Creality Print 7.0**.

## Filosofia: Separação de Responsabilidades

O sistema adota uma separação clara entre perfil de processo e perfil de filamento:

| Componente | Responsabilidade | Exemplo |
|------------|------------------|---------|
| **Perfil de Processo** | Define velocidades alvo da *impressora* + estrutura da peça | 500 mm/s inner wall no Speed |
| **Perfil de Filamento** | Define o limite de fluxo do *material* (`filament_max_volumetric_speed`) | Voolt3D Velvet: 25 mm³/s |
| **Creality Print** | Combina os dois em runtime, aplica o menor limitador | Slicer calcula velocidade real |

### Por que essa abordagem?

Perfis de processo que limitam velocidades com base no material penalizam filamentos premium. Um PLA Silk (MVS=12) e um PLA High Speed (MVS=25) teriam o mesmo perfil de processo, mas capacidades completamente diferentes.

Com a separação:
- O perfil de processo define o **potencial da máquina** para cada profile type
- O filamento define o **limite do material**
- O slicer aplica automaticamente `max_speed = MVS / (layer_height × line_width)`
- Filamentos premium aproveitam o máximo da K2, filamentos lentos são contidos sem configuração extra

### Hierarquia de Perfis de Processo

```
Fast → Standard → Strong → Detail → Safe
```

| Profile Type | Foco | Walls | Infill | Speed Mult |
|--------------|------|-------|--------|-----------|
| **Fast** | Velocidade máxima | 3 | 12% grid | 1.70x |
| **Standard** | Equilíbrio geral | 4 | 15% gyroid | 1.00x |
| **Strong** | Resistência mecânica | 6 | 55% | 0.70x |
| **Detail** | Qualidade visual (0.08-0.16mm) | 5 | 20% gyroid | 0.55x |
| **Safe** | Ultra-conservador | 4 | 18% gyroid | 0.40x |

### MVS dos Filamentos Principais

| Filamento | MVS (mm³/s) | Cap em 0.20mm* |
|-----------|-------------|----------------|
| Voolt3D Velvet | 25 | ~277 mm/s |
| Voolt3D PLA HS | 25 | ~277 mm/s |
| Sunlu PLA HS | 22 | ~244 mm/s |
| Voolt3D PLA Standard | 20 | ~222 mm/s |
| Creality Hyper PETG | 18 | ~200 mm/s |
| Sunlu PLA Meta | 18 | ~200 mm/s |
| Sunlu PLA+ | 15 | ~167 mm/s |
| Voolt3D PETG HF | 12 | ~133 mm/s |
| Sunlu PETG | 12 | ~133 mm/s |

*Cap = MVS / (0.20 × 0.45), velocidade máxima de extrusão que o slicer aplica.

## Arquitetura

```
filament-data/*.yaml →  Fonte de verdade (filamentos + MVS por perfil)
process-base/        →  Fonte de verdade (processos via herança, sem cap volumétrico)
        ↓
    build.py         →  Pipeline: schema + seed + export
        ↓
  filament.db        →  Banco SQLite
        ↓
  Creality-Print/
    filaments/       →  JSONs com filament_max_volumetric_speed
    process/         →  JSONs com velocidades alvo da impressora
        ↓
  publish.sh         →  Copia para ~/filament-db/
        ↓
  run-creality-print.sh → Copia para Creality Print e abre o slicer
```

## Uso rápido

```bash
# Build completo (banco + export)
python3 build.py

# Publicar localmente
./publish.sh

# Build + publish em um comando
./publish.sh  # já roda build.py internamente

# Apenas publish (sem rebuild)
./publish.sh --no-build

# Abrir Creality Print com perfis atualizados
~/run-creality-print.sh
```

## Comandos

| Comando | O que faz |
|---------|-----------|
| `python3 build.py` | Recria banco + exporta perfis Creality Print |
| `python3 build.py --only-db` | Apenas recria o banco (sem export) |
| `python3 build.py --only-export` | Apenas exporta (banco já existe) |
| `./publish.sh` | Build + copia para ~/filament-db/ |
| `./publish.sh --no-build` | Apenas copia (sem rebuild) |
| `./publish.sh --clean` | Limpa destino antes de copiar |

## Como adicionar um filamento

1. Edite ou crie um arquivo YAML em `filament-data/` (ex: `filament-data/nova_marca.yaml`)
2. Defina `max_volumetric_speed` para cada perfil (obrigatório — é o que limita velocidade no slicer)
3. Execute `python3 build.py && ./publish.sh --no-build`
4. Os perfis estarão em `~/filament-db/` prontos para o Creality Print

## Como ajustar perfis de processo

Os processos são gerados por herança a partir de:

- `process-base/base.json` — configurações base compartilhadas
- `process-base/layer_heights/` — ajustes por altura de camada
- `process-base/profile_types/` — parâmetros estruturais (walls, infill, seam)
- `process-base/materials/` — velocidades e acelerações por tipo de material
- `process-base/combinations.json` — define quais combinações gerar

As velocidades nos materiais definem o alvo **sem cap volumétrico**. O slicer limita automaticamente pela seleção do filamento.

## Estrutura do projeto

```
FilamentDB/
├── filament-data/           # YAMLs de filamentos (fonte de verdade)
├── process-base/            # Sistema de herança de processos
│   ├── base.json            # Config base (suporte, printer, etc)
│   ├── combinations.json    # Quais perfis gerar
│   ├── layer_heights/       # Override por layer height
│   ├── materials/           # Velocidades alvo por material
│   └── profile_types/       # Estrutura por profile type
├── Creality-Print/          # Output exportado
│   ├── filaments/           # Perfis de filamento (.json + .info)
│   └── process/             # Perfis de processo (.json + .info)
├── src/                     # Aplicação Flask
├── templates/               # HTML do dashboard
├── static/                  # JS/CSS
├── build.py                 # Pipeline unificado
├── publish.sh               # Publica para ~/filament-db/
└── requirements.txt
```

## Requisitos

- Python 3.9+
- Flask, PyYAML (ver `requirements.txt`)
