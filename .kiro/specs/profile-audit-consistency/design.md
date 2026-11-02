# Design — Audit, Comparação com Baseline e Validação de Perfis K2

## Visão geral

O trabalho se divide em quatro camadas que mapeiam 1:1 para os requisitos:

1. **Auditoria (read-only)** — já em execução via workflow `bundled://investigate`;
   produz `.agents/tasks/profile-audit-k2.md`. O design aqui formaliza as
   invariantes verificadas para que virem código no validador.
2. **Comparação com baseline** — parte do mesmo relatório; define as fontes
   stock e o método de diff.
3. **Remediação** — edições em `process-base/` + rebuild + publish.
4. **Validação automatizada** — um módulo novo `validate.py` (ou
   `audit/validators.py`) chamado pelo `build.py` e pelo CI.

Decisão de design central: **as invariantes de auditoria e o validador
automatizado compartilham a mesma definição**. Em vez de ter regras no relatório
e regras duplicadas no código, as invariantes viram funções puras reutilizadas.
O relatório de auditoria é a aplicação one-shot dessas funções sobre o estado
atual; o validador é a aplicação recorrente no build/CI.

## Arquitetura

```
process-base/ (fonte de verdade)
      │
      ▼
  build.py ──(gera perfis em memória)──► validate.py (invariantes)
      │                                        │
      │                                        ├─ OK  → export (Creality-Print/, OrcaSlicer/)
      │                                        └─ FAIL→ exit≠0, mensagem citando fonte
      ▼
  .github/workflows/ci.yml ──► python build.py (--validate obrigatório)
```

### Onde o validador se encaixa no build.py

O `generate_process_profile()` já monta o perfil final em memória (merge,
overrides de adesão, multiplicadores, caps de device, herança). O ponto natural
de injeção é logo após a geração de **todos** os perfis em `seed_processes()`,
antes do export. O validador recebe a lista de perfis gerados + o contexto de
fonte (qual layer_height/profile_type/material/device originou cada um) e aplica
as invariantes.

Alternativa considerada e descartada: validar lendo os JSON já exportados.
Descartada porque (a) perde o rastro da fonte (`process-base/`), prejudicando a
mensagem de erro, e (b) validar antes do export evita publicar lixo.

## Componentes e invariantes

### Módulo `validate.py`

Funções puras, uma por invariante, cada uma recebendo os dados necessários e
retornando `list[Violation]` (vazio = OK). `Violation` carrega
`(severity, source_path, invariant, detail, got, expected)`.

| Invariante | Função | Regra |
|---|---|---|
| Layer multiple | `check_layer_multiple` | `initial_layer_print_height % layer_height ≈ 0` para todo layer_height, considerando overrides de profile_type/material promovidos por `ADHESION_OVERRIDE_FIELDS`. |
| Device caps | `check_device_caps` | toda velocidade de extrusão ≤ `max_extrusion_speed`; travel ≤ `max_travel_speed`; accel ≤ `max_acceleration`, por device. |
| Multiplier math | `check_multiplier_math` | `gerado ≈ base × mult` (speed/quality_speed/accel) dentro de `EPS`. |
| Shell coherence | `check_shell_thickness` | `top_shell_thickness ≈ top_shell_layers × layer_height` (idem bottom). |
| Support coherence | `check_support_distances` | `support_top_z_distance ≥ layer_height`; spacing/xy dentro de faixa sã. |
| Prime tower | `check_prime_tower` | `prime_tower_width ≥ 35`; `flush_multiplier` e flags coerentes com base. |
| Inherits | `check_inherits_resolve` | todo `inherits` resolvido existe no conjunto de pais do slicer alvo. |
| Combinations | `check_combinations` | todo device referenciado tem arquivo; contagem = esperada. |

`EPS` para comparação de float: `1e-6` nas razões de layer height, tolerância
relativa de `1e-3` na matemática de multiplicadores (strings `"300.0"` vs
recomputação).

### Integração no build.py

- Novo parâmetro de `main()`/CLI: `--validate` (default **ligado**;
  `--no-validate` para desligar em debug).
- `seed_processes()` acumula `(profile_dict, source_meta)` e, ao final, chama
  `validate.run_all(profiles, devices, source_defs)`.
- Em violação de severidade alta → `error()` + `sys.exit(1)`. Severidade
  média/baixa → `warn()` e segue (não quebra o build, mas aparece no log e no CI
  como aviso).

### Relatório de auditoria (one-shot)

O relatório `.agents/tasks/profile-audit-k2.md` (produzido pelo workflow) é a
Parte 1+2. O design não reescreve o relatório; ele define que, **após** o
relatório sair, as invariantes confirmadas viram as funções acima. Se a
auditoria encontrar uma classe de inconsistência não prevista aqui, adiciona-se
uma função nova ao `validate.py` (extensível por design).

### Comparação com baseline — método

Diff parâmetro-a-parâmetro entre nosso perfil gerado e os dois stock:

- **Fonte A (Creality Print 7.3)**: `~/.config/Creality/Creality Print/7.3/system/Creality/`.
- **Fonte B (OrcaSlicer System)**: `~/.config/OrcaSlicer/system/Creality/process/`
  — K2 0.4 nozzle base (K2 Pro/Plus só como contexto).
- Normalização: ambos usam JSON de preset; campos equivalentes podem ter nomes
  iguais (herança comum do PrusaSlicer/Bambu lineage). Comparar por chave; onde
  o nome diverge, mapear manualmente no relatório.
- Classificação de divergência de velocidade: cruzar com MVS dos filamentos
  premium (`filament-data/*.yaml`) para decidir "conservador e correto" vs
  "deixando capacidade na mesa".

## Modelo de dados

Sem schema novo. O validador opera sobre dicionários de perfil já existentes.
`Violation` é um dataclass efêmero, não persistido.

## Tratamento de erros

- Validador: falha dura (exit 1) só em severidade alta; médio/baixo = warning.
- Build com `--validate` no CI: qualquer alta quebra o pipeline.
- Comparação com baseline: se uma fonte stock não existir na máquina de CI,
  degradar graciosamente (a comparação é tarefa local/relatório, não entra no
  gate de CI).

## Estratégia de testes

- `tests/test_validate.py`: casos unitários por invariante — um fixture válido,
  um com layer height não-múltiplo, um com velocidade acima do cap.
- Teste de integração: rodar `build.py --validate` sobre a `process-base/` atual
  e exigir exit 0 (após remediação).
- CI: adicionar passo `python build.py --validate` em `ci.yml`.
