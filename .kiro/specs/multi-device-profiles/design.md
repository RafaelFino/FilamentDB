# Design — Perfis Multi-Device

## Visão geral

Introduzir o **device** como quarta dimensão de configuração do pipeline de
geração de perfis, ao lado de material, profile_type e layer_height. O device
encapsula tudo que é específico da impressora: caps físicos, cadeia de herança
do slicer, `compatible_printers` e sufixo de nome.

A estratégia é **refatorar sem alterar comportamento primeiro** (extrair o K2
hardcoded para `devices/k2.json` com regressão zero), depois **adicionar a CC2**
como novo device. Isso isola o risco: o passo de refatoração é validado por diff
byte-a-byte dos perfis gerados; o passo de adição é puramente aditivo.

```
Dimensões do pipeline:
  device × profile_type × layer_height × material
     │          │              │            │
  caps,      estrutura,     geometria,   velocidades
  inherits,  multiplic.     shells,      base, temps
  compat.                   adhesion
```

## Decisões de arquitetura

### 1. Estrutura `process-base/devices/<id>.json`

Espelha o padrão existente (`materials/`, `profile_types/`, `layer_heights/`).
Cada device é um JSON declarativo. Esquema proposto:

```json
{
  "id": "cc2",
  "display_name": "Elegoo Centauri Carbon 2",
  "nozzle": "0.4",
  "name_template": "{layer}mm {type} @{display_name} {nozzle} nozzle - {material}",
  "orca_name_suffix": "CC2",
  "limits": {
    "max_extrusion_speed": 500,
    "max_travel_speed": 500,
    "max_acceleration": 20000
  },
  "slicers": {
    "orca": {
      "enabled": true,
      "compatible_printers": ["<NOME EXATO DO PERFIL DE MÁQUINA CC2 — CONFIRMAR>"],
      "filament_base": "generic",
      "process_inherits_by_layer": [
        { "max": 0.10, "inherits": "0.08mm ... @<máquina CC2>" },
        { "max": 0.14, "inherits": "0.12mm ... @<máquina CC2>" },
        { "max": 0.18, "inherits": "0.16mm ... @<máquina CC2>" },
        { "max": 0.22, "inherits": "0.20mm Standard @<máquina CC2>" },
        { "max": 0.26, "inherits": "0.24mm ... @<máquina CC2>" },
        { "max": 99.0, "inherits": "0.28mm ... @<máquina CC2>" }
      ]
    },
    "creality_print": {
      "enabled": false
    }
  }
}
```

Para o K2, o `devices/k2.json` reproduz exatamente os valores hoje hardcoded:

```json
{
  "id": "k2",
  "display_name": "Creality K2",
  "nozzle": "0.4",
  "orca_name_suffix": "K2",
  "limits": { "max_extrusion_speed": 600, "max_travel_speed": 800, "max_acceleration": 20000 },
  "slicers": {
    "orca": {
      "enabled": true,
      "compatible_printers": ["Creality K2 0.4 nozzle"],
      "process_inherits_by_layer": [
        { "max": 0.10, "inherits": "0.08mm SuperDetail @Creality K2 0.4 nozzle" },
        { "max": 0.14, "inherits": "0.12mm Detail @Creality K2 0.4 nozzle" },
        { "max": 0.18, "inherits": "0.16mm Optimal @Creality K2 0.4 nozzle" },
        { "max": 0.22, "inherits": "0.20mm Standard @Creality K2 0.4 nozzle" },
        { "max": 0.26, "inherits": "0.24mm Draft @Creality K2 0.4 nozzle" },
        { "max": 99.0, "inherits": "0.28mm SuperDraft @Creality K2 0.4 nozzle" }
      ]
    },
    "creality_print": {
      "enabled": true,
      "process_inherits_by_layer": [
        { "max": 0.28, "inherits": "{layer}mm {type} @Creality K2 0.4 nozzle" },
        { "max": 99.0, "inherits": "0.28mm Standard @Creality K2 0.4 nozzle" }
      ]
    }
  }
}
```

**Nota de regressão:** o nome dos perfis K2 hoje é
`"0.20mm Standard @Creality K2 0.4 nozzle - PLA"`. O `name_template` do K2 deve
produzir exatamente essa string. Como `display_name` = `"Creality K2"`, o
template `"{layer}mm {type} @{display_name} {nozzle} nozzle - {material}"` gera
`"0.20mm Standard @Creality K2 0.4 nozzle - PLA"` — idêntico. Confirmar na
implementação com diff.

### 2. Caps físicos derivados do device

Hoje em `generate_process_profile` (build.py ~683) os caps são constantes:

```python
if field == "travel_speed":
    raw_speed = min(raw_speed, 800.0)
else:
    raw_speed = min(raw_speed, 600.0)
# ...
profile[field] = str(min(raw_accel, 20000.0))
```

Refatorar para receber o device e ler os caps:

```python
def generate_process_profile(profile_type, layer_height, material_name, device):
    limits = device["limits"]
    # ...
    cap = limits["max_travel_speed"] if field == "travel_speed" else limits["max_extrusion_speed"]
    raw_speed = min(raw_speed, float(cap))
    # ...
    raw_accel = min(raw_accel, float(limits["max_acceleration"]))
```

O default (quando o device não declara `limits`) são os valores da K2
(600/800/20000), documentado. O princípio de que o MVS é responsabilidade do
filamento permanece intacto — nenhum cap volumétrico entra no processo.

**Observação sobre velocidades base dos materiais:** hoje `materials/*.json`
tem velocidades calibradas para a K2 (ex. PLA inner_wall 450). Para a CC2 (cap
500 vs 600) os valores da K2 que excedem 500 serão naturalmente limitados pelo
cap do device — sem necessidade de materiais por device nesta fase. Se no futuro
se desejar velocidades base por device, a estrutura comporta
`devices/<id>/materials/` como override opcional; **fora do escopo desta spec**.

### 3. `combinations.json` com dimensão `devices`

Formato novo (retrocompatível):

```json
{
  "combinations": [
    {
      "profile_type": "standard",
      "layer_heights": ["0.20", "0.28"],
      "materials": ["PLA", "PETG"],
      "devices": ["k2", "cc2"]
    }
  ],
  "default_devices": ["k2"]
}
```

- Se uma combinação não declara `devices`, usa `default_devices` (que é `["k2"]`
  por default — preserva comportamento atual).
- O loop de geração passa a ser:
  `for device in devices: for pt: for lh: for material: generate(...)`.
- Validação: todo `id` em qualquer `devices` deve ter arquivo em `devices/`;
  caso contrário o build falha com mensagem explícita.

### 4. Export parametrizado por device

#### Processo Orca (`export_orca_processes`)

Hoje o `inherits` e `compatible_printers` são resolvidos inline. Passam a ser
resolvidos pelo device do perfil:

```python
orca_cfg = device["slicers"]["orca"]
if not orca_cfg.get("enabled"): continue
orca_inherits = resolve_inherits(orca_cfg["process_inherits_by_layer"], lh)
data["compatible_printers"] = orca_cfg["compatible_printers"]
```

`resolve_inherits` percorre a lista `process_inherits_by_layer` e escolhe a
primeira entrada cujo `max` ≥ layer height (substitui a cadeia de `if/elif`
hardcoded hoje nas linhas 1298-1310).

#### Filamento Orca (`export_orca_filaments`)

O sufixo `@K2` vira `@{orca_name_suffix}` e `compatible_printers` vem do device.
Como o filamento descreve o material (não a máquina), o mesmo perfil de filamento
é exportado uma vez **por device habilitado**, cada um com seu sufixo e
`compatible_printers`. Nome: `"PLA - Voolt3D - Velvet @CC2"`.

#### Creality Print

Só gera para devices com `slicers.creality_print.enabled = true`. A CC2 tem
`enabled: false`, então nenhum arquivo Creality Print é gerado para ela —
atendendo ao Requisito 3.3 (CC2 é Orca-only).

### 5. Persistência no banco (process_profiles)

A tabela `process_profiles` ganha uma coluna `device_id` (TEXT). O export lê o
device por perfil. Isso mantém o banco como fonte de verdade e permite que os
exports filtrem/agrupem por device. O `name`/`print_settings_id` já embute o
device via `name_template`, garantindo unicidade entre devices.

### 6. Publicação (`publish.sh`)

Estrutura de destino por device sob `orca/`:

```
~/filament-db/orca/
├── k2/
│   ├── filament/
│   └── process/
└── cc2/
    ├── filament/
    └── process/
```

Decisão: migrar o layout atual (`orca/filament`, `orca/process`) para
`orca/k2/{filament,process}`. Isso é uma mudança de layout — o `run-orca-slicer.sh`
(fora do repo, em `~`) precisa ser ajustado para a nova origem. A spec registra
isso como passo de migração explícito. Alternativa de menor impacto: manter K2
em `orca/{filament,process}` (como hoje) e adicionar devices extras em
`orca/<id>/{filament,process}`. **A implementação escolhe a alternativa de menor
impacto por default** (K2 no local atual, CC2 em `orca/cc2/`), para não quebrar o
`run-orca-slicer.sh` existente, e documenta a opção de normalizar depois.

O backup zip e a rotação (10) passam a incluir as subpastas de device adicionais.

### 7. Documentação

- `.kiro/steering/filamentdb-rules.md`: nova seção "Devices (Printer Targets)"
  descrevendo a estrutura, a separação device/material/processo, e a regra de
  que caps físicos vêm do device.
- `README.md`: seção "Adicionar um novo device" com o passo a passo (criar JSON,
  referenciar em combinations, confirmar nome da máquina no slicer, build,
  publish).
- Registrar que CC2 é Orca-only e que o nome do perfil de máquina deve ser
  confirmado na instalação alvo.

### 8. Testes (tests/test_multi_device.py)

Seguindo o padrão de `test_build_catalog.py` (unittest + subprocess + temp DB):

- `test_all_combination_devices_have_definition`: todo device em
  `combinations.json` tem `devices/<id>.json`.
- `test_generated_speeds_respect_device_caps`: para cada perfil gerado, nenhuma
  velocidade/accel excede os caps do seu device.
- `test_k2_standard_regression`: perfil `0.20mm Standard ... K2 ... PLA` mantém
  os valores atuais (inner_wall 450, outer_wall 250, infill 500, accel 18000
  etc.).
- `test_orca_profile_device_coherence`: perfis Orca têm `compatible_printers` e
  `inherits` coerentes com a definição do device.
- `test_cc2_is_orca_only`: nenhum perfil Creality Print é gerado para CC2.

Todos offline, sem rede/LLM, rodando no job `test` do CI via `pytest tests/`.

### 9. CI

Nenhuma mudança estrutural. O job `test` já roda `build.py --only-db` e
`pytest tests/ -v`. Como o build multi-device roda no mesmo comando e os testes
novos ficam em `tests/`, o CI exercita tudo automaticamente. O job `price-smoke`
e a separação de camadas ficam intocados (Requisito 9.3).

### 10. Ordenação alfabética (fabricantes, materiais, tipos/modelos)

A maior parte das queries em `src/database.py` já tem `ORDER BY`, mas há dois
problemas: (a) `build_tree()` não reordena o dict de saída (confia na ordem de
inserção), ao contrário de `build_process_tree()`; (b) o SQLite ordena com
collation binária por padrão e os `.sort()` do `main.js` ordenam por code-point,
ambos sensíveis a maiúsculas/acentos.

Pontos de mudança (todos confirmados no código):

**`src/database.py`**
- `list_manufacturers` (~33) e `list_materials` (~42): trocar `ORDER BY name`
  por `ORDER BY name COLLATE NOCASE`.
- `build_tree()` (~469): usar `COLLATE NOCASE` nos `mf.name`/`m.name` do SQL e,
  no final, reordenar o dict de saída por chave (fabricante) e os `materials`
  internos por nome — espelhando o `return dict(sorted(...))` que
  `build_process_tree()` já faz.

**`static/main.js`**
- `populateCatalogManufacturers()` (~2660): trocar `.sort()` por
  `.sort((a,b)=>a.localeCompare(b))`.
- Handler `invCatMfr change` (~2666): mesmo ajuste no `.sort()` dos materiais.
- Handler `invCatMat change` (~2677): ordenar as cores/variantes por
  `color_name` com `localeCompare` (hoje sem sort).
- **Preservar** a ordenação de domínio: `renderTable()` (~231) mantém
  `matRank` + `MAT_ORDER` (~34) — não alterar.

**`templates/dashboard.html`**
- `#mfr-select` (~1041): nenhuma mudança necessária se `build_tree()` passar a
  reordenar a saída; o `{% for manufacturer in tree.keys() %}` herda a ordem
  corrigida. (Alternativa defensiva: `tree.keys()|sort`, mas a correção no
  backend é a canônica.)

Decisão: corrigir na **fonte** (backend `build_tree()` + collation) e ajustar os
`.sort()` client-side por consistência. Isso cobre tanto os combos
server-rendered quanto os montados em JS a partir de `window.treeData`.

### 11. Curadoria de exportação (lista específica)

A flag `export: true` já é lida pelo `build.py` como `export_enabled` (INSERT em
`filament_profiles` ~505-531; consumida por `_export_allowed` ~915 em
`export_filaments` e `export_orca_filaments`). **Nenhuma mudança de código** —
só edição de dados nos YAMLs. A curadoria é a lista do Requisito 11; o diff de
flags por arquivo:

- **`filament-data/voolt3d.yaml`**:
  - Adicionar `export: true`: `Voolt3D PLA High Speed`, `Voolt3D PLA Macaron`,
    `Voolt3D PLA CF` (material PLA-CF), `Voolt3D ABS`, `Voolt3D TPU`, mais os dois
    novos `Voolt3D PLA Premium Outlet` e `Voolt3D PLA EVO` (criados na seção 12).
  - Já têm: `Voolt3D PLA Velvet`, `Voolt3D PLA V-Silk`, `Voolt3D PETG HF`.
- **`filament-data/sunlu.yaml`**:
  - Adicionar: `Sunlu PLA Matte`.
  - Já têm: `Sunlu PLA High Speed`, `Sunlu PETG HS`.
- **`filament-data/creality.yaml`**:
  - Nada a adicionar — `Creality Hyper PLA`, `Creality CR PETG`,
    `Creality Hyper PETG` já têm.
- **`filament-data/elegoo.yaml`**:
  - Nada a mudar — `Elegoo PLA+` e `Elegoo PLA Pro` já têm a flag e ambos estão
    na lista curada.

Resultado: o conjunto exportado passa a ser exatamente os 18 produtos da tabela
curada (16 existentes + 2 novos). Nenhuma remoção de flag é necessária — todos os
perfis que hoje têm `export: true` estão na lista.

A restrição do steering (PLA-CF/ABS/TPU só geram **processo** em 0.20mm Standard)
continua valendo para o **processo**; a exportação de **filamento** desses não é
afetada.

**Nota de produto:** substitui a lista anterior de ~9 produtos. É uma curadoria
deliberada baseada no estoque físico real do usuário. O steering é atualizado
com a nova tabela.

### 12. Novos materiais Voolt3D (PLA Premium Outlet e PLA EVO)

Edição de dados em `filament-data/voolt3d.yaml`, seguindo o schema existente
(`lines[]` + `materials.PLA.profiles[]`). Sem mudança de código.

**PLA Premium Outlet** — nova linha + perfil:

```yaml
# em lines[]:
- name: Outlet Line
  description: PLA de troca de cor da linha de produção; cor imprevisível, base premium
  positioning: aesthetic
  difficulty: 40
  tier: premium
  category: aesthetic
  finish: variable
  notes: >
    Produto de troca de cor (cor indefinida, cada rolo é único). Mesma base dos
    PLA tradicionais. Linhas com aditivos (Stone/Wood/Cosmos) podem exigir bico
    >= 0.6mm; default do catálogo permanece 0.4mm.

# em materials.PLA.profiles[]:
- line: Outlet Line
  commercial_name: PLA Premium Outlet
  profile_name: Voolt3D PLA Premium Outlet
  export: true
  nozzle: { initial: 220, min: 190, max: 230 }   # specs oficiais 190-230
  bed:    { initial: 65,  standard: 60 }          # 50-70
  max_volumetric_speed: 25
  color: Indefinida
```

Valores de nozzle/bed/MVS vêm das specs oficiais do produto
([Voolt3D](https://voolt3d.com.br/produtos/filamento-pla-outlet/)).

**PLA EVO** — nova linha + perfil, specs oficiais confirmadas; posicionamento
Standard+ (PLA reforçado na adesão entre camadas):

```yaml
# em lines[]:
- name: EVO Line
  description: PLA Standard+ com maior aderência e resistência entre camadas
  positioning: balanced
  difficulty: 40
  tier: standard   # Standard+; base de tier standard
  category: general
  finish: standard
  notes: >
    PLA reforçado na adesão entre camadas (peças mais resistentes), baixo
    warping e boa fluidez. Compatível com impressoras convencionais e High
    Speed. Specs oficiais Voolt3D.

# em materials.PLA.profiles[]:
- line: EVO Line
  commercial_name: PLA EVO
  profile_name: Voolt3D PLA EVO
  export: true
  nozzle: { initial: 215, min: 190, max: 230 }   # specs oficiais 190-230
  bed:    { initial: 65,  standard: 60 }          # 50-70
  max_volumetric_speed: 25                        # oficial: até 25 mm³/s
  color: Natural
```

Valores de nozzle/bed/MVS vêm das specs oficiais do produto
([Voolt3D PLA EVO](https://voolt3d.com.br/produtos/filamento-pla-branco-off-white-evo-1kg/)).
Nota: o EVO tem MVS 25 (igual ao Outlet e ao High Speed) — o diferencial é a
adesão entre camadas, não a velocidade.

Ambos são **PLA puro** → disponíveis em todos os profile_types/layer heights pela
regra atual, e entram na curadoria de exportação (Requisito 11).

## Fluxo de dados (geração de um perfil CC2)

```
combinations.json (devices: ["k2","cc2"])
        │
        ▼
load devices/cc2.json  ──────────────┐
        │                            │ caps, inherits, compatible_printers
        ▼                            │
generate_process_profile(pt, lh, mat, device=cc2)
   merge base < layer < type         │
   apply material speeds × mult       │
   cap por device.limits ◄───────────┘
        │
        ▼
insert em process_profiles (device_id="cc2")
        │
        ▼
export_orca_processes (device cc2)
   inherits ← device.process_inherits_by_layer[lh]
   compatible_printers ← device.compatible_printers
        │
        ▼
OrcaSlicer/process/<nome CC2>.json  →  publish → ~/filament-db/orca/cc2/process/
```

## Riscos e mitigações

- **Nome do perfil de máquina CC2 errado**: se não bater com o instalado no
  Orca, a herança falha silenciosamente no slicer. Mitigação: parâmetro de
  config explícito + passo de confirmação na task + placeholder marcado.
- **Regressão silenciosa nos perfis K2**: mitigação por diff byte-a-byte dos
  JSONs gerados antes/depois da refatoração (task dedicada) + teste de
  regressão.
- **Velocidades base da K2 inadequadas para CC2**: nesta fase, cap do device
  limita; calibração fina de materiais por device fica como trabalho futuro
  documentado.
- **Layout de publicação quebrando `run-orca-slicer.sh`**: mitigação por manter
  K2 no local atual e isolar devices novos em subpastas.
