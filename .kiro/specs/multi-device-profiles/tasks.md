# Tasks — Perfis Multi-Device

Plano de implementação incremental. A ordem prioriza **regressão zero**: primeiro
extrair o K2 hardcoded para configuração (sem mudar nenhum output), validar por
diff, e só então adicionar a CC2. Cada task referencia os requisitos que atende.

- [ ] 1. Capturar baseline de regressão do K2
  - Rodar o build atual e salvar cópia dos JSONs gerados em
    `Creality-Print/` e `OrcaSlicer/` como referência (fora do git ou em
    diretório temporário) para diff posterior.
  - Documentar no PR o comando de diff a ser usado na validação.
  - _Requisitos: 5.1, 5.3_

- [ ] 2. Criar a estrutura de device e carregar no build
  - [ ] 2.1 Criar `process-base/devices/k2.json` reproduzindo exatamente os
        valores hoje hardcoded (caps 600/800/20000, `compatible_printers`
        `"Creality K2 0.4 nozzle"`, cadeias `inherits` Orca e Creality Print,
        `name_template` que gera o nome idêntico ao atual).
  - [ ] 2.2 Adicionar função `load_device(id)` em `build.py` com validação de
        schema mínima (campos obrigatórios) e defaults documentados (caps K2
        quando ausentes).
  - [ ] 2.3 Adicionar `load_devices_for_combinations()` que valida que todo
        device referenciado em `combinations.json` tem arquivo; falhar com erro
        explícito citando o `id` ausente.
  - _Requisitos: 1.1, 1.2, 1.3, 1.4_

- [ ] 3. Derivar caps físicos do device em `generate_process_profile`
  - [ ] 3.1 Alterar a assinatura para receber `device` e substituir as
        constantes 600/800/20000 pelos valores de `device["limits"]`.
  - [ ] 3.2 Garantir que o cap volumétrico (MVS) continua ausente do processo
        (responsabilidade do filamento) — nenhuma mudança nesse ponto.
  - [ ] 3.3 Usar `name_template` do device para montar `name`/`print_settings_id`.
  - _Requisitos: 2.1, 2.2, 2.4, 3.4_

- [ ] 4. Adicionar dimensão `devices` ao `combinations.json`
  - [ ] 4.1 Adicionar `"devices": ["k2"]` nas combinações existentes e
        `"default_devices": ["k2"]` no topo (preserva comportamento).
  - [ ] 4.2 Alterar `seed_processes()` para iterar
        `device × profile_type × layer_height × material`, usando
        `default_devices` quando a combinação não declara `devices`.
  - [ ] 4.3 Adicionar coluna `device_id` à tabela `process_profiles` e popular no
        insert.
  - _Requisitos: 4.1, 4.2, 4.3_

- [ ] 5. Parametrizar export Orca por device
  - [ ] 5.1 Em `export_orca_processes`, resolver `inherits` via
        `device.slicers.orca.process_inherits_by_layer` (substituir a cadeia
        if/elif) e `compatible_printers` via device. Pular devices com Orca
        `enabled: false`.
  - [ ] 5.2 Em `export_orca_filaments`, usar `orca_name_suffix` do device no nome
        e `compatible_printers` do device; exportar o filamento uma vez por
        device Orca habilitado.
  - _Requisitos: 3.1, 3.2, 3.4_

- [ ] 6. Condicionar export Creality Print ao device
  - [ ] 6.1 Em `export_processes` (Creality Print), gerar apenas para devices com
        `slicers.creality_print.enabled = true`; resolver `inherits` via a
        cadeia do device.
  - _Requisitos: 3.3_

- [ ] 7. Validar regressão zero do K2
  - [ ] 7.1 Rodar o build e fazer diff byte-a-byte contra o baseline da task 1.
        O resultado esperado é **zero diferenças** nos perfis K2.
  - [ ] 7.2 Corrigir qualquer divergência até o diff ficar limpo antes de
        prosseguir para a CC2.
  - _Requisitos: 5.1, 5.2, 5.3_

- [ ] 8. Adicionar o device CC2 (Orca-only)
  - [ ] 8.1 **Confirmar o nome exato do perfil de máquina CC2** no OrcaSlicer
        alvo (ou no repo de perfis Elegoo/Orca). Esse nome alimenta
        `compatible_printers` e as entradas de `process_inherits_by_layer`.
  - [ ] 8.2 Criar `process-base/devices/cc2.json` com caps 500/500/20000,
        `creality_print.enabled = false`, cadeia `inherits` Orca da CC2 e
        `orca_name_suffix: "CC2"`.
  - [ ] 8.3 Adicionar `"cc2"` às combinações desejadas em `combinations.json`
        (começar por Standard 0.20 PLA/PETG, expandir conforme validação).
  - [ ] 8.4 Rodar o build e inspecionar os perfis CC2 gerados (nome, inherits,
        compatible_printers, caps aplicados).
  - _Requisitos: 1.1, 2.3, 3.1, 3.2, 3.3, 4.1_

- [ ] 9. Atualizar `publish.sh` para múltiplos devices
  - [ ] 9.1 Manter K2 em `~/filament-db/orca/{filament,process}` (local atual) e
        publicar CC2 em `~/filament-db/orca/cc2/{filament,process}`.
  - [ ] 9.2 Incluir as subpastas de device no backup zip e preservar a rotação
        (últimos 10).
  - [ ] 9.3 Atualizar contagens/resumo da saída do script para refletir devices.
  - _Requisitos: 6.1, 6.2, 6.3_

- [ ] 10. Testes multi-device
  - [ ] 10.1 Criar `tests/test_multi_device.py` (padrão unittest + subprocess +
        temp DB, como `test_build_catalog.py`).
  - [ ] 10.2 `test_all_combination_devices_have_definition`.
  - [ ] 10.3 `test_generated_speeds_respect_device_caps` (nenhuma velocidade/accel
        acima do cap do device).
  - [ ] 10.4 `test_k2_standard_regression` (valores atuais do Standard 0.20 PLA).
  - [ ] 10.5 `test_orca_profile_device_coherence` (compatible_printers e inherits
        coerentes com o device).
  - [ ] 10.6 `test_cc2_is_orca_only` (nenhum perfil Creality Print para CC2).
  - [ ] 10.7 Rodar `pytest tests/ -v` localmente e confirmar verde.
  - _Requisitos: 8.1, 8.2, 8.3, 8.4, 8.5_

- [ ] 11. Documentação
  - [ ] 11.1 Atualizar `.kiro/steering/filamentdb-rules.md` com a seção "Devices
        (Printer Targets)": estrutura `process-base/devices/`, separação
        device/material/processo, caps físicos vindos do device.
  - [ ] 11.2 Atualizar `README.md` com "Adicionar um novo device" (criar JSON,
        referenciar em combinations, confirmar nome da máquina, build, publish).
  - [ ] 11.3 Registrar que a CC2 é Orca-only e o requisito de confirmar o nome do
        perfil de máquina no slicer alvo.
  - _Requisitos: 7.1, 7.2, 7.3_

- [ ] 13. Ordenação alfabética (fabricantes, materiais, tipos/modelos)
  - [ ] 13.1 `src/database.py`: aplicar `COLLATE NOCASE` em `list_manufacturers`,
        `list_materials` e nos `mf.name`/`m.name` de `build_tree()`.
  - [ ] 13.2 `src/database.py`: reordenar o dict de saída de `build_tree()` por
        fabricante e os `materials` internos por nome (espelhando
        `build_process_tree()`).
  - [ ] 13.3 `static/main.js`: trocar `.sort()` por `localeCompare` em
        `populateCatalogManufacturers()` e no handler `invCatMfr change`; ordenar
        cores por `color_name` no handler `invCatMat change`.
  - [ ] 13.4 Confirmar que a ordenação de domínio (`MAT_ORDER`/`matRank` em
        `main.js`, `mat_rank` em `build_process_tree`) permanece intacta.
  - [ ] 13.5 Verificar na UI: `#mfr-select` e combos de inclusão em ordem
        alfabética case-insensitive.
  - _Requisitos: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7_

- [ ] 16. Cadastrar novos materiais Voolt3D (pré-requisito da task 14)
  - [ ] 16.1 Em `filament-data/voolt3d.yaml`, adicionar a linha `Outlet Line`
        (tier premium) e o perfil `Voolt3D PLA Premium Outlet` em
        `materials.PLA.profiles[]` com nozzle 190-230 / bed 50-70 / MVS 25 /
        `color: Indefinida`, note de troca-de-cor e `export: true`.
  - [ ] 16.2 Adicionar a linha `EVO Line` (Standard+) e o perfil
        `Voolt3D PLA EVO` com specs oficiais (nozzle 190-230 / initial ~215,
        bed 50-70, MVS 25), `note` do diferencial (adesão entre camadas) e
        `export: true`.
  - [ ] 16.3 Rodar `python build.py --only-db` e confirmar que os dois perfis
        entram no catálogo sem erro de schema.
  - _Requisitos: 12.1, 12.2, 12.3, 12.4, 12.5, 12.6_

- [ ] 14. Curadoria de exportação (lista específica)
  - [ ] 14.1 Em `filament-data/voolt3d.yaml`, adicionar `export: true` a
        `Voolt3D PLA High Speed`, `Voolt3D PLA Macaron`, `Voolt3D PLA CF`,
        `Voolt3D ABS`, `Voolt3D TPU` (Velvet, V-Silk, PETG HF e os dois novos da
        task 16 já ficam marcados).
  - [ ] 14.2 Em `filament-data/sunlu.yaml`, adicionar `export: true` a
        `Sunlu PLA Matte` (High Speed e PETG HS já têm).
  - [ ] 14.3 Em `filament-data/elegoo.yaml`, nenhuma mudança — `Elegoo PLA+` e
        `Elegoo PLA Pro` já têm a flag e ambos estão na lista curada.
  - [ ] 14.4 Em `filament-data/creality.yaml`, nenhuma mudança (os 3 já têm).
  - [ ] 14.5 Rodar `python build.py` e `./publish.sh --list`; confirmar que a
        lista exibida corresponde **exatamente** à tabela curada (18 produtos).
  - [ ] 14.6 Atualizar o steering substituindo a lista de ~9 produtos pela nova
        tabela curada.
  - _Requisitos: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.7_

- [ ] 15. Validação final e CI
  - [ ] 15.1 Rodar `build.py --only-db` + `pytest tests/ -v` (espelha o job
        `test` do CI) e confirmar verde, sem rede nem LLM.
  - [ ] 15.2 Confirmar que o job `price-smoke` e a estrutura de jobs do CI
        permanecem inalterados.
  - [ ] 15.3 Fatiar um STL de teste no OrcaSlicer local com um perfil CC2 e
        exportar `.3mf`; confirmar que o arquivo embute processo/filamento/máquina
        CC2 (validação manual do caso de uso real).
  - [ ] 15.4 Verificar na UI que fabricantes/materiais/tipos aparecem em ordem
        alfabética nos combos (fecha a Mudança 1).
  - [ ] 15.5 Confirmar via `publish.sh --list` que o conjunto exportado é
        exatamente a tabela curada de 18 produtos (fecha a Mudança 2), incluindo
        os dois novos materiais Voolt3D.
  - _Requisitos: 9.1, 9.2, 9.3, 10.1, 11.5, 12.1, 12.2_
