# Contrato do agente de preços

Este documento é o contrato operacional para qualquer agente que faça a coleta diária do FilamentDB.

## 1. Descobrir o catálogo

Leia o `filament.db` e selecione somente perfis com `tracking = 1`. Nunca invente `filament_key`. A chave canônica já existe no catálogo. Para cada perfil, considere as cores/variantes disponíveis quando forem relevantes para a busca.

## 2. Escopo

Priorizar PLA e PETG de alta qualidade: linhas Premium, Matte, Velvet ou equivalentes claramente posicionadas como premium. Fabricantes prioritários: Voolt3D, 3D Lab, F3D, Sunlu, eSUN, Elegoo e Creality. Fontes: lojas oficiais conhecidas e Mercado Livre, Amazon, Shopee e AliExpress.

## 3. Pesquisar todas as ofertas

A meta é **massa de dados**, não uma única recomendação. Para cada combinação pesquisada, registre todas as ofertas relevantes e confiáveis encontradas. Inclua preços normais, promocionais, cupons quando observáveis, frete quando observável e diferentes quantidades/kits.

Não descarte uma oferta porque ela não é a mais barata. A aplicação calculará ranking, mediana, melhor histórico e oportunidade.

## 4. Kits e quantidade

Preserve a forma comercial: quantidade de rolos e peso unitário. Exemplo: `2 x 1 kg por R$ 189,90`. Não transforme isso em uma oferta de 1 kg. A aplicação normaliza R$/kg para comparação.

## 5. Identidade

Antes de gravar uma oferta, valide:

1. `filament_key` pertence ao catálogo;
2. fabricante do título/produto é compatível com a chave;
3. cor pertence ou pode ser associada à variante;
4. loja e URL correspondem ao produto;
5. preço e moeda estão claros.

Nunca associe uma oferta Elegoo a uma chave Voolt3D, nem o contrário.

## 6. Link

Use o link direto da oferta. Não registre URL de página de busca ou redirecionador quando não for possível identificar a oferta final.

## 7. O que não foi encontrado

Para cada fonte/escopo pesquisado, registre resultado `found` ou `not_found`. Se a pesquisa encontrou páginas mas não um link direto confiável, use `not_found` e explique isso em `notes`. Assim a UI mostra tanto o que foi encontrado quanto o que não foi.

## 8. Snapshot

Gere exatamente um arquivo por dia: `data/price-data/YYYY-MM-DD.json`. O arquivo deve conter todas as ofertas daquela coleta e a seção `collection` com o log de fontes. Não sobrescreva snapshots anteriores.

## 9. Publicação

Valide JSON e chaves antes de publicar. Faça commit/push apenas do snapshot e eventuais artefatos de relatório/documentação gerados pela coleta. O servidor não executa pesquisa: ele apenas baixa o Git e projeta os snapshots no SQLite.
