"""
buildinfo.py — Informação da última atualização bem-sucedida do servidor.

O update-server.sh grava um arquivo (FILAMENTDB_BUILD_INFO_PATH) ao concluir
com sucesso, contendo o timestamp e o commit atual. A UI lê via /api/build-info
para o usuário saber se está na versão mais recente.

Formato do arquivo (KEY=VALUE, escrito pelo shell):
    updated_at=2026-08-28T22:00:03-03:00
    commit=abc1234
    commit_subject=...
"""

import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent


def _path():
    return os.environ.get(
        "FILAMENTDB_BUILD_INFO_PATH", str(ROOT_DIR / "build-info.env")
    )


def read():
    """Lê o build-info. Retorna dict com updated_at/commit/commit_subject.

    Se o arquivo não existe (ex.: rodando em dev sem update-server), retorna
    valores None — a UI trata como "desconhecido".
    """
    info = {"updated_at": None, "commit": None, "commit_subject": None}
    try:
        text = Path(_path()).read_text()
    except (OSError, FileNotFoundError):
        return info
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key in info:
            info[key] = val or None
    return info
