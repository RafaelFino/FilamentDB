# FilamentDB

FilamentDB é um sistema centralizado baseado em SQLite para gerenciamento, estruturação e exportação de perfis de materiais para impressão 3D.

O projeto elimina a fragmentação de configurações de filamentos presentes em fatiadores. Ele centraliza as variáveis em um banco de dados relacional e gera perfis prontos para importação, com foco inicial no Creality Print 7.0.

## Visão geral

* Fonte única de verdade: banco SQLite centralizado.
* UI web para navegar fabricantes, materiais e baixar perfis em lote.
* Exportação para Creality Print 7.0 em `.json` + `.info` dentro de `.zip`.
* Estrutura modular: `app.py` como host, `app_database.py` para SQLite, `services.py` para exportação e `web.py` para rotas.
* **Perfis de processo (print settings)**: Configurações de impressão otimizadas para diferentes usos (rápido, resistente, qualidade) para PLA e PETG.

## Estrutura do repositório

```text
FilamentDB/
├── app.py
├── app_database.py
├── services.py
├── web.py
├── requirements.txt
├── templates/
│   └── tree.html
├── static/
│   └── main.js
├── create_db.py
├── seed.py
├── seed_process.py
├── export-creality-print.py
├── export-process.py
├── data/
├── creality-print/
├── creality-print-process/
└── filament.db
```

## Instalação

```bash
python -m pip install -r requirements.txt
```

## Uso

### Método Recomendado: Usar o script run.sh

O script `run.sh` gerencia automaticamente o virtualenv, dependências e inicialização:

```bash
./run.sh
```

Este script:
- Cria e ativa o virtualenv automaticamente
- Instala as dependências do requirements.txt
- Cria o banco de dados se não existir
- Popula com perfis de filamento e processo
- Inicia o servidor Flask

### Método Manual

#### 1. Criar e ativar virtualenv

```bash
python3 -m venv .venv
source .venv/bin/activate
```

#### 2. Instalar dependências

```bash
pip install -r requirements.txt
```

#### 3. Criar o banco de dados

```bash
python create_db.py
```

#### 4. Popular o banco de dados com perfis de filamento

```bash
python seed.py
```

#### 5. Popular o banco de dados com perfis de processo (print settings)

```bash
python seed_process.py
```

Isso criará 6 perfis de processo:
- **PLA**: Fast, Strong, Quality
- **PETG**: Fast, Strong, Quality

#### 6. Executar a aplicação web

```bash
python app.py
```

Abra `http://localhost:5000/tree` no navegador para ver os perfis de filamento.
Abra `http://localhost:5000/process-profiles` para ver e comparar os perfis de processo.

### Exportar Perfis

#### Exportar perfis de filamento

```bash
python export-creality-print.py
```

#### Exportar perfis de processo

```bash
python export-process.py
```

### Instalar Perfis no Creality Print

O script `install-creality-profiles.py` descobre automaticamente o caminho do Creality Print e copia os perfis:

```bash
python install-creality-profiles.py
```

Este script:
- Detecta automaticamente o sistema operacional (Linux, macOS, Windows)
- Encontra o caminho de instalação do Creality Print
- Identifica o ID do usuário
- Copia os perfis de filamento para a pasta correta
- Copia os perfis de processo para a pasta correta

Se o caminho não for encontrado automaticamente, você pode especificá-lo manualmente quando solicitado.

## Variáveis de ambiente opcionais

* `FILAMENT_DB_PATH` — caminho do arquivo SQLite usado pelos scripts e pela aplicação.
* `CREALITY_OUTPUT_DIR` — diretório de saída para `export-creality-print.py`.
* `PROCESS_OUTPUT_DIR` — diretório de saída para `export-process.py`.
* `PORT` — porta usada pelo servidor Flask.
* `FLASK_DEBUG` — `1` ativa modo debug.

## API disponíveis

* `GET /health`
* `GET /manufacturers`
* `GET /materials`
* `GET /filament-profiles`
* `GET /filament-profiles/<id>`
* `GET /manufacturers/<id>/materials`
* `GET /download/creality-print?manufacturer=<name>&material=<name>`
* `GET /download/creality-print/<manufacturer>/<material>`
* `GET /download/creality-print/options`
* `GET /process-profiles` - Página web para visualizar e comparar perfis de processo
* `GET /api/process-profiles` - Lista todos os perfis de processo (API JSON)
* `GET /api/process-profiles/<id>` - Detalhes de um perfil de processo (API JSON)
* `GET /api/materials/<id>/process-profiles` - Perfis de processo por material (API JSON)
* `GET /download/process?material=<name>` - Download ZIP dos perfis de processo
* `GET /download/process/<material>` - Download ZIP dos perfis de processo
* `GET /api/download/process/options` - Opções de download de perfis de processo (API JSON)
* `GET /tree` - Página web para navegar perfis de filamento

## Exportação para Creality Print

### Perfis de Filamento
Copie os arquivos gerados para a pasta de usuário do fatiador:

```text
~/.config/Creality/Creality Print/7.0/user/<USER_ID>/filament
```

### Perfis de Processo (Print Settings)
Copie os arquivos gerados para a pasta de processo do fatiador:

```text
~/.config/Creality/Creality Print/7.0/user/<USER_ID>/process
```

## Perfis de Processo Disponíveis

O sistema inclui perfis de processo otimizados para diferentes necessidades:

### PLA
- **Fast**: Otimizado para velocidade, ideal para protótipos rápidos
- **Strong**: Otimizado para resistência mecânica, ideal para peças funcionais
- **Quality**: Otimizado para acabamento superficial, ideal para peças estéticas

### PETG
- **Fast**: Otimizado para velocidade com qualidade aceitável
- **Strong**: Otimizado para máxima resistência e durabilidade
- **Quality**: Otimizado para melhor acabamento visual

## Licença

Este projeto está sob a licença Apache-2.0.
