# Guia de Calibração — Creality K2 + extrusora DXC2

Guia operacional para diagnosticar e corrigir **sub-extrusão** (calibração,
saturação do motor, vazão, temperatura) e calibrar o fluxo na ordem correta.
Escrito para o setup real: **Creality K2 (Klipper) com extrusora DXC2**. Os configs
vivem em `~/git/CrealityK2-PrinterConfig/` (`default/` = stock, `DXC2/` = atual).

> **TL;DR do caso deste setup:**
> - **Fato medido:** a extrusão entrega menos filamento que o pedido, déficit
>   **cresce com a velocidade** (90/70/20 mm para 100 pedidos a 1/6/16,8 mm/s);
>   **pó de filamento** na extrusora (patinagem real).
> - **Causa provável (fontes externas):** **engrenagem de tração arrastando no
>   frame da DXC2** — problema conhecido ([Phaetus Issue #3](https://github.com/Phaetus/DXC-2-Extruder/issues/3)
>   + fórum Creality). **Não** é tensão insuficiente (usuários têm pó mesmo no mais
>   frouxo), e os parafusos da montagem afrouxam com o ciclo térmico.
> - **Ação prioritária:** teste de **rotação livre** da engrenagem (sentir arrasto)
>   → solução do fabricante (afrouxar 2 parafusos, girar até suave, reapertar) +
>   reapertar os parafusos da montagem. Em paralelo: testar **outro filamento** (D).
> - **Revisar:** o aumento para 230 °C pode ter sido contraproducente (calor amolece
>   o filamento e facilita o descascamento) — considerar voltar a ~220 °C.
> - **`rotation_distance` nominal: 6.86** — manter; não recalibrar enquanto houver
>   patinagem.

## Diagnóstico atual (nov/2026)

O sintoma observado é **sub-extrusão**, confirmado por fotos do teste de Flow Rate
do Creality Print (perfil `0.20mm Standard PLA`, Voolt3D Velvet):

- Top layers com **gaps/frestas** entre as linhas (não encostam).
- **Pinholes**/buracos espalhados, piores nas placas de flow mais negativo.
- A placa **+10%** foi a **menos ruim** → quanto mais material, melhor fica.
  Assinatura inequívoca de **falta de material** (sub-extrusão), não excesso.

> **Leitura do teste de flow:** todas as placas saíram ruins; os "−20 / −9"
> escolhidos eram apenas os *menos piores* de um lote inteiro sub-extrudado. O
> teste estava varrendo na **direção errada** — o ótimo está do lado positivo (mais
> flow), não negativo. Por isso "mesmo assim ficou ruim": não havia ponto bom
> naquela faixa.

### O que é FATO vs o que é HIPÓTESE

Separação honesta, para não cravar conclusão não testada.

#### Fatos (medidos)

1. A extrusão entrega **menos filamento que o pedido**, e o déficit **cresce com a
   velocidade**. Dois testes escalonados (rd=6.86), em temperaturas diferentes:

   | Comando      | Velocidade | **220 °C** | **230 °C** |
   |--------------|------------|------------|------------|
   | `E100 F60`   | 1 mm/s     | 90 (−10%)  | 110 (+10%)* |
   | `E100 F360`  | 6 mm/s     | 70 (−30%)  | 70 (−30%)  |
   | `E100 F1008` | 16,8 mm/s  | 20 (−80%)  | 20 (−80%)  |

   \* A 1 mm/s o resultado variou dentro da margem de medição manual (±5–10 mm) e
   pode incluir **oozing** a 230 °C (PLA escorre sozinho durante os ~100 s do
   disparo lento). Tratar como "perto de 100", não como super-extrusão real.

   **Leitura:** a 6 e 16,8 mm/s os números são **idênticos** nas duas temperaturas
   → subir para 230 °C **não aliviou** o déficit sob carga. Isso **enfraquece a
   hipótese C** (contrapressão/temperatura) como causa do déficit em velocidade.

2. **Pó de plástico dentro da extrusora** (observado ao manusear). É debris de
   filamento raspado pelos dentes da engrenagem — **evidência física direta de
   patinagem mecânica (hipótese A)**. O pó ainda entope os vãos dos dentes,
   reduzindo a mordida e realimentando a patinagem. **O pó tinha as cores dos
   filamentos das últimas duas peças impressas** (não é pó metálico): confirma que é
   PLA raspado, e **levanta a hipótese D (filamento como causa)** — ver abaixo.

3. No teste manual **parado** (extrusora na mão), a engrenagem morde o filamento e
   o acoplamento ao eixo é firme. **Ressalva (confirmada como falso-negativo):**
   parado, sem a contrapressão do bico quente, a engrenagem morde bem; o
   deslizamento só aparece **sob carga**. O pó (fato 2) é a evidência que o teste
   estático não capturou.

4. Config: `motor_control.cfg` tem `motor_closed_loop: x,y,e` (o extruder é servo
   closed-loop com encoder) e **não** tem bloco de parâmetros `e_*` (só `x/y/z/z1`).
   Há `motor_e_stall: nozzle_mcu:PB12` (detecção de stall) e
   `variable_e_min_current: 0.27`.

#### Hipóteses — estado atual

| # | Hipótese | Estado | Evidência |
|---|----------|--------|-----------|
| E | **Engrenagem de tração arrastando no frame da DXC2** (desalinhamento) | **HIPÓTESE LÍDER** | Problema **conhecido** da DXC2, documentado pelo fabricante e por vários usuários (ver "Solução do fabricante"). Engrenagem trava/arrasta no meio da rotação → rouba torque → sub-extrusão com pó. Bate com todos os sintomas. |
| A | **Tensão insuficiente do idler** — engrenagem desliza no filamento | **REBAIXADA** | A patinagem (pó) é fato, mas usuários relatam pó **mesmo com a tensão no mais frouxo** → tensão provavelmente **não** é a causa. Apertar pode até piorar se a engrenagem já arrasta (E). |
| D | **Filamento como causa** — úmido, fora de diâmetro ou ruim | **A INVESTIGAR** | O pó tem a cor dos filamentos usados; testar com **outro filamento** (seco, outra marca) isola. Barato, não exige desmontar. |
| B | **Motor closed-loop perdendo posição / saturando** | Possível, secundária | Config sem bloco `e_*` (indício). Validar pelo `klippy.log` **se** E, A e D forem descartadas. |
| C | **Contrapressão do bico** (vazão/temperatura) | **ENFRAQUECIDA / revisada** | 230 °C não mudou o déficit. Pior: fonte do fórum sugere que **temperatura alta amolece o filamento e facilita o descascamento** pelas engrenagens — o 230 °C pode ter sido contraproducente. Reconsiderar voltar a ~220 °C. |

> **Virada de diagnóstico (fontes externas):** o [Phaetus Issue #3](https://github.com/Phaetus/DXC-2-Extruder/issues/3)
> e threads do fórum Creality descrevem **exatamente** este caso na DXC2:
> engrenagem de tração **arrastando no corpo da extrusora** (hipótese E), com
> sub-extrusão tipo "swiss cheese" no topo — igual às fotos. A causa provável
> **não** é tensão (A): usuários relatam pó mesmo no mais frouxo. Prioridade agora:
> **teste de rotação livre da engrenagem** + solução do fabricante (abaixo). O teste
> de filamento (D) continua valendo como verificação barata em paralelo.
> *Conteúdo das fontes parafraseado para conformidade de licenciamento.*

#### Observação sobre o config (indício, não prova)

A ausência de bloco `e_*` no `motor_control.cfg` **sugere** que o motor do extruder
roda com tuning default do firmware (calibrado para o extruder stock, não para a
DXC2). Isso **manteria a hipótese B viável** se a patinagem (A) não explicar todo o
déficit — mas é indício de config, não medição do motor. Só investigar B depois de
descartar A pelo conserto mecânico.

> **Corrente não é um `run_current` simples de TMC:** o extruder é closed-loop
> gerenciado pelo `nozzle_mcu`. Não há `run_current` de TMC para o extruder. Editar
> PIDs/limites do `motor_control.cfg` às cegas (sem a datasheet do motor da DXC2:
> R, L, Ke) é arriscado — superaquecimento/falha do driver. Só com valores oficiais
> da DXC2.

### Log da investigação (o caminho até o diagnóstico)

| # | Ação | Resultado | Leitura |
|---|------|-----------|---------|
| 1 | Teste Flow Rate CP, perfil partiu de 1.04 | pass1 −20, pass2 −9 → flow efetivo 0.757 | fator ~0.728 (−27%); fotos = sub-extrusão |
| 2 | `rotation_distance` 6.9 (stock) → 6.35 (chute manual) | — | direção certa (mais material) mas sem medir |
| 3 | Voltou para **6.86** (recomendação fabricante DXC2) | — | ponto de partida nominal correto |
| 4 | Extrude 1000 mm **a 16,8 mm/s**, rd=6.86 | entrou **725 mm** (−27,5%) | bate com o −27% do flow test; velocidade alta ⇒ medição contaminada |
| 5 | Calculou e gravou rd = 6.86 × 0.725 = **4.97** | — | **erro**: calibrou em cima de medição contaminada por velocidade |
| 6 | Reteste **a 1 mm/s**, rd=4.97 | **super-extrudou** (entrou mais que o pedido) | 4.97 é baixo demais; confirma que o 725 estava contaminado |
| 7 | Reverteu para **6.86** e rodou teste escalonado (1 / 6 / 16,8 mm/s) | consumo 90 / 70 / 20 mm para 100 pedidos | erro cresce com a velocidade/carga — déficit depende da velocidade |
| 8 | Teste manual (parado) + inspeção dos configs | mordida OK parada; `motor_closed_loop: x,y,e`; sem bloco `e_*` | indícios, não prova; 3 hipóteses em aberto (A/B/C) — ver "Fato vs Hipótese" |
| 9 | Velvet 230 °C + MVS 20→14 aplicados e publicados | — | paliativos aplicados; flow calibration a observar |
| 10 | 2º teste escalonado **a 230 °C** (F60/F360/F1008) | consumo 110 / 70 / 20 mm | a 6/16,8 mm/s **idêntico** ao de 220 °C → temperatura não afeta o déficit sob carga → **hipótese C enfraquecida** |
| 11 | **Pó de filamento observado dentro da extrusora** | debris com as cores das últimas 2 peças | patinagem mecânica **confirmada como mecanismo**; pó colorido (não metálico) ⇒ PLA raspado |
| 12 | **A planejar:** refazer teste escalonado com **outros filamentos** | *(a observar)* | isola **hipótese D (filamento)** — se o déficit some com filamento novo/seco, a causa era o material |
| 13 | Encontrada foto do DXC2 + thread do Reddit + Phaetus Issue #3 + fórum Creality | problema conhecido: **engrenagem arrasta no frame**; parafusos afrouxam com o calor; pó mesmo com tensão frouxa | **hipótese E criada e vira líder**; tensão (A) rebaixada; 230 °C possivelmente contraproducente (C revisada) |

> **Lição travada:** nunca calibrar `rotation_distance` com extrusão em velocidade
> alta. O método do Klipper exige **1 mm/s (F60)**, porque velocidade alta carrega
> o motor/engrenagem e o déficit cresce, disfarçando de erro de calibração. O passo
> 5 (gravar 4.97) foi o erro clássico: medir sujo e cravar. E, neste setup, **nem o
> 1 mm/s era limpo** (10% de déficit já lá).

### Histórico da `rotation_distance`

| Valor  | Origem                               | Situação |
|--------|--------------------------------------|----------|
| 6.9    | `default/` (extruder stock K2)       | referência stock |
| 6.35   | chute manual (tentativa de corrigir sub) | direção ok, sem medir |
| 4.97   | calibração em cima de medição a 16,8 mm/s | **errado** — medição contaminada pela velocidade |
| **6.86** | **recomendação do fabricante da DXC2** | **base nominal — manter até medição limpa** |

> **Regra do Klipper:** `rotation_distance` **menor** = **mais** material por
> rotação. O 6.86 é o valor nominal do fabricante e permanece como base; a
> sub-extrusão **não** se resolve mexendo nesse número enquanto o déficit sob carga
> não for resolvido (Etapa 2). Só revalide/recalibre a `rotation_distance`
> **depois** que o teste escalonado estiver limpo (erro < 1% nas três velocidades).

### Por que a ordem importa

Sub-extrusão tem várias causas (calibração, patinagem mecânica, motor, vazão,
temperatura). Corrigir no flow ratio do slicer antes de isolar a causa física
**mascara** o problema: você grava um flow inflado em cada filamento para compensar
algo que deveria ser resolvido uma vez na máquina. No dia que a máquina for
calibrada, todos os flows ficam errados juntos.

**Ordem obrigatória (de baixo pra cima):**

1. `rotation_distance` do extruder, medida **a 1 mm/s** (base). Valor nominal:
   **6.86**.
2. **Isolar e resolver o déficit de extrusão sob carga** — causa ainda **em aberto**
   (hipóteses A/B/C). Rodar os testes discriminantes da Etapa 2 antes de aplicar
   qualquer correção definitiva; usar paliativos (temperatura/MVS) para destravar.
3. `pressure_advance` (qualidade de cantos, não volume).
4. Flow ratio no slicer (ajuste fino por material, faixa **0.95–1.05**).
5. Gravar o flow ratio calibrado nos YAMLs do FilamentDB.

Nunca pule da etapa 1 direto pro teste de flow. Ele só converge depois que a causa
física do déficit estiver resolvida.

---

## Etapa 1 — Validar/calibrar `rotation_distance` (método do filamento marcado)

Método oficial do Klipper, imune às distorções do teste de parede (perímetros,
temperatura, PA não interferem). Confirma se o **6.86 do fabricante** está certo
para o *seu* conjunto ou se precisa de ajuste fino. Referência:
<https://www.klipper3d.org/Rotation_Distance.html>

### Passo a passo

1. Aqueça o hotend a **220 °C** (PLA) com o filamento carregado e fluindo (purge
   curto antes).
2. Escolha um **ponto de referência fixo** na entrada do extruder (topo do corpo,
   tampa, porca de entrada do tubo). Com caneta, marque o filamento a **120 mm**
   desse ponto. Meça os 120 mm com paquímetro/régua rígida — a precisão aqui
   define a precisão de tudo.
3. No console do Klipper (Fluidd/Mainsail), extrude 100 mm **devagar**:

   ```gcode
   M83          ; extruder em modo relativo
   G1 E100 F60  ; 100 mm a 1 mm/s (lento = não derrapa)
   ```

   Espere terminar (~100 s).
4. Meça a **distância restante** entre a marca e o ponto de referência. No ideal,
   sobrariam 20 mm (120 − 100).
5. Calcule o que **realmente** entrou:

   ```
   mm_reais = 120 − distância_restante_medida
   ```

   - Se `mm_reais < 100` → entrou **menos** que o pedido (sub). A 1 mm/s, parte
     disso ainda pode ser déficit sob carga (ver Etapa 2), não só calibração.
   - Se `mm_reais > 100` → super-extrusão (entrou mais).
6. Calcule a nova `rotation_distance`:

   ```
   nova_rd = rotation_distance_atual × (mm_reais / 100)
   ```

   Partindo de **6.86**:
   - Se `mm_reais = 99–101`: 6.86 está certo → **mantenha 6.86** e vá para a Etapa 2.
   - Se `mm_reais` fora de 99–101 **mesmo a 1 mm/s**: há déficit mesmo devagar.
     **Não recalibre a rd ainda** — primeiro isole a causa na Etapa 2 (se for
     déficit sob carga, mexer na rd só mascara). Só recalibre se a Etapa 2 provar
     que o motor/engrenagem está limpo e o resíduo é puramente de calibração.

   > `mm_reais` **menor** que 100 ⇒ `nova_rd` **desceria** (empurra mais material).
   > `mm_reais` maior ⇒ subiria.

   > **ATENÇÃO (lição do passo 5 do log):** só calcule `nova_rd` a partir de
   > medição feita **a 1 mm/s** e **sem déficit sob carga pendente**. Medir em
   > velocidade alta embute o déficit e leva a valor errado (foi assim que o 4.97 —
   > baixo demais — acabou gravado).

7. Se precisou recalibrar, edite o campo no `[extruder]` de
   `~/git/CrealityK2-PrinterConfig/DXC2/printer.cfg`:

   ```ini
   [extruder]
   rotation_distance: <nova_rd>
   ```

8. Salve e reinicie o firmware:

   ```gcode
   FIRMWARE_RESTART
   ```

9. **Repita os passos 2–6 uma vez** para confirmar. Alvo: `mm_reais` entre **99 e
   101 mm** (erro < 1%), sempre a 1 mm/s.

### Dicas

- Filamento **PLA seco**; úmido ou flexível (TPU) derrapa e falseia a medida.
- `F60` (1 mm/s) é **obrigatório** — velocidade alta carrega o conjunto e, neste
  setup, o déficit cresce, subestimando a extrusão. (Ver log e Etapa 2.)
- Se a DXC2 declarar `gear_ratio` no `[extruder]`, **não** mexa nele; calibre só a
  `rotation_distance`. (Hoje o bloco não declara `gear_ratio`.)

---

## Etapa 2 — Resolver a patinagem mecânica (hipótese líder) e confirmar

Com rd=6.86, a extrusão perde material e o déficit cresce com a velocidade (~30% a
6 mm/s, ~80% a 16,8 mm/s). Fontes externas (Phaetus + fórum Creality) apontam para
**engrenagem de tração arrastando no frame da DXC2 (hipótese E)** como causa
conhecida — não tensão. Esta etapa ataca **E primeiro** (solução do fabricante),
com o teste de filamento (D) em paralelo. **Não** mexa na `rotation_distance` aqui.

### 2.1 — Teste de velocidade escalonada (confirma que o déficit depende da carga)

É o **medidor de progresso** — repita após cada ação e veja o consumo a 16,8 mm/s
subir em direção a 100 mm. A vazio (hotend a 220 °C, filamento carregado, seco),
medindo o consumo real de 100 mm pedidos em três velocidades:

```gcode
M83
G1 E100 F60    ; 1 mm/s   — referência
G1 E100 F360   ; 6 mm/s
G1 E100 F1008  ; 16,8 mm/s — a velocidade que já falhou
```

Meça o consumo real a cada disparo. Deixe o hotend estabilizar antes de cada um.

- Consumo cai conforme a velocidade sobe (ex. real: 90/70/20) → déficit depende da
  carga. **Não diz qual hipótese** (A, B ou C) — use 2.2 para discriminar.
- Os três próximos de 100 → não há déficit sob carga; a sub-extrusão veria de vazão
  ou temperatura (2.3).

Alvo após o conserto: os três regimes consumindo **99–101 mm**.

### 2.2 — Resolver (ordem baseada nas fontes externas)

**Teste de rotação livre (diagnóstico de E — fazer primeiro).** Com o filamento
removido, gire **manualmente** a engrenagem de tração e sinta a rotação ao longo de
uma volta completa:
- Há um **ponto de travamento/arrasto** no meio da rotação → **hipótese E
  confirmada**: a engrenagem raspa no frame. Aplicar a solução do fabricante
  abaixo.
- Rotação **lisa** o tempo todo → E descartada; siga para D (filamento) e A
  (tensão).

#### Solução do fabricante para E (Phaetus Issue #3)

Procedimento relatado pelo fabricante (parafraseado; confirmar os parafusos na
imagem do [Phaetus Issue #3](https://github.com/Phaetus/DXC-2-Extruder/issues/3)):

1. Afrouxe os **dois parafusos** indicados na montagem da engrenagem.
2. Insira a engrenagem de tração e **gire-a** até sentir a rotação ficar **suave**
   (sem o ponto de arrasto).
3. **Reaperte** os dois parafusos nessa posição.

Contexto corroborado por outras fontes do fórum Creality:
- Os parafusos da montagem **afrouxam sozinhos com o ciclo térmico** (~1/4 de volta)
  — verifique e reaperte os três parafusos da montagem se estiverem soltos.
- Usuários relatam pó/descascamento **mesmo com a tensão no mais frouxo** → tensão
  não é a causa provável.

> **Reteste escalonado (F60/F360/F1008) após o ajuste.** Alvo: consumo ~100 mm nos
> três regimes e **sem gerar pó novo**. Esse é o critério de sucesso.

#### Teste do filamento (D) — em paralelo, não exige desmontar

Carregue **outro filamento** (seco, outra marca/lote) e repita o teste escalonado.
Seque o filamento suspeito antes, se possível (PLA ~45–50 °C por 6–8 h).
- Déficit **some** com o filamento novo → a causa era o **filamento (D)**.
- Déficit **persiste** → não é o filamento.

#### Limpar os dentes da engrenagem — fazer de qualquer forma

O pó precisa sair (ele entope os vãos e piora a mordida): escova de cerdas rígidas,
palito ou ar comprimido.

#### Tensão do idler (A) — só se E/D/limpeza não resolverem

Mecanismo típico: parafuso/botão comprime mola que empurra o idler contra o
filamento. **Apertar = mais mordida.** Ajuste **1/4 de volta por vez**, retestando.
Alvo: **mínima** tensão que elimina a patinagem — tensão demais achata o filamento
e piora. **Dado das fontes:** vários usuários resolveram sem mexer (ou até
afrouxando) a tensão — por isso A é última, não primeira.

#### Se, após o teste de filamento (0) e o conserto mecânico (1–4), SOBRAR déficit

Ou seja: nem o filamento (D) nem a extrusora (A) explicam. Aí investigue as
hipóteses secundárias:

- **B — motor closed-loop.** Durante extrude a 16,8 mm/s, olhe o console /
  `klippy.log`: aviso do motor `e` (track error, over-current, stall) → é o
  controlador. O motor roda com tuning default (sem bloco `e_*` no
  `motor_control.cfg`); conserto real = **obter o perfil de motor `e` da DXC2 com o
  fabricante** (`e_motor_param_R/L/Ke`, PIDs, limites de proteção) ou um
  `motor_control.cfg` adaptado. **Não** edite esses valores às cegas (sem datasheet:
  risco de superaquecer o motor / derrubar o driver). Corrente não é `run_current`
  de TMC aqui — o closed-loop gerencia sozinho.
- **C — bico/vazão.** Já enfraquecida (230 °C não mudou nada). Só reconsiderar com
  cold pull se houver sinal de obstrução.

### 2.3 — Paliativos para destravar enquanto a causa não é fechada

Reduzem o dano e permitem imprimir, mas **não** substituem o conserto de E:

1. **Baixar MVS.** Limita a velocidade de extrusão abaixo do ponto onde o déficit
   dispara. **Responsabilidade do filamento, não do processo** — nunca baixe
   velocidade no perfil de processo (steering `filamentdb-rules.md`).
2. **Temperatura — CUIDADO, reavaliar.** Eu havia sugerido subir para 230 °C
   (contrapressão), mas: (a) não mudou o déficit nos testes, e (b) uma fonte do
   fórum Creality indica que **temperatura alta amolece o filamento e facilita o
   descascamento** pelas engrenagens — ou seja, 230 °C pode **piorar** a geração de
   pó. **Recomendação revisada:** voltar a ~220 °C até E estar resolvida, e tratar
   temperatura como variável a testar, não como paliativo garantido.

#### Sobre o MVS

O Voolt3D Velvet estava com `max_volumetric_speed: 20` (agora **14**, teste em
andamento). **20 mm³/s é agressivo para o bico stock 0.4mm da K2** (não é volcano);
faixa realista de PLA em hotend padrão: **10–15 mm³/s**. MVS alto também piora o
déficit: exige vazão que o conjunto não entrega, aumentando a contrapressão.

| Material | MVS anterior (Velvet) | MVS conservador (DXC2 + bico stock) |
|----------|-----------------------|-------------------------------------|
| PLA      | 20 → **14** (em teste) | 10–14                               |
| PETG     | 15–20                 | 8–12                                |

> **Limitação deste paliativo neste setup:** o déficit já aparece a 1 mm/s
> (≈ 2,4 mm³/s para 1.75 mm: `π × 0.875² × 1 ≈ 2,4`). Se até 2,4 mm³/s já há ~10% de
> perda, **baixar MVS reduz a falha mas pode não entregar impressão perfeita** — o
> conserto real depende de qual hipótese (A/B/C) se confirmar. MVS é redução de
> dano, não solução garantida. **O teste atual (230 °C + MVS 14 + flow calibration)
> vai dizer quanto esses paliativos resolvem.**

---

## Etapa 3 — Recalibrar `pressure_advance`

O PA atual (`0.038`) foi **herdado do extruder stock** e não reflete a DXC2. PA
não afeta volume (não resolve sub-extrusão), mas afeta cantos, seams e bleeding.
Recalibre **depois** da `rotation_distance`.

### Opção A — Torre de PA do Creality Print / Orca

Calibration → Pressure Advance. Imprima, escolha a altura com cantos mais limpos,
o valor correspondente vira o novo PA.

### Opção B — `TUNING_TOWER` do Klipper (mais preciso)

```gcode
SET_PRESSURE_ADVANCE ADVANCE=0
TUNING_TOWER COMMAND=SET_PRESSURE_ADVANCE PARAMETER=ADVANCE START=0 FACTOR=.005
```

Imprima um cubo oco alto, meça a altura Z de cantos mais nítidos:

```
PA = START + (FACTOR × altura_Z_boa)
```

Grave em `[extruder] → pressure_advance` no `DXC2/printer.cfg`, `FIRMWARE_RESTART`.

> Faixa esperada para direct drive: PA **0.02–0.06**. Acima disso suspeite de
> mecânica (tensão de polia, filamento úmido).

---

## Etapa 4 — Teste de Flow Rate no Creality Print

Só rode **depois** das etapas 1–3 — em especial, só depois de o **déficit sob carga
(Etapa 2) estar resolvido ou contornado**. Com a causa física resolvida, o flow
ratio deve cair na faixa saudável de PLA (**0.95–1.05**). Se ainda pedir correção
grande (>10%) na direção positiva, o déficit persiste — volte à Etapa 2.

> **Nota sobre o teste atual (230 °C + MVS 14):** rodar o flow calibration agora é
> um teste empírico válido para ver quanto os paliativos resolvem, mas com **duas
> variáveis mudando juntas** — se melhorar, não isola se foi a temperatura ou o MVS.
> Para fins de "destravar e observar", tudo bem; para isolar causa, mude uma de cada
> vez.

### Como o teste do CP funciona (crítico entender)

O teste de Flow Rate do Creality Print (herdado do Orca/Bambu) é **multiplicativo
em dois passos** sobre o flow que está no perfil no momento do teste:

```
flow_final = flow_de_partida × (1 + pass1/100) × (1 + pass2/100)
```

- **pass1** varre em passos grandes (ex.: −20, −10, 0, +10, +20).
- **pass2** refina em passos finos em torno do melhor pass1.
- Os números das placas são **deltas percentuais**, **não** o valor final.
- **Direção:** se o top sai esburacado (sub), o melhor está do lado **positivo**
  (+flow). Se sai inchado/blobbing (super), do lado negativo.

### Procedimento

1. **Zere o flow de partida** antes do teste: no perfil de filamento do CP, use
   `flow_ratio = 1.0`. Assim o resultado já é o valor absoluto a gravar.
2. Filamento de **referência** (Voolt3D Velvet PLA) + perfil `0.20mm Standard PLA`.
3. Rode **pass1**. Escolha a placa com top mais fechado e uniforme (sem gaps, sem
   blobbing). Anote o delta.
4. Rode **pass2** sobre o pass1. Melhor placa, anote o delta.
5. Flow final (partindo de 1.0):

   ```
   flow_final = 1.0 × (1 + pass1/100) × (1 + pass2/100)
   ```

6. Esse `flow_final` é o valor a gravar no YAML do Velvet.

### O que avaliar em cada placa

- **Sub (falta material):** gaps/frestas entre perímetros, pinholes no topo,
  paredes translúcidas, peça frágil. → precisa de **mais** flow (lado +).
- **Super (excesso):** topo inchado/rugoso, blobbing, material empurrado pra cima,
  dimensão externa maior que o CAD. → precisa de **menos** flow (lado −).
- **Certo:** topo liso e fechado, perímetros encostando sem sobra, dimensão no
  alvo.

### Repita por material (opcional)

Flow ratio é específico de bico+extrusora+material. Rode ao menos uma vez por
**tipo** que você usa de verdade (PLA e PETG). Variações de marca dentro do mesmo
tipo costumam ficar em ±2% e não valem teste individual.

---

## Etapa 5 — Gravar o flow ratio nos YAMLs do FilamentDB

Com os valores calibrados (faixa 0.95–1.05 esperada):

1. Edite `flow_ratio` (e `max_volumetric_speed`, se a Etapa 2 indicou vazão) nos
   perfis em `filament-data/*.yaml`.
2. Rebuild + validação:

   ```bash
   .venv/bin/python build.py --validate
   ```

   Confirme **0 violações de severidade ALTA** e as contagens de contrato (steering
   `filamentdb-rules.md`).
3. Publique:

   ```bash
   ./publish.sh
   ```

> **Não** grave flows de compensação de erro físico (mecânico, vazão ou
> temperatura) nos YAMLs. Se a máquina for recalibrada depois, esses valores viram
> erro de extrusão. O YAML guarda o flow ratio **fino por material** e o MVS que o
> **material** aguenta — não o conserto da máquina.

---

## Checklist rápido

- [ ] Etapa 1: `rotation_distance` confirmada a **1 mm/s**; `mm_reais` 99–101 mm (valor nominal: 6.86).
- [ ] `DXC2/printer.cfg` com rd=6.86 + `FIRMWARE_RESTART` (reverter o 4.97 se ainda estiver gravado).
- [ ] **Etapa 2.2 — teste de rotação livre da engrenagem** (sentir ponto de arrasto) → diagnostica hipótese E.
- [ ] **Solução Phaetus (se E):** afrouxar os 2 parafusos, girar a engrenagem até suave, reapertar; reapertar os parafusos da montagem (afrouxam com o calor).
- [ ] **Em paralelo: testar com OUTRO filamento** (seco, outra marca) — hipótese D.
- [ ] **Limpar os dentes da engrenagem** (remover o pó colorido) — de qualquer forma.
- [ ] Reteste escalonado (F60/F360/F1008) buscando consumo ~100 nos três regimes **e sem gerar pó novo**.
- [ ] Só se E/D/limpeza não resolverem: ajustar tensão do idler (A), depois motor (B, `klippy.log`).
- [ ] **Reavaliar a temperatura:** considerar voltar o Velvet de 230 → ~220 °C (230 pode piorar o descascamento).
- [ ] MVS 14 no Velvet (publicado) como redução de dano; flow calibration a observar após o conserto.
- [ ] Etapa 3: `pressure_advance` recalibrado para a DXC2 (faixa 0.02–0.06).
- [ ] Etapa 4: Flow Rate do CP com perfil zerado em 1.0; flow final 0.95–1.05 (lado + se sub).
- [ ] Etapa 5: `flow_ratio`/MVS gravados nos YAMLs; `build.py --validate` 0 violações ALTA; `publish.sh`.

## Referências

- Klipper — Rotation distance: <https://www.klipper3d.org/Rotation_Distance.html>
- Klipper — Pressure advance: <https://www.klipper3d.org/Pressure_Advance.html>
- The Incompetent Craftsman — "Creality K2 Plus Calibrating E Steps - Rotation
  Distance": <https://www.youtube.com/watch?v=HjecuraOoqI> (guia em vídeo usado na
  calibração deste setup).

*Conteúdo técnico das referências do Klipper foi parafraseado para conformidade de
licenciamento. O vídeo é citado como referência de método; nenhum conteúdo dele foi
reproduzido.*
