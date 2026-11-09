# Compatibilidade com Slicers — Armadilhas do Creality Print e Orca

Guia operacional para mexer no export de perfis (`build.py`) e depurar
"perfis sumidos" / "lixo que não sai" nos slicers. Aprendido na marra.

## Regra de ouro

Quando um perfil "não aparece" ou "tem valor errado" no slicer, a fonte
(`process-base/`, `build.py`) quase sempre está certa — o problema está em
**como o slicer interpreta o JSON**. Antes de mexer na fonte:

1. Confirmar o `.json` no disco do usuário do slicer (campos esperados presentes).
2. **Ler o log de debug do slicer** — é a fonte de verdade do motivo:
   `~/.config/Creality/Creality Print/<versão>/log/debug_*.log*`. Procurar
   `incorrect keys`, `can not find parent`, `invalid preset`.
3. Se o valor volta errado após abrir o slicer logado, suspeitar de **cloud sync**.
4. Só então editar `build.py`/`process-base/` e rebuildar.

Nunca chutar nome/escopo de chave do slicer. Quando precisar do nome/formato
interno de um campo, **peça ao usuário para setá-lo na UI, salvar o perfil, e
colar o JSON salvo** — ler do próprio slicer é o único jeito confiável (os nomes
vêm do lineage OrcaSlicer/Bambu mas o Creality Print renomeia/filtra alguns).

## Creality Print — chaves e escopo (processo)

- **`flush_multiplier` NÃO vai no processo.** O CP a trata como chave de
  filamento; emitida no processo, ele **invalida o preset inteiro** (perfil some
  da UI). `build.py` omite `flush_multiplier` do `field_map` do `export_processes`
  (CP). Os demais `flush_into_infill/objects/support` são aceitos.
- **`type: "process"` e `instantiation: "true"` são OBRIGATÓRIOS** para o CP
  listar um preset de usuário. Sem eles o preset é classe-base invisível.
  `build.py` emite ambos no `data` do `export_processes`.
- Ao adicionar QUALQUER chave nova ao export de processo do CP, verificar o log
  de debug após importar: se aparecer `incorrect keys: <nova>`, o CP não aceita
  essa chave em processo — removê-la do export CP (pode continuar no Orca).

## Creality Print — cloud preset sync

- O CP logado sincroniza presets de usuário com a Creality Cloud
  (`Creality.conf` → `app.cloud` / `sync_user_preset` / `sync_system_preset`).
- A nuvem **sobrescreve o disco** no login: lixo antigo volta; perfis locais
  somem se a nuvem estiver vazia. Editar o conf local **não persiste** (o CP
  reescreve ao abrir).
- Solução durável: deletar lixo pela UI logado (propaga à nuvem) ou desligar o
  cloud preset sync nas Preferências. O FilamentDB é a fonte de verdade local.

## Primeira camada × multimaterial (invariante travada)

Com prime tower ligada (padrão em 100% dos perfis), o CP perde o CFS/multicolor
se `initial_layer_print_height != layer_height`. Invariante em `validate.py`
(`check_layer_multiple`): com prime tower, exigir `initial == layer`. Nunca
reintroduzir primeira camada "dobrada" para adesão em perfis com prime tower.

## Herança de filamento (parent)

Log `can not find parent for config .../<filamento>.json` = o `inherits` do
nosso filamento aponta para um preset-pai que o slicer não tem. O perfil fica
quarentenado/invisível. Verificar que o `inherits` resolve para um preset de
sistema existente em `.../system/Creality/filament/`.

Mapa `get_inherits_for_material` em `build.py` — nomes REAIS verificados no CP
7.3 (os nomes "ABS @...", "TPU @...", "Hyper PETG CF @...", "ASA @..." eram
INVENTADOS e quebravam):

| Material | inherits correto (K2 0.4) |
|----------|---------------------------|
| PLA      | `Hyper PLA @Creality K2 0.4 nozzle` |
| PETG     | `Hyper PETG @Creality K2 0.4 nozzle` |
| PETG CF  | `Hyper PETG-CF @Creality K2 0.4 nozzle` (hífen!) |
| ABS      | `CR-ABS @Creality K2 0.4 nozzle` |
| ASA      | `Generic ASA @Creality K2 0.4 nozzle` |
| TPU      | `CR-TPU @Creality K2 0.4 nozzle` |

Ao adicionar material/inherits novo, CONFIRMAR o nome exato com
`find ~/.config/Creality/"Creality Print"/<v>/system/Creality/filament/ -iname '*<mat>*K2 0.4*'`
antes — não inventar o nome do pai.

## OrcaSlicer — cobertura de campos no export de processo (gap corrigido)

O export de PROCESSO do Orca (`export_orca_processes`) emitia só um subconjunto
dos campos de perfil — faltavam suporte, prime tower, flush, brim, wall_generator
e os patterns. Sintoma: perfis apareciam na UI mas "vários parâmetros não vinham"
(ex.: bloco de suporte ausente). **Causa-raiz**: o gap NÃO estava no `set_val`
(que já funcionava) e sim no `SELECT` do `export_orca_processes` — enxuto, não
buscava essas colunas, então nunca chegavam ao payload.

Fix: o `SELECT` foi **estendido** com as colunas faltantes (desempacotadas na
tupla `row`) e foram adicionadas as chamadas de emissão correspondentes,
espelhando os nomes/valores/transformações do `field_map` do `export_processes`
(CP). O export Orca agora **espelha os campos de perfil do CP**, exceto:

- `flush_multiplier` — exclusão proposital (o CP rejeita a chave em processo;
  mantida fora do Orca por simetria).
- Colunas `[meta]` (printer_model, base_id, timestamps, ids etc.) — nunca vão
  para o payload.

Casas decimais: `set_val` arredonda float a 1 casa. Distâncias pequenas
(`support_top_z_distance`, `support_interface_spacing`,
`support_object_xy_distance`, `brim_object_gap`, `top/bottom_shell_thickness`) e
`initial_layer_print_height` são emitidas via helper `set_2dp` (2 casas) para não
colapsar 0.25→0.2 / 0.15→0.1 / 0.12→0.1 — mesmo tratamento já usado para
`ironing_spacing`. O mesmo `set_2dp` corrige um colapso pré-existente do próprio
`layer_height` (0.12→"0.1", 0.16→"0.2"), que fazia o Orca fatiar na altura
errada nos layer heights finos.

Travado por `OrcaProcessFieldCoverageTests` em `tests/test_multi_device.py`:
presença dos 8 de suporte + 4 de prime tower + 3 de flush + os 9 demais campos
(wall_generator/wall_sequence, os 3 patterns, os 2 shell_thickness,
initial_layer_print_height, infill_combination); ausência de `flush_multiplier`;
enum de `support_type` ∈ {normal(auto), tree(auto)}; 2 casas em 0.20 Standard e
no `layer_height` fino; e **paridade completa de VALOR CP×Orca** no perfil de
referência (`test_cp_orca_scoped_field_parity`, comparação numérica que tolera só
diferença de representação como `brim_width` "5.0"/"5"). Wipe
(`role_based_wipe_speed`/`wipe_on_loops`) é **condicional** — CP e Orca só o
emitem quando a coluna tem valor (ausente no Fast PETG em ambos); por isso não é
asserção de presença incondicional, só é garantido pela paridade por-perfil.

**Gate de runtime (manual, só o usuário):** a paridade estática CP×Orca NÃO
substitui carregar os presets no OrcaSlicer real e conferir o log de debug
(`~/.config/OrcaSlicer/log/debug_*.log.0`, extensão `.log.0`) por
`incorrect keys`/`invalid preset`/`invalid version`. Antes de publicar para uso,
confirmar na UI que o suporte aparece (`support_type=tree(auto)`,
`support_top_z_distance=0.25`, `support_critical_regions_only=1`).

## Export CP vs Orca — são blocos distintos no build.py

`export_processes` (Creality Print, `field_map` indexado) e
`export_orca_processes` (Orca, `set_val`) são independentes. Uma chave pode ser
válida em um slicer e não no outro. Ao corrigir um, verificar se o outro precisa
do mesmo tratamento — mas NÃO replicar cego (ex.: `flush_multiplier` sai só do CP).

## Checklist ao mexer no export de processo

- [ ] Rebuild com `.venv/bin/python build.py --validate` (0 violações ALTA).
- [ ] Contagens de contrato batem (ver steering `filamentdb-rules.md`).
- [ ] Importar no slicer e ler o log de debug — zero `incorrect keys` nos nossos.
- [ ] Perfis aparecem na UI do slicer.
- [ ] Idealmente: teste de contrato em `tests/test_multi_device.py` travando a
      presença de `type`/`instantiation` e a ausência de `flush_multiplier` no
      processo CP.
