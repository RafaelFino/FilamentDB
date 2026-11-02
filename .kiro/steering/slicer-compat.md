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
