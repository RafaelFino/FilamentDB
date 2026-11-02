# Tasks — Audit, Comparação com Baseline e Validação de Perfis K2

- [x] 1. Consolidar os achados da auditoria
  - Relatório pronto em `.agents/tasks/profile-audit-k2.md`. Achados por
    severidade abaixo (ver tarefas 2 e 6 para ação).
  - **ALTO:** (a) `safe.json:23` força `initial_layer_print_height: 0.24` →
    reintroduz o bug de múltiplo em Safe 0.16/0.20 (razões 1.5 e 1.2); (b)
    `base.json:21` `flush_into_objects: 1` contamina a peça em troca de cor
    (stock/schema/steering usam 0).
  - **MÉDIO:** (c) `layer_heights/0.24.json:6` `support_top_z_distance: 0.2` <
    layer_height 0.24 e quebra a monotonicidade da escala; (d) outer_wall/
    top_surface do Standard muito abaixo do stock e do teto MVS premium; (e)
    acoplamento solto shell_layers (profile_type) vs shell_thickness
    (layer_height).
  - **BAIXO:** (f) `prime_volume: 30` vs stock 45; (g) drift doc×dado no MVS do
    Voolt Velvet (steering diz 25, YAML diz 20).
  - _Requisitos: 1.8, 2.3, 2.4_

- [x] 2. Decidir remediações com o usuário
  - [x] 2.1 Correções de consistência ALTA (aprovadas e aplicadas):
    - Removido `initial_layer_print_height` de `safe.json` (layer_height manda).
    - `flush_into_objects: 1 → 0` em `base.json`.
    - _Requisitos: 3.1, 3.3_
  - [x] 2.2 Correção MÉDIA aplicada:
    - `layer_heights/0.24.json`: `support_top_z_distance 0.2 → 0.25`,
      `interface_spacing 0.6 → 0.7`, `interface_top_layers 3 → 2`,
      `xy_distance 0.4 → 0.5` (restaura monotonicidade e alinha com vizinhos).
    - _Requisitos: 3.2_
  - [x] 2.3 Conservadorismo do Standard — modo EQUILIBRADO aplicado na base do
    material (não no quality_speed, para preservar a 1ª camada):
    - PLA: `outer_wall 150 → 190` (efetivo @Std 114), `top_surface 130 → 180`
      (efetivo 108).
    - PETG: `outer_wall 120 → 150` (efetivo 90), `top_surface 110 → 135`
      (efetivo 81).
    - Internas (inner/infill) e 1ª camada: intocadas. Verificado: nada estoura o
      cap do device (maior outer gerado = 285 Fast PLA, cap 600).
    - _Requisitos: 2.4, 3.2, critério guia_
  - [ ] 2.4 Baixo (PENDENTE, não bloqueia): reconciliar MVS Voolt Velvet
    (steering 25 vs YAML 20) e decidir se `prime_volume` sobe de 30.
    - _Requisitos: 2.4_

- [x] 3. Implementar o validador `validate.py`
  - [x] 3.1 Criar o módulo com o dataclass `Violation` e `run_all()`.
    - _Requisitos: 4.1, 4.3_
  - [x] 3.2 Implementar `check_layer_multiple` (incluindo overrides promovidos por
    `ADHESION_OVERRIDE_FIELDS`).
    - _Requisitos: 1.1, 1.2_
  - [x] 3.3 Implementar `check_device_caps`.
    - _Requisitos: 1.3_
  - [x] 3.4 Implementar `check_multiplier_math` (speed/quality_speed/accel,
    detecção de dupla penalização).
    - _Requisitos: 1.4_
  - [x] 3.5 Implementar `check_shell_thickness` e `check_support_distances`.
    - _Requisitos: 1.5_
  - [x] 3.6 Implementar `check_prime_tower`, `check_inherits_resolve` e
    `check_combinations`.
    - _Requisitos: 1.6, 1.7_

- [x] 4. Integrar o validador ao build.py
  - Acumular `(profile, source_meta)` em `seed_processes()` e chamar
    `validate.run_all()` antes do export.
  - Adicionar flag CLI `--validate` (default ligado) / `--no-validate`.
  - Severidade alta → `sys.exit(1)`; média/baixa → `warn()`.
  - _Requisitos: 4.1, 4.2_

- [x] 5. Testes do validador
  - [x] 5.1 `tests/test_validate.py`: fixture válido, layer height não-múltiplo,
    velocidade acima do cap.
    - _Requisitos: 4.5_
  - [x] 5.2 Teste de integração: `build.py --validate` sobre a `process-base/`
    atual retorna exit 0 após remediação.
    - _Requisitos: 3.4, 4.5_

- [ ] 6. Aplicar as remediações aprovadas
  - Editar apenas `process-base/` (layer_heights, materials, profile_types,
    conforme decisão da tarefa 2).
  - Rodar `python3 build.py --validate` e confirmar exit 0 + contagem de perfis
    esperada (51 processos; 49 export Creality Print; 51 Orca).
  - _Requisitos: 3.1, 3.3, 3.4_

- [x] 7. Integrar o gate no CI
  - Adicionar passo `python build.py --validate` em
    `.github/workflows/ci.yml` como obrigatório.
  - _Requisitos: 4.4_

- [ ] 8. Publicar
  - Rodar `./publish.sh` (build + backup + sync para `~/filament-db/`).
  - Instruir o usuário a rodar `~/run-creality-print.sh` para sincronizar e abrir
    o slicer.
  - _Requisitos: 3.5_
