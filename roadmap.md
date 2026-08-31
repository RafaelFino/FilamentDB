# FilamentDB — Roadmap e Estado do Projeto

> Documento de continuidade. Deve ser atualizado sempre que uma etapa importante da arquitetura, API, coleta de preços, deploy ou integração com LLMs mudar.
>
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

A API expõe duas identificações para o agente: `technical_key`, derivada da identidade interna do registro (`filament_profiles.id`), e `filament_key`, que é a chave canônica de correlação usada para relacionar ofertas externas ao catálogo.

O collector deve usar `filament_key` fornecido pelo catálogo/API; ele não deve reconstruir uma chave técnica interna. A validação do snapshot usa a mesma expressão canônica do catálogo e não depende de uma coluna `tracking`, que não existe no schema atual de `filament_profiles`.

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
- Cerebras — configurado, créditos free consumidos durante os testes;
- OpenRouter — configurado, créditos free consumidos durante os testes.

Quando o fluxo principal estiver comprovadamente estável, voltar para uma estratégia de fallback ordenada, com:

1. timeout curto por provedor;
2. detecção de erro/rate limit/quota;
3. tentativa do próximo provedor;
4. logs identificando o provedor utilizado e motivo do fallback;
5. nunca expor secrets nos logs;
6. evitar consumir provedores pagos desnecessariamente durante testes.

A ordem definitiva deve ser definida após medir custo, disponibilidade, qualidade da busca e limites de cada provedor.

## 7. Expansão do catálogo de consulta

Durante a fase de validação, manter o escopo pequeno para reduzir custo e facilitar diagnóstico.

Depois de confirmar uma coleta ponta a ponta:

- liberar a consulta para todos os filamentos elegíveis;
- garantir paginação/limites para não estourar contexto ou tempo da LLM;
- agrupar consultas de forma eficiente;
- registrar o que foi consultado, encontrado e não encontrado;
- manter rastreabilidade por `filament_key`/chave de correlação.

## 8. Coleta e qualidade dos preços

A coleta deve continuar registrando:

- loja/fonte;
- URL;
- título encontrado;
- preço;
- preço original, quando houver;
- frete;
- preço total, quando calculável;
- moeda;
- disponibilidade;
- quantidade de rolos/unidades;
- peso unitário;
- base do preço (`unit`, `total`, etc.);
- vendedor, quando aplicável;
- identificador externo, quando disponível;
- data/hora da coleta;
- status da coleta por filamento/fonte;
- observações e falhas.

A UI deve continuar podendo mostrar **todas as ofertas encontradas**, e não somente a melhor oferta.

## 9. Fontes de preço previstas

Fontes monitoradas/planejadas incluem:

- Amazon.com
- AliExpress
- Shopee
- Mercado Livre
- Voolt3D
- 3D Lab
- Filamentos3D Brasil (especialmente F3D)
- sites oficiais dos fabricantes quando relevantes

Marcas prioritárias já discutidas incluem Voolt3D, 3DLab, Sunlu, eSun, Elegoo e Creality.

Materiais prioritários: PLA e PETG, com atenção especial a linhas premium, matte/velvet e produtos de boa qualidade.

## 10. Regras importantes para marketplaces

Não assumir que o preço exibido é sempre de um rolo.

A coleta deve distinguir:

- preço por unidade;
- kit/multipack;
- quantidade de rolos;
- peso por rolo;
- preço total do anúncio;
- frete.

Uma oferta de kit pode ser melhor que uma oferta unitária depois da normalização, mas a informação original deve ser preservada.

## 11. Histórico e persistência

`price-history.db` é o banco de histórico e não deve ser confundido com o catálogo principal.

Snapshots JSON em `price-data/` servem como artefato auditável da coleta e como entrada para o processo de atualização/importação do servidor.

Não apagar ou substituir dados históricos simplesmente para corrigir uma coleta nova.

## 12. Deploy no servidor

Scripts relevantes:

- `scripts/update-server.sh`
- `scripts/run.sh`
- `scripts/run-api.sh`
- `systemd/filamentdb-api.service`

Sempre que scripts forem alterados:

```bash
chmod +x scripts/*.sh
```

O deploy deve:

1. atualizar código;
2. preservar banco/dados;
3. atualizar dependências quando necessário;
4. reiniciar o serviço correto;
5. validar healthcheck;
6. deixar a aplicação web e a API funcionando independentemente.

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

- [ ] Melhorar relatório de coleta: encontrados, não encontrados e falhas.
- [ ] Garantir visualização de todas as ofertas.
- [ ] Consolidar visualização de estoque/quantidade por filamento quando aplicável.
- [ ] Mostrar múltiplas cores disponíveis para uma mesma chave de filamento.
- [ ] Ordenar preços por material e fabricante.
- [ ] Revisar normalização de kits/unidades/peso/preço.
- [ ] Melhorar histórico e comparações de preço.

### P3 — manutenção

- [ ] Manter `roadmap.md` atualizado.
- [ ] Documentar mudanças de schema antes de alterar queries.
- [ ] Criar testes de contrato entre collector, API e banco.
- [ ] Adicionar testes de integração do workflow quando possível.
- [ ] Revisar periodicamente limites/custos dos provedores LLM.

## 14. Problemas que já apareceram e lições

### Caminho de banco hardcoded

Problema: código dependia de caminhos absolutos como `/srv/FilamentDB`.

Solução: usar configuração de caminho (`DB_PATH`/configuração central) para permitir execução local e no servidor.

### Encoding

Problema: textos como `preÃ§o` apareceram na UI.

Solução: garantir UTF-8 de ponta a ponta e revisar arquivos/headers quando alterações de texto forem feitas.

### Schema divergente

Problema: queries assumiram colunas que não existiam no schema vigente.

Lição: sempre consultar o schema real antes de criar uma query nova. Não inferir nomes de colunas a partir de versões antigas do projeto.

### Preços 100x menores

Problema: erro de cálculo/normalização de preço em determinadas ofertas.

Lição: separar preço do anúncio, quantidade, peso e base do preço; testar unitário versus total explicitamente.

### API / histórico

Problema anterior: endpoint de histórico apresentou erro 500 e a UI informou que não conseguia carregar o histórico.

Lição: manter testes de API e de banco sincronizados com o schema e testar também a integração completa.

### Chaves de filamento

Problema: risco de construir `filament_key` dinamicamente a partir de strings diferentes entre collector, API e banco.

Solução arquitetural: manter uma chave técnica interna estável e uma chave canônica de correlação de ofertas, com responsabilidades separadas.

**Não reintroduzir o modelo antigo sem atualizar este documento.**

## 15. Critério de pronto da fase atual

A fase de API/preços só deve ser considerada concluída quando:

- healthcheck da API responde corretamente;
- uma oferta real chega pela API;
- a oferta é validada/normalizada;
- a oferta é persistida;
- a chave técnica e a chave de correlação permanecem corretas;
- o workflow termina sem erro;
- o snapshot é produzido;
- a aplicação consegue consultar o resultado;
- pelo menos dois provedores LLM foram validados;
- fallback pode ser reativado sem alterar a lógica de persistência;
- uma coleta em escala maior é possível sem intervenção manual.

## 16. Próximo passo imediato

**Não ampliar o escopo ainda.** Primeiro executar uma coleta pequena e controlada contra a API instalada no servidor. Se passar, ampliar progressivamente.

A próxima sessão deve começar lendo este `roadmap.md` e os documentos `API-INGEST.md`, `PRICE-COLLECTOR.md` e `PRICE_AGENT.md`, depois verificar o último workflow do GitHub Actions e seguir a seção 5 deste documento.
