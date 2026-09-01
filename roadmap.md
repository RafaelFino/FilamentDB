# FilamentDB — Roadmap e Estado do Projeto

> Documento de continuidade. Deve ser atualizado sempre que uma etapa importante da arquitetura, API, coleta de preços, deploy ou integração com LLMs mudar.
> Estado registrado em 2026-08-30/31, durante a conclusão da nova API pública de ingestão de preços.

## 1. Objetivo do projeto

O FilamentDB é o sistema central de catálogo de filamentos, perfis de impressão e dados de estoque/preços. A arquitetura atual separa o catálogo técnico da coleta de preços:

- catálogo principal: `filament.db`;
- histórico de preços: `price-history.db`;
- snapshots de coleta: `price-data/`;
- aplicação web/API existente para consulta humana;
- API pública de ingestão para agentes/LLMs;
- GitHub Actions como orquestrador da coleta automatizada;
- LLM + busca web para localizar ofertas reais;
- deploy no servidor Linux com serviços separados.

## 2. Arquitetura de preços atual

Fluxo pretendido:

```text
GitHub Actions
    |
    v
collect_prices_agent.py
    |
    +--> LLM (atualmente Mistral/Gemini em teste)
    |       |
    |       +--> busca web
    |       +--> normalização das ofertas
    |
    v
POST /v1/agent/offers
    |
    v
API pública de ingestão
    |
    v
price-history.db
    |
    +--> snapshot JSON / price-data
    |
    v
commit/persistência no GitHub
```

A API de ingestão deve permanecer separada da aplicação web principal e ter seu próprio processo/systemd. O `run.sh` e o `update-server.sh` devem continuar tratando as duas aplicações de forma independente.

## 3. Modelo de chaves — REGRA IMPORTANTE

Não voltar ao modelo em que a API ou o agente constroem uma chave de filamento de forma improvisada/dinâmica.

Existem **duas identificações diferentes e intencionais**:

### 3.1 Chave técnica interna

É a identificação estável usada internamente pelo banco/aplicação para referenciar uma entidade de filamento. Ela deve apontar para o registro técnico/cadastral correto e não deve depender de texto apresentado por uma LLM.

Exemplos de componentes que podem participar dessa identidade interna: material/tipo, fabricante, linha/modelo/qualidade e identificadores técnicos do cadastro.

A regra é: **a chave técnica é propriedade do catálogo e não deve ser recriada pelo collector.**

### 3.2 Chave de correlação de ofertas

As ofertas encontradas na web precisam de uma chave semântica/canônica para correlacionar o produto comercial encontrado com o cadastro do FilamentDB.

Essa chave é baseada nos atributos acordados para correlação, especialmente:

```text
nome | tipo/material | fabricante | qualidade/linha (quando aplicável)
```

A normalização deve ser determinística (case folding, espaços e demais normalizações previstas pelo projeto), mas a chave deve ser **derivada do cadastro**, não inventada de forma independente pela LLM.

### 3.3 Regra de ouro

- `technical/internal key` = identidade estável do FilamentDB.
- `offer correlation key` = chave canônica para relacionar produto/oferta externa ao cadastro.
- `offer_key` = identidade da oferta específica, incluindo loja/produto/identificador externo conforme o schema de preços.

Nunca misturar essas três coisas.

Antes de alterar qualquer código que lide com `filament_key`, consultar este documento e o schema vigente.

## 3.4 Contrato implementado no catálogo da API

A API expõe duas identificações para o agente: `technical_key`, derivada da identidade interna do registro (`filament_profiles.id`), e `filament_key`, que é a chave canônica persistida de correlação usada para relacionar ofertas externas ao catálogo.

O `tracking` é uma flag explícita do cadastro: `tracking=1` significa que queremos pesquisar preços daquele filamento; `tracking=0` significa que ele não entra na coleta. Collector, API e validator devem respeitar essa flag.

O collector deve usar o `filament_key` persistido fornecido pelo catálogo/API; ele não deve reconstruir a chave a partir de material/fabricante/linha. O schema gerado por `build.py` já possui `filament_key` e `tracking`; artefatos antigos do banco podem não possuir essas colunas, por isso o workflow precisa executar o build do catálogo antes da coleta.

Esta distinção deve ser preservada em futuras alterações.

## 4. O que já foi feito

### API de ingestão

- Criada a nova API para receber ofertas produzidas pelo agente/LLM.
- Endpoint de health implementado.
- Endpoint de catálogo/consulta preparado para uso do agente.
- Endpoint de ingestão de ofertas implementado.
- Validação e normalização de valores vindos de LLM foram endurecidas.
- Foram tratados valores como `R$ 89,90`, `sim/não`, `1 kg`, `3 rolos`, `por unidade`, etc.
- Testes de resiliência da API foram restaurados.
- A API possui serviço/systemd próprio e script `scripts/run-api.sh`.

### Collector / agente

- Collector de preços integrado ao GitHub Actions.
- Agente foi endurecido contra timeouts e falhas de busca web.
- Assinaturas/chamadas do Gemini foram corrigidas.
- O fluxo de coleta foi testado com Mistral e Gemini.
- Durante os testes, provedores gratuitos como Groq, Z.ai, Cerebras e OpenRouter consumiram seus créditos disponíveis; eles devem voltar posteriormente como fallback, não necessariamente como primeira opção.

### Deploy

- Servidor foi atualizado com a versão mais recente antes desta fase de validação.
- `update-server.sh` foi preparado para atualizar a aplicação e preservar os dados.
- A API possui processo separado da aplicação web.
- Scripts de inicialização devem manter permissões executáveis (`chmod +x`) após qualquer alteração.

### Testes recentes

- Houve testes reais usando Mistral e Gemini.
- O próximo passo é validar o fluxo completo contra a versão atualmente instalada no servidor, antes de ampliar o catálogo e reativar todos os fallbacks.

## 5. Situação atual / ponto exato da retomada

O código está no commit mais recente relacionado à API resiliente, atualmente em torno de:

- `fix: restore resilient API implementation`
- `fix: restore API resilience tests`

A validação do deploy ainda é a etapa crítica.

### Ordem obrigatória da próxima sessão

1. Confirmar que a API está saudável no servidor atualizado.
2. Fazer uma ingestão real controlada usando o agente/LLM.
3. Confirmar resposta HTTP da API.
4. Confirmar que a oferta foi persistida em `price-history.db`.
5. Confirmar que a correlação com o catálogo usa as chaves corretas.
6. Confirmar snapshot/resultado da coleta.
7. Executar o workflow do GitHub Actions e analisar logs.
8. Só depois liberar a consulta do catálogo completo de filamentos.
9. Só depois reativar os demais provedores de LLM como fallback.

## 6. Estratégia de LLMs

Provedores configurados no GitHub incluem, conforme o ambiente atual:

- Mistral — atualmente respondendo e deve ser usado durante a validação;
- Gemini — ainda possui aproximadamente créditos pagos disponíveis e deve ser usado com cautela;
- Groq — configurado, mas créditos free consumidos durante os testes;
- Z.ai — configurado, créditos free consumidos durante os testes;
- Cerebras — configurado, mas créditos free consumidos durante os testes;
- OpenRouter — configurado, mas créditos free consumidos durante os testes.

A ordem de fallback deve ser configurável por variável do workflow, sem acoplar a persistência a um provedor específico.

## 7. Workflow e dependências

O workflow `.github/workflows/price-collector.yml` instala `requirements.txt`, incluindo `PyYAML`, antes de executar `build.py --only-db`. O build é obrigatório antes da coleta para produzir o banco de catálogo atual.

O workflow recebe `limit` para permitir testes controlados. `limit=1` é a estratégia recomendada enquanto o fluxo ponta a ponta não estiver validado.

## 8. Coleta e qualidade dos preços

A coleta deve continuar registrando loja/fonte, URL, título encontrado, preço, preço original, frete, preço total, moeda, disponibilidade, quantidade de rolos/unidades, peso unitário, base do preço, vendedor, identificador externo, data/hora, status e observações/falhas.

A UI deve continuar podendo mostrar **todas as ofertas encontradas**, e não somente a melhor oferta.

## 9. Fontes de preço previstas

Fontes monitoradas/planejadas incluem Amazon.com, AliExpress, Shopee, Mercado Livre, Voolt3D, 3D Lab, Filamentos3D Brasil e sites oficiais dos fabricantes quando relevantes.

Marcas prioritárias: Voolt3D, 3DLab, Sunlu, eSun, Elegoo e Creality. Materiais prioritários: PLA e PETG, com atenção especial a linhas premium, matte/velvet e produtos de boa qualidade.

## 10. Regras importantes para marketplaces

Não assumir que o preço exibido é sempre de um rolo. Distinguir preço por unidade, kit/multipack, quantidade de rolos, peso por rolo, preço total e frete. Preservar a informação original mesmo após normalização.

## 11. Histórico e persistência

`price-history.db` é o banco de histórico e não deve ser confundido com o catálogo principal. Snapshots JSON em `price-data/` servem como artefato auditável. Não apagar ou substituir dados históricos simplesmente para corrigir uma coleta nova.

## 12. Deploy no servidor

Scripts relevantes: `scripts/update-server.sh`, `scripts/run.sh`, `scripts/run-api.sh`, `systemd/filamentdb-api.service`.

Sempre que scripts forem alterados: `chmod +x scripts/*.sh`.

## 13. Backlog

### P0 — concluir agora

- [ ] Validar API no servidor atualizado.
- [ ] Validar ingestão real com Mistral.
- [ ] Validar ingestão real com Gemini sem consumir créditos excessivos.
- [ ] Confirmar persistência no `price-history.db`.
- [ ] Confirmar correlação usando as duas camadas de chave corretas.
- [ ] Executar e estabilizar GitHub Actions de coleta.
- [ ] Corrigir qualquer problema encontrado no fluxo ponta a ponta.

### P1 — imediatamente após validação

- [ ] Liberar consulta para todos os filamentos.
- [ ] Reativar Groq, Z.ai, Cerebras e OpenRouter como fallbacks.
- [ ] Implementar/confirmar ordem de fallback por disponibilidade/custo.
- [ ] Melhorar logs de escolha/falha de provedor.
- [ ] Garantir que nenhum secret seja impresso.
- [ ] Rodar coleta em escala maior.

### P2 — qualidade e produto

- [ ] Melhorar relatório de coleta.
- [ ] Garantir visualização de todas as ofertas.
- [ ] Consolidar estoque/quantidade por filamento.
- [ ] Mostrar múltiplas cores disponíveis.
- [ ] Ordenar preços por material e fabricante.
- [ ] Revisar normalização de kits/unidades/peso/preço.
- [ ] Melhorar histórico e comparações de preço.

### P3 — manutenção

- [ ] Manter `roadmap.md` atualizado.
- [ ] Documentar mudanças de schema antes de alterar queries.
- [ ] Criar testes de contrato entre collector, API e banco.
- [ ] Adicionar testes de integração do workflow.
- [ ] Revisar periodicamente limites/custos dos provedores LLM.

## 14. Problemas que já apareceram e lições

### Caminho de banco hardcoded

Problema: código dependia de caminhos absolutos como `/srv/FilamentDB`.

Solução: usar configuração de caminho para permitir execução local e no servidor.

### Encoding

Problema: textos como `preÃ§o` apareceram na UI. Solução: garantir UTF-8 de ponta a ponta.

### Schema divergente

Problema: queries assumiram colunas que não existiam no schema vigente. Lição: sempre consultar o schema real antes de criar uma query nova.

### Preços 100x menores

Problema: erro de cálculo/normalização. Lição: separar preço, quantidade, peso e base do preço.

### API / histórico

Problema anterior: endpoint de histórico apresentou erro 500. Lição: manter testes de API e banco sincronizados.

### Chaves de filamento

Problema: risco de construir `filament_key` dinamicamente a partir de strings diferentes. Solução: chave técnica interna estável + chave canônica de correlação.

**Não reintroduzir o modelo antigo sem atualizar este documento.**

## 14.5 Incidente de 2026-08-30/31 — tracking e banco desatualizado

O primeiro teste após a publicação da API falhou na validação do snapshot porque o validator consultava uma coluna `tracking` que não existia no artefato antigo. O schema produzido por `build.py` já define `filament_key` e `tracking`, e o workflow passou a reconstruir o banco antes da coleta.

No teste seguinte, a API corretamente respondeu `404 unknown_or_untracked_filament` porque o perfil controlado ainda estava com `tracking=0`.

### Solução

- `tracking` permanece como **opt-in de coleta de preços**.
- `filament_key` é persistido no catálogo e fornecido ao collector/LLM.
- Collector e validator filtram `tracking=1`.
- Workflow executa `python build.py --only-db` antes da coleta.
- O teste controlado usa PETG XT Line da 3DFila com `tracking: 1`.
- A expansão deve ser deliberada pela flag `tracking`.

O erro `429` do Mistral é independente e deve ser tratado por fallback.

## 14.6 Incidente de 2026-08-31 — dependência PyYAML ausente no GitHub Actions

`build.py` falhou com `ModuleNotFoundError: No module named 'yaml'`. `requirements.txt` já declarava `PyYAML>=6.0`, mas o workflow não instalava o arquivo.

### Solução

O passo de dependências passou a executar:

```bash
python -m pip install --upgrade -r requirements.txt openai ddgs
```

## 14.7 Incidente de 2026-08-31 — collector apontava para o banco errado

Após o build confirmar `data/filament.db`, o collector falhou com `no such column: fp.filament_key`. A causa foi uma divergência de caminho: `build.py` produz `data/filament.db`, mas o collector apontava para `ROOT/filament.db`.

### Correção

O collector agora usa `ROOT / "data" / "filament.db"`, exatamente o banco produzido pelo build. `tracking` continua como opt-in e `filament_key` continua vindo do catálogo persistido.

Foi adicionado teste de regressão para o caminho do catálogo.

### Incidente durante a aplicação da correção

Uma primeira tentativa automática substituiu indevidamente o conteúdo completo do collector por uma implementação incompleta. Isso foi identificado antes de novo teste. O arquivo foi restaurado a partir da versão testada anterior e a correção final foi reaplicada de forma mínima. O roadmap registra esse incidente para rastreabilidade.

## 15. Critério de pronto da fase atual

A fase de API/preços só deve ser considerada concluída quando healthcheck, ingestão real, validação/normalização, persistência, chaves, workflow, snapshot, consulta e pelo menos dois provedores LLM estiverem validados.

## 16. Próximo passo imediato

**Não ampliar o escopo ainda.** Executar uma coleta pequena e controlada contra a API instalada no servidor. Se passar, ampliar progressivamente.

A próxima sessão deve começar lendo este `roadmap.md` e os documentos `API-INGEST.md`, `PRICE-COLLECTOR.md` e `PRICE_AGENT.md`, depois verificar o último workflow do GitHub Actions.


## 2026-09-01 — incidente: API de instruções devolvia prompts vazios

### O que deu errado
- O primeiro run real observado no Actions ainda não teve sucesso.
- O build do catálogo funcionou: `data/filament.db` foi recriado com 98 perfis e 26 perfis com `tracking=1`.
- O collector chamou `/v1/agent/instructions?filament_key=...`, mas a API retornava as regras estruturadas sem `system_prompt` e `user_prompt`.
- O collector usava strings vazias como fallback para esses campos; o Mistral rejeitou a requisição com HTTP 400: `No messages contain any content`.
- Isso significa que o problema estava no contrato API → agente, antes de qualquer pesquisa web ou publicação de oferta.

### Correção aplicada
- O endpoint `/v1/agent/instructions` agora exige `filament_key` e retorna `system_prompt` e `user_prompt` não vazios, contextualizados para a chave solicitada.
- A versão do contrato de instruções foi elevada para `3`.
- Foi adicionado teste de regressão para garantir prompts não vazios e presença da chave solicitada no prompt.
- `tracking=1` continua sendo o opt-in oficial para coleta; `tracking=0` permanece fora do catálogo de coleta.
- `filament_key` continua sendo a chave canônica persistida de correlação; o collector não a reconstrói.

### Estado
- O código da API foi corrigido no repositório.
- **O servidor precisa receber esta versão antes do próximo teste**, porque `/v1/agent/instructions` é servido pela API em produção.
- O workflow ainda deve ser testado novamente somente depois do update do servidor.
