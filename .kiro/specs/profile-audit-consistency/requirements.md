# Requirements — Audit, Comparação com Baseline e Validação de Perfis K2

## Introdução

Este documento especifica o trabalho de (1) auditar a consistência interna do
pipeline de geração de perfis do FilamentDB, (2) comparar nossos perfis com os
perfis padrão (stock) da Creality K2 como linha de base para identificar
conservadorismo injustificado, e (3) aplicar as correções acordadas, fechando
com uma camada de **validação automatizada** que impede regressão da classe de
bug que motivou este trabalho (`initial_layer_print_height` não múltiplo do
`layer_height`, causando warning de layer height na prime tower).

O escopo cobre o ciclo completo: achados → decisão → remediação → guarda
automática. A fonte de verdade continua sendo `process-base/`; nenhuma correção
é feita em arquivos gerados (`Creality-Print/`, `OrcaSlicer/`), que o `build.py`
sobrescreve.

### Contexto arquitetural (invariável)

- Fonte de verdade: `process-base/{base.json, materials/, profile_types/,
  layer_heights/, devices/, combinations.json}`.
- `build.py` combina `base < layer_height < profile_type`, aplica overrides de
  adesão (`ADHESION_OVERRIDE_FIELDS`), aplica velocidades do material com
  multiplicadores do profile type, capa por device (`limits`), resolve herança
  do slicer e exporta.
- Filosofia (steering `filamentdb-rules.md`): MVS é exclusivo do filamento; cap
  de velocidade/aceleração é exclusivo do device; bases PLA/PETG recalibradas
  conservadoras de propósito. Conservador ≠ bug — mas conservadorismo sem motivo
  é alvo de correção.

### Critério de aceite guia (prioridade de decisão)

Toda decisão de valor nesta spec é um controle entre três pilares — **economia
de material, qualidade visual e velocidade de impressão** — mediado por dois
limites inegociáveis: respeitar os limites físicos da impressora e não
desperdiçar sua capacidade. Cada perfil deve usar o melhor do que a máquina
oferece dentro da sua intenção.

Regras de desempate, nesta ordem:

1. **Segurança de impressão e qualidade da peça vencem sempre.** Quando os
   pilares conflitam, fica-se com o que garante a impressão bem-sucedida e a
   integridade/qualidade da peça — nunca empurrar velocidade a ponto de arriscar
   falha, under-extrusion ou perda de qualidade.
2. **Não desperdiçar a máquina.** Dentro da margem de segurança, usar o máximo
   que o device e o MVS do filamento permitem — ser conservador *sem motivo* é
   defeito tanto quanto ultrapassar limites.
3. **Respeitar a intenção do perfil.** O alvo de cada profile type define onde,
   no espectro qualidade↔velocidade, ele deve cair (ver Requisito 5).

O **Standard** é o ponto de equilíbrio: busca o melhor dos três pilares
simultaneamente (economia + qualidade visual + velocidade), e em caso de
conflito cede para segurança e qualidade da peça.

---

## Requisitos

### Requisito 1 — Audit de consistência interna

**User Story:** Como mantenedor do FilamentDB, quero uma varredura sistemática de
todo o pipeline que encontre inconsistências estruturais, para que eu corrija a
classe inteira de problemas de uma vez e não só o sintoma reportado.

#### Acceptance Criteria

1. QUANDO a auditoria roda ENTÃO o sistema DEVE verificar, para todo
   `layer_heights/*.json`, que `initial_layer_print_height` é múltiplo inteiro
   de `layer_height` (razão com tolerância de ponto flutuante).
2. QUANDO qualquer `profile_type` ou `material` sobrescreve
   `initial_layer_print_height` ou `layer_height` ENTÃO a auditoria DEVE
   detectar e reportar o override, pois `ADHESION_OVERRIDE_FIELDS` promove o
   maior valor e pode reintroduzir o desalinhamento.
3. QUANDO a auditoria avalia cada combinação gerada ENTÃO ela DEVE confirmar que
   nenhuma velocidade de extrusão/travel nem aceleração resultante ultrapassa os
   `limits` do device correspondente (k2: 600/800/20000; cc2: 500/500/20000).
4. QUANDO a auditoria avalia os multiplicadores dos profile types ENTÃO ela DEVE
   confirmar que `valor_gerado == base_material × multiplicador` (com
   `quality_speed` nos campos de `QUALITY_SPEED_FIELDS`) dentro de tolerância, e
   sinalizar dupla penalização.
5. QUANDO a auditoria avalia prime tower / flush / suportes / shells ENTÃO ela
   DEVE reportar valores incoerentes (ex.: `support_top_z_distance` <
   `layer_height`; `top_shell_thickness` ≠ `top_shell_layers × layer_height`).
6. QUANDO a auditoria avalia a herança do slicer ENTÃO ela DEVE confirmar que
   todo `inherits` resolvido aponta para um perfil-pai existente no slicer alvo.
7. QUANDO a auditoria avalia `combinations.json` ENTÃO ela DEVE confirmar que
   todo device referenciado tem arquivo em `devices/` e que a contagem de perfis
   bate com o documentado (86 processos; 84 export Creality por cc2 Orca-only).
8. O resultado DEVE listar cada achado com: caminho de arquivo, valor exato,
   severidade (alto/médio/baixo) e correção sugerida — sem aplicar nada.

### Requisito 2 — Comparação com perfis padrão (baseline)

**User Story:** Como usuário que quer aproveitar a K2 ao máximo, quero comparar
nossos perfis com os perfis stock (Creality Print e OrcaSlicer System) para
saber onde estamos conservadores demais sem justificativa.

#### Acceptance Criteria

1. A comparação DEVE usar como baseline **ambas** as fontes stock instaladas:
   Creality Print 7.3 (`~/.config/Creality/Creality Print/7.3/system/Creality/`
   e os stock em `.../user/8401264742/process/`) e OrcaSlicer System
   (`~/.config/OrcaSlicer/system/Creality/process/`, K2 0.4 nozzle base).
2. A comparação DEVE distinguir perfis nossos (sufixo `- PLA`/`- PETG`) dos
   stock (sem sufixo de material).
3. Para o profile type **Standard** (PLA e PETG, alturas 0.16/0.20/0.24), a
   comparação DEVE produzir, por parâmetro divergente, uma tabela: parâmetro |
   nosso valor | Creality stock | Orca System | delta | comentário.
4. O comentário DEVE classificar cada divergência como "conservador e correto"
   (justificado por MVS/filosofia) ou "conservador desperdiçando capacidade",
   considerando o MVS dos filamentos premium do usuário (Voolt3D Velvet MVS=25,
   Sunlu HS MVS=22 — `filament-data/*.yaml`).
5. QUANDO houver dúvida sobre o recomendado para a K2 ENTÃO o relatório DEVE
   consultar fontes oficiais (Creality, docs OrcaSlicer) e citar as URLs.

### Requisito 3 — Remediação acordada

**User Story:** Como mantenedor, quero aplicar as correções priorizadas na
fonte de verdade e republicar, para que os perfis instalados fiquem corretos.

#### Acceptance Criteria

1. As correções DEVEM ser aplicadas apenas em `process-base/` (nunca em
   arquivos gerados).
2. CADA correção de conservadorismo (Parte 2) DEVE ser aprovada explicitamente
   pelo usuário antes de aplicar — divergências com baseline são dados para
   decisão, não correção automática.
3. As correções de consistência (Parte 1, severidade alta) DEVEM ser aplicadas
   sem alterar a filosofia de separação processo/filamento/device.
4. APÓS aplicar ENTÃO o sistema DEVE rodar `build.py` e confirmar que a geração
   conclui sem erro e que a contagem de perfis permanece a esperada.
5. A publicação para o Creality Print DEVE usar `publish.sh` (com backup
   automático) seguido do runner `~/run-creality-print.sh`, executado pelo
   usuário.

### Requisito 4 — Validação automatizada (guarda contra regressão)

**User Story:** Como mantenedor, quero uma checagem automática de invariantes que
rode no build e no CI, para que a classe de bug corrigida nunca mais passe
despercebida.

#### Acceptance Criteria

1. O sistema DEVE expor um validador (script Python ou módulo chamado pelo
   `build.py`) que verifica as invariantes do Requisito 1 (itens 1–7) sobre os
   perfis gerados em memória, antes do export.
2. QUANDO uma invariante é violada ENTÃO o validador DEVE falhar com exit code
   não-zero e mensagem citando arquivo-fonte, invariante violada e valores.
3. O validador DEVE ser determinístico e sem efeitos colaterais (read-only sobre
   os dados; não escreve perfis).
4. O validador DEVE ser integrado ao CI (`.github/workflows/ci.yml`) como passo
   obrigatório.
5. O validador DEVE ter testes cobrindo pelo menos: caso válido, violação de
   múltiplo de layer height, e velocidade acima do cap do device.

### Requisito 5 — Intenção de cada profile type (alvo no espectro qualidade↔velocidade)

**User Story:** Como mantenedor, quero que cada profile type tenha uma intenção
explícita no espectro qualidade↔velocidade↔economia, para que decisões de valor
(especialmente conservadorismo) sejam julgadas contra o alvo do perfil, não
contra um número arbitrário.

#### Acceptance Criteria

1. CADA decisão de valor DEVE ser avaliada contra a intenção do profile type
   conforme a steering `filamentdb-rules.md`:
   - **Fast**: velocidade máxima, aceita perda de qualidade.
   - **Economy**: economia de material via estrutura mínima; velocidade = Standard.
   - **Factory**: fábrica conservador (0.65x) com brim sempre ligado.
   - **Standard**: equilíbrio dos três pilares; em conflito, segurança/qualidade.
   - **Strong**: resistência mecânica (6 walls, 50% infill).
   - **Detail**: qualidade visual máxima (quality_speed 0.45).
   - **Safe**: ultra-conservador para 1ª impressão / material desconhecido.
   - **LW-Structure / LW-Extreme**: peças leves de aeromodelo (estrutura reduzida).
2. QUANDO um ajuste melhora um pilar às custas da intenção do perfil ENTÃO ele
   NÃO DEVE ser aplicado (ex.: não acelerar o Safe a ponto de perder confiança;
   não deixar o Detail rápido ao ponto de perder acabamento).
3. O ajuste de conservadorismo do Standard (Req 2/3) DEVE preservar a 1ª camada
   conservadora (segurança de adesão) mesmo ao subir superfícies visíveis —
   decidido via base do material, não via `quality_speed` compartilhado.
