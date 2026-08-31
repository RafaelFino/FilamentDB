# FilamentDB — Roadmap e Estado do Projeto

> Documento de continuidade. Deve ser atualizado sempre que uma etapa importante da arquitetura, API, coleta de preços, deploy ou integração com LLMs mudar.
> Estado registrado em 2026-08-30/31, durante a conclusão da nova API pública de ingestão de preços.

## REGRA DE MANUTENÇÃO
Toda alteração relevante no repositório deve atualizar este documento no mesmo commit, registrando problema, causa, solução e estado de validação.

## Arquitetura e chaves

O FilamentDB separa catálogo técnico, histórico de preços e coleta agentic. O catálogo principal é `data/filament.db`; o histórico é `price-history.db`; snapshots ficam em `data/price-data/`.

Há duas identificações intencionais: `technical_key`, derivada da identidade interna do registro (`filament_profiles.id`), e `filament_key`, chave canônica persistida para correlação de ofertas. `offer_key` identifica uma oferta específica. Nunca misturar essas responsabilidades.

`tracking` é o opt-in de coleta: `tracking=1` significa pesquisar preços; `tracking=0` significa não pesquisar. Collector, API e validator devem respeitar a flag.

## Estado atual

A nova API de ingestão está separada da aplicação web e é usada pelo collector agentic do GitHub Actions. Mistral e Gemini estão configurados para a fase de validação; Groq, Z.ai, Cerebras e OpenRouter ficam para o fallback posterior.

O workflow reconstrói o catálogo com `python build.py --only-db` antes da coleta e instala `requirements.txt`, incluindo PyYAML.

## Incidentes recentes

### Schema antigo / `tracking`
O validator chegou a consultar `fp.tracking` em um artefato antigo do banco. A arquitetura correta mantém `tracking` no schema produzido por `build.py`, e o workflow passou a reconstruir o banco antes da coleta.

### `unknown_or_untracked_filament`
O collector chegou a montar uma chave para PETG 3DFila enquanto a API corretamente recusava perfis não rastreados. A solução foi tornar `tracking` o opt-in oficial e fazer o collector consumir o `filament_key` persistido no catálogo.

### PyYAML ausente
O workflow executava `build.py`, mas não instalava `requirements.txt`. Corrigido para instalar o arquivo de dependências antes do build.

### 2026-08-31 — banco errado usado pelo collector
O workflow confirmou que `build.py --only-db` criou o banco em `data/filament.db` e importou 98 perfis. Apesar disso, o collector usava `ROOT / "filament.db"`. Esse arquivo não era o banco recém-construído; por isso a consulta encontrou um schema sem `filament_key` e falhou com:

```text
sqlite3.OperationalError: no such column: fp.filament_key
```

**Causa:** divergência de caminho entre o produtor do catálogo (`build.py`) e o consumidor (`collect_prices_agent.py`).

**Correção:** o collector agora aponta explicitamente para `ROOT / "data" / "filament.db"`, o mesmo artefato produzido pelo build.

**Lição:** o caminho do catálogo deve ser uma configuração compartilhada ou uma constante claramente alinhada ao `DB_PATH` do build; nunca manter dois caminhos implícitos para o mesmo banco.

## Teste controlado

O teste deve continuar usando somente o perfil PETG XT Line da 3DFila com `tracking=1`, limitando a execução a um perfil. Não ampliar o catálogo nem reativar todos os providers enquanto o fluxo ponta a ponta não estiver verde.

A sequência esperada é: build do catálogo → collector lê `data/filament.db` → LLM → `POST /v1/agent/offers` → persistência em `price-history.db` → snapshot → validator.

## Backlog P0

- [ ] Reexecutar coleta controlada após correção do caminho do banco.
- [ ] Confirmar oferta real via API e persistência em `price-history.db`.
- [ ] Confirmar snapshot válido.
- [ ] Validar Mistral e Gemini.

## Backlog P1

- [ ] Liberar consulta para todos os filamentos desejados, mantendo `tracking` como controle explícito.
- [ ] Reativar Groq, Z.ai, Cerebras e OpenRouter como fallback.
- [ ] Definir ordem de fallback por disponibilidade/custo.
- [ ] Melhorar logs e relatório de coleta.

## Backlog P2/P3

- [ ] Mostrar todas as ofertas.
- [ ] Consolidar estoque/quantidades.
- [ ] Mostrar múltiplas cores.
- [ ] Melhorar normalização de kits/unidades/peso/preço.
- [ ] Melhorar histórico e comparações.
- [ ] Criar testes de contrato entre collector, API e banco.
- [ ] Adicionar testes de integração do workflow.

## Critério de pronto

A fase só termina quando healthcheck, ingestão real, persistência, correlação das chaves, snapshot, workflow e pelo menos dois provedores estiverem validados. Só depois disso ampliar escala e fallback.
