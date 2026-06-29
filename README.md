# FilamentDB

FilamentDB é um sistema centralizado baseado em SQLite para gerenciamento, estruturação e exportação de perfis de materiais para impressão 3D.

O projeto elimina a fragmentação de configurações de filamentos presentes em fatiadores. Ele centraliza as variáveis em um banco de dados relacional e gera perfis prontos para importação, com foco inicial no Creality Print 7.0.

## Visão geral

* Fonte única de verdade: banco SQLite centralizado.
* UI web para navegar fabricantes, materiais e baixar perfis em lote.
* Exportação para Creality Print 7.0 em `.json` + `.info` dentro de `.zip`.
* Estrutura modular: `app.py` como host, `app_database.py` para SQLite, `services.py` para exportação e `web.py` para rotas.

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
├── export-creality-print.py
├── data/
├── creality-print/
└── filament.db
```

## Instalação

```bash
python -m pip install -r requirements.txt
```

## Uso

### 1. Criar o banco de dados

```bash
python create_db.py
```

### 2. Popular o banco de dados

```bash
python seed.py
```

### 3. Executar a aplicação web

```bash
python app.py
```

Abra `http://localhost:5000/tree` no navegador.

### 4. Exportar os perfis em arquivos

```bash
python export-creality-print.py
```

## Variáveis de ambiente opcionais

* `FILAMENT_DB_PATH` — caminho do arquivo SQLite usado pelos scripts e pela aplicação.
* `CREALITY_OUTPUT_DIR` — diretório de saída para `export-creality-print.py`.
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
* `GET /tree`

## Exportação para Creality Print

Copie os arquivos gerados para a pasta de usuário do fatiador:

```text
~/.config/Creality/Creality Print/7.0/user/<USER_ID>/filament
```

## Licença

Este projeto está sob a licença Apache-2.0.
