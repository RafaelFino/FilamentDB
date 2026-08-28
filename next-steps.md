# FilamentDB — Next Steps (Servidor)

Backlog de features do **servidor** (Flask), independentes do app mobile.
Para o roteiro do app Android, ver [`mobile-roadmap.md`](mobile-roadmap.md).

---

## 1. Autorização básica — escrita de estoque restrita a usuários permissionados

### Objetivo

Somente uma lista de usuários pode **alterar** o inventário/estoque. Todos os
demais usuários (já autenticados pelo Pangolin) continuam com acesso de
**leitura** ao dashboard, sem restrição.

Modelo: **RBAC mínimo de dois níveis** — `writer` (pode escrever) e `viewer`
(só lê). Sem cadastro de usuários no app; a identidade vem do Pangolin.

### Como funciona

O Pangolin, como proxy identity-aware, pode **forwardar a identidade do usuário
logado via header HTTP** para o backend (ver
[Forwarded Headers](https://docs.pangolin.net/manage/access-control/forwarded-headers)).
O Flask lê esse header e faz o match contra uma allowlist de writers.
*(Conteúdo da doc do Pangolin parafraseado por conformidade de licenciamento.)*

```
Request → Pangolin (autentica + injeta header de identidade) → Flask (autoriza)
```

- Leitura: liberada para qualquer request que passou pelo Pangolin.
- Escrita: só se o usuário do header estiver na allowlist.

### ⚠️ Risco crítico — header de identidade é forjável

Headers HTTP são triviais de falsificar. Se alguém conseguir falar **direto com
o Flask** (sem passar pelo Pangolin), pode mandar
`X-Forwarded-User: qualquer-um@exemplo.com` e o Flask acreditaria.

O gate no Flask **só é seguro** se as duas defesas abaixo estiverem no lugar:

1. **Rede — o Flask não pode ser alcançável fora do Pangolin.**
   Hoje o `run.sh` sobe com `HOST=0.0.0.0`, o que expõe o Flask em todas as
   interfaces. Na topologia com Pangolin, o Flask deve escutar apenas onde o
   túnel (Newt) o alcança (ex: `127.0.0.1` ou a interface interna), sem caminho
   direto da LAN/internet. **Revisar isto é pré-requisito da feature.**
2. **App — segredo compartilhado proxy↔Flask.**
   Configurar o Pangolin para enviar também um header secreto conhecido só pelo
   proxy e pelo Flask. O Flask valida o segredo **antes** de confiar no header de
   identidade. Assim, mesmo que alguém alcance o Flask, sem o segredo o header de
   usuário é ignorado (fail-closed).

Sem (1) e (2), a autorização é apenas cosmética.

### Escopo no código (já mapeado)

Endpoints de **escrita** em `src/web.py` (os únicos que alteram dados — persistem
em `inventory.db`):

- `POST   /api/inventory`            → criar item
- `PATCH  /api/inventory/<id>`       → editar item
- `POST   /api/inventory/<id>/use`   → marcar uso (decrementa rolos)
- `DELETE /api/inventory/<id>`       → remover item

Todo o resto é leitura e permanece aberto a qualquer usuário logado.

### Esboço de implementação

```python
# src/web.py (ou um src/auth.py dedicado)
import os
from functools import wraps
from flask import request, jsonify

# Allowlist de quem pode escrever. Origem: env var (não versionar e-mails reais).
WRITERS = set(
    e.strip().lower()
    for e in os.environ.get("FILAMENTDB_WRITERS", "").split(",")
    if e.strip()
)
# Nome real do header a confirmar com a config do Pangolin (ver "Pendências").
IDENTITY_HEADER = os.environ.get("FILAMENTDB_IDENTITY_HEADER", "X-Forwarded-User")
# Segredo compartilhado proxy↔Flask (defesa contra header forjado).
PROXY_SECRET = os.environ.get("FILAMENTDB_PROXY_SECRET", "")
PROXY_SECRET_HEADER = "X-Proxy-Secret"


def current_user():
    return (request.headers.get(IDENTITY_HEADER) or "").strip().lower()


def require_writer(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        # 1. Prova de que a request veio do proxy confiável.
        if PROXY_SECRET and request.headers.get(PROXY_SECRET_HEADER) != PROXY_SECRET:
            return jsonify({"error": "forbidden"}), 403
        # 2. Autorização por identidade.
        user = current_user()
        if not user or user not in WRITERS:
            return jsonify({"error": "read-only access", "user": user or None}), 403
        return fn(*args, **kwargs)
    return wrapper
```

Aplicar `@require_writer` nos 4 endpoints de escrita listados acima.

### Suporte ao front-end (cosmético, não é segurança)

- Novo endpoint `GET /api/me` retornando `{ "user": ..., "can_write": bool }`.
- No `static/main.js` (view de inventário), esconder/desabilitar os botões de
  escrita (`+ Adicionar filamento`, editar, mover, usar, remover) quando
  `can_write` for falso, e mostrar um aviso de "modo somente leitura".
- **Importante**: isto é só UX. A garantia real é o gate no servidor — o
  front-end nunca deve ser tratado como fronteira de segurança.

### Divisão de responsabilidades

- 🤖 **Kiro**: `require_writer` + aplicar nos 4 endpoints; `GET /api/me`;
  ajustes no `main.js`; ler `WRITERS`/`PROXY_SECRET`/header de env vars.
- 👤 **Rafael**:
  - Habilitar Forwarded Headers no recurso do Pangolin e **informar o nome
    exato do header e se o valor é email ou username**.
  - Configurar o header de segredo compartilhado no Pangolin.
  - Ajustar o bind do Flask (`run.sh`) para não ficar exposto fora do túnel.
  - Definir a lista de e-mails/usuários writers (env `FILAMENTDB_WRITERS`).

### Pendências / decisões em aberto

- [ ] 👤 Confirmar o **nome do header** de identidade que o Pangolin envia e o
      formato do valor (email vs username). Isso trava a implementação.
- [ ] 👤 Confirmar se o Pangolin consegue injetar um **header secreto** fixo por
      recurso (para a defesa nº 2). Se não, avaliar alternativa (ex: mTLS entre
      Traefik e Flask, ou bind exclusivo em rede interna).
- [ ] Decidir onde mora a allowlist: env var (simples) vs tabela no
      `inventory.db` (permite gerenciar sem redeploy). Começar com env var.
- [ ] Definir comportamento quando o header de identidade está ausente
      (ex: acesso direto em dev local): tratar como viewer? writer? Sugestão:
      um `FILAMENTDB_DEV_OPEN=1` que libera tudo só em desenvolvimento.

### Pronto quando

- Um usuário fora da allowlist consegue **ver** o estoque mas recebe 403 ao
  tentar qualquer escrita (testado via request direta, não só pela UI).
- Um usuário da allowlist consegue escrever normalmente.
- Uma request forjando o header de identidade **sem** o segredo compartilhado é
  rejeitada com 403.
- O Flask não responde a requests que não passaram pelo Pangolin.
