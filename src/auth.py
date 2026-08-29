"""
auth.py — Autorização mínima (RBAC de dois níveis) para escrita de estoque.

Modelo: `writer` (pode escrever) vs `viewer` (só lê). A identidade vem de um
header injetado pelo proxy identity-aware (Pangolin). O gate só protege a
ESCRITA — leitura permanece aberta a qualquer request que chegou ao Flask.

FEATURE FLAG: controlada por FILAMENTDB_AUTH_ENABLED.
  - desligada (default): sistema aberto, usuário reportado como "guest".
  - ligada: escrita exige que o header de identidade case com a allowlist.

⚠️ SEGURANÇA: headers HTTP são forjáveis. Este gate só é seguro se:
  1. o Flask não for alcançável fora do proxy (bind interno), e
  2. houver um segredo compartilhado proxy↔Flask (FILAMENTDB_PROXY_SECRET).
Sem isso, a autorização é apenas cosmética.

Precedência de decisão em escrita (quando a flag está ON):
  1. Se PROXY_SECRET configurado e o header secreto não bate  → 403 (fail-closed)
  2. Se usuário do header ∈ allowlist                          → permite
  3. Caso contrário                                            → 403
Exceção de desenvolvimento: FILAMENTDB_DEV_OPEN=1 libera tudo (só use em dev).
"""

import os
from functools import wraps

from flask import request, jsonify

GUEST = "guest"
PROXY_SECRET_HEADER = "X-Proxy-Secret"


def _truthy(val):
    return str(val or "").strip().lower() in ("1", "true", "yes", "on")


def auth_enabled():
    """Feature flag mestra. Lida a cada chamada para permitir toggle sem restart lógico."""
    return _truthy(os.environ.get("FILAMENTDB_AUTH_ENABLED"))


def dev_open():
    """Modo dev: libera escrita mesmo com auth ligada (sem header de identidade)."""
    return _truthy(os.environ.get("FILAMENTDB_DEV_OPEN"))


def _identity_header_name():
    return os.environ.get("FILAMENTDB_IDENTITY_HEADER", "Remote-Email")


def _writers():
    """Allowlist de e-mails/usuários que podem escrever, vinda do config (CSV)."""
    raw = os.environ.get("FILAMENTDB_WRITERS", "")
    return {e.strip().lower() for e in raw.split(",") if e.strip()}


def _proxy_secret():
    return os.environ.get("FILAMENTDB_PROXY_SECRET", "")


def current_user():
    """Identidade do request.

    Com auth ligada: o valor do header de identidade (normalizado), ou None se
    ausente. Com auth desligada: sempre GUEST (não há identidade a verificar).
    """
    if not auth_enabled():
        return GUEST
    val = (request.headers.get(_identity_header_name()) or "").strip().lower()
    return val or None


def _proxy_trusted():
    """True se a request prova ter vindo do proxy confiável.

    Se nenhum PROXY_SECRET está configurado, não há como verificar — retorna
    True mas isso é inseguro (documentado). Com segredo configurado, exige o
    header secreto correto (fail-closed).
    """
    secret = _proxy_secret()
    if not secret:
        return True
    return request.headers.get(PROXY_SECRET_HEADER) == secret


def can_write():
    """Decide se o request atual pode escrever, sem produzir resposta HTTP.

    Usado tanto pelo decorator quanto pelo /api/me (para a UI).
    """
    if not auth_enabled():
        return True
    if dev_open():
        return True
    if not _proxy_trusted():
        return False
    user = current_user()
    return bool(user and user in _writers())


def me():
    """Snapshot de identidade/permissão para a UI (GET /api/me)."""
    return {
        "user": current_user() or GUEST,
        "can_write": can_write(),
        "auth_enabled": auth_enabled(),
    }


def require_writer(fn):
    """Decorator: bloqueia a rota com 403 se o request não puder escrever.

    Com a flag desligada é um no-op (deixa passar). Com ligada, aplica o gate
    completo (segredo do proxy + allowlist), em modo fail-closed.
    """
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not auth_enabled():
            return fn(*args, **kwargs)
        if dev_open():
            return fn(*args, **kwargs)
        if not _proxy_trusted():
            return jsonify({"error": "forbidden", "reason": "untrusted_origin"}), 403
        user = current_user()
        if not user or user not in _writers():
            return jsonify({
                "error": "read-only access",
                "reason": "not_a_writer",
                "user": user,
            }), 403
        return fn(*args, **kwargs)
    return wrapper
