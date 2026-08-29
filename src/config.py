#!/usr/bin/env python3
"""
config.py — Carregador leve de configuração a partir de config.env.

Fonte única de verdade para paths de banco, porta e afins, compartilhada por
todos os componentes (app Flask, build.py, scripts shell via `source`, e o
unit do systemd via EnvironmentFile). Evita a divergência de "cada módulo
resolve o path por conta própria e os defaults podem não bater".

Precedência (do mais forte ao mais fraco):
    1. Variável já presente no ambiente (os.environ)
    2. Valor definido em config.env
    3. Default embutido no código (fallback)

Ou seja: config.env preenche apenas o que NÃO veio do ambiente. Assim o
systemd/cron/shell podem sobrescrever pontualmente sem editar o arquivo.

Formato do config.env: linhas KEY=VALUE (compatível com `source` no shell e
com `EnvironmentFile` do systemd). Comentários com `#`. Sem dependência externa
(não usa python-dotenv) para manter o projeto sem libs extras.
"""

import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_ENV_PATH = ROOT_DIR / "config.env"

# Defaults canônicos. São o fallback final quando a chave não está no ambiente
# nem no config.env. Todos relativos à raiz do projeto — o mesmo lugar que os
# módulos já usavam, então o comportamento sem config.env permanece idêntico.
_DEFAULTS = {
    # Banco principal; os demais bancos são irmãos no mesmo diretório.
    "DB_PATH": str(ROOT_DIR / "data" / "filament.db"),
    "FILAMENTDB_BACKUP_DIR": str(ROOT_DIR / "backups"),
    "FILAMENTDB_BUILD_INFO_PATH": str(ROOT_DIR / "build-info.env"),
    "PORT": "5000",
    # Autorização (feature flag desligada por padrão → sistema aberto).
    "FILAMENTDB_AUTH_ENABLED": "0",
    "FILAMENTDB_WRITERS": "",
    "FILAMENTDB_IDENTITY_HEADER": "Remote-Email",
    "FILAMENTDB_PROXY_SECRET": "",
    "FILAMENTDB_DEV_OPEN": "0",
}

_loaded = False


def _parse_env_file(path):
    """Lê um arquivo KEY=VALUE simples. Retorna dict. Tolera aspas e comentários."""
    values = {}
    try:
        text = path.read_text()
    except (OSError, FileNotFoundError):
        return values
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        if "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in ("'", '"'):
            val = val[1:-1]
        if key:
            values[key] = val
    return values


def load(force=False):
    """Carrega config.env no os.environ, sem sobrescrever valores definidos.

    Valor vazio em config.env ou no ambiente é tratado como não configurado,
    permitindo o fallback para o default canônico.
    """
    global _loaded
    if _loaded and not force:
        return current()

    file_values = _parse_env_file(CONFIG_ENV_PATH)

    # 1) config.env preenche só o que não veio do ambiente.
    # Valor vazio significa "não configurado".
    for key, val in file_values.items():
        if val != "" and not os.environ.get(key):
            os.environ[key] = val

    # 2) defaults preenchem o que ainda estiver ausente ou vazio.
    for key, val in _DEFAULTS.items():
        if not os.environ.get(key):
            os.environ[key] = val

    _loaded = True
    return current()


def current():
    """Snapshot das chaves conhecidas resolvidas no ambiente atual."""
    keys = set(_DEFAULTS) | set(_parse_env_file(CONFIG_ENV_PATH))
    return {k: os.environ.get(k) for k in keys}


def get(key, default=None):
    """Retorna uma configuração resolvida após carregar o ambiente."""
    load()
    return os.environ.get(key, default)


def database_path(filename="filament.db"):
    """Retorna o caminho de um banco no mesmo diretório do DB_PATH e cria a pasta."""
    main = Path(get("DB_PATH"))
    data_dir = main.parent
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / filename


# Carrega na importação: qualquer módulo que faça `from src import config`
# (ou importe algo que o faça) já encontra o ambiente resolvido.
load()
