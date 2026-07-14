# FilamentDB

Banco de dados de perfis de filamentos e configurações de processo para impressoras 3D, focado na **Creality K2 Combo** com o **Creality Print 7.0**.

## Arquitetura

```
filament-data/*.yaml →  Fonte de verdade (filamentos)
process-base/        →  Fonte de verdade (processos via herança)
        ↓
    build.py         →  Pipeline: schema + seed + export
        ↓
  filament.db        →  Banco SQLite (API lê daqui)
        ↓
  Creality-Print/
    filaments/       →  JSONs prontos para o Creality Print
    process/         →  JSONs prontos para o Creality Print
```

## Uso rápido

```bash
# 1. Instalar dependências e subir o servidor
./run.sh

# Ou manualmente:
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python3 build.py
python3 -m src.app
```

## Comandos

| Comando | O que faz |
|---------|-----------|
| `python build.py` | Recria banco + exporta perfis Creality Print |
| `python build.py --only-db` | Apenas recria o banco (sem export) |
| `python build.py --only-export` | Apenas exporta (banco já existe) |
| `python install.py` | Copia perfis para a instalação local do Creality Print |
| `./run.sh` | Setup completo + inicia servidor na porta 5000 |

## Como adicionar um filamento

1. Edite ou crie um arquivo YAML em `filament-data/` (ex: `filament-data/nova_marca.yaml`)
2. Execute `python build.py`
3. Os perfis estarão no banco, na API, e em `Creality-Print/filaments/`

## Como ajustar perfis de processo

Os processos são gerados por herança a partir de:

- `process-base/base.json` — configurações base compartilhadas
- `process-base/layer_heights/` — ajustes por altura de camada
- `process-base/profile_types/` — ajustes por tipo (quality, balanced, fast, etc)
- `process-base/materials/` — velocidades e acelerações por material
- `process-base/combinations.json` — define quais combinações gerar

Edite esses arquivos e execute `python build.py`.

## API

O servidor Flask expõe:

- `GET /api/filaments` — lista todos os filamentos
- `GET /api/process-profiles` — lista todos os perfis de processo
- `GET /api/tree` — árvore completa (fabricante > material > perfis)
- `GET /download/creality-print/<fabricante>/<material>` — ZIP com perfis
- `GET /download/process/<material>` — ZIP com perfis de processo
- `GET /health` — status do servidor

## Estrutura do projeto

```
FilamentDB/
├── filament-data/               # YAMLs de filamentos (fonte de verdade)
├── process-base/            # Sistema de herança de processos
│   ├── base.json
│   ├── combinations.json
│   ├── layer_heights/
│   ├── materials/
│   └── profile_types/
├── src/                     # Aplicação Flask
│   ├── app.py
│   ├── database.py
│   ├── services.py
│   └── web.py
├── templates/               # HTML do dashboard
├── static/                  # JS/CSS
├── scripts/                 # Utilitários de enriquecimento
├── build.py                 # Pipeline unificado
├── install.py               # Instala perfis no Creality Print local
├── run.sh                   # Setup + servidor
└── requirements.txt
```

## Requisitos

- Python 3.9+
- Flask, PyYAML (ver `requirements.txt`)
