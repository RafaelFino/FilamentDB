# FilamentDB — Roadmap Mobile

Roteiro e registro de decisões para levar o FilamentDB ao celular (Android).
Este é o documento canônico: reúne o **porquê** de cada escolha e o **o quê**
falta fazer, para que qualquer sessão futura (ou pessoa) retome sem reconstruir
o contexto.

> Features do **servidor** (ex: autorização de escrita do estoque) ficam em
> [`next-steps.md`](next-steps.md), não aqui. A autorização vale tanto para o
> web quanto para o mobile.

- **Escopo**: app Android que dá acesso ao FilamentDB pelo celular.
- **Uso principal**: controle de **estoque** e ver **simulações**.
- **Evolução planejada**: integração direta com a impressora (Creality K2).
- **Estado atual**: scaffold Android completo em `android/`, **validado
  estaticamente mas ainda não compilado** (a máquina de dev não tinha Gradle nem
  Android SDK). Próximo desbloqueio = primeiro build (Fase 0).

---

## 0. Divisão de responsabilidades — 🤖 Kiro vs. 👤 Rafael

**Ler antes de executar qualquer fase.** Um agente do Kiro roda sem device
Android, sem emulador e sem interação humana (não consegue fazer login, ver a
tela, nem tocar no app). Por isso as tarefas se dividem:

- 🤖 **Kiro faz sozinho**: escrever/editar código (Kotlin, XML, `main.js`, CSS,
  Flask), criar arquivos de config, ajustar o roadmap, validar sintaxe
  estaticamente. Tudo que é edição de repositório.
- 👤 **Só o Rafael faz**: instalar SDK/Studio, rodar `./gradlew`, aprovar
  permissões, fazer login no Pangolin, observar o app rodando, testar em device
  real, publicar APK.
- 🤝 **Colaborativo**: Kiro implementa a mudança e descreve exatamente o que
  testar; Rafael executa no device e reporta o resultado; Kiro ajusta.

Cada item do checklist (seção 4) está marcado com 🤖 / 👤 / 🤝. **Uma nova
sessão do Kiro deve pegar itens 🤖 e preparar os 🤝, mas não pode "completar" um
item 👤** — só deixar pronto para o Rafael executar.

---

## 1. Setup real (a base de tudo)

Estas são as condições de infra que ditam as decisões técnicas. Se mudarem,
revisar as decisões da seção 2.

- **App web**: Flask, servindo `templates/dashboard.html` + `static/main.js`.
  A UI já é responsiva e o menu virou um botão "apps" (dropdown) no canto
  superior esquerdo, pensado para telas pequenas.
- **Exposição**: atrás do **Pangolin** (proxy identity-aware = Traefik + auth de
  borda via middleware Badger). Todo request passa pela auth antes de chegar no
  Flask.
- **Domínio**: `https://filamentdb.learnops.duckdns.org/` com TLS válido
  (Let's Encrypt via Traefik).
- **Autenticação**: portal web do próprio Pangolin. Login por **email/senha
  local** (sem IdP externo tipo Google/Microsoft). Usuário criado e autorizado
  manualmente. Acesso sustentado por **cookie de sessão**.

---

## 2. Decisões tomadas e alternativas avaliadas

### 2.1 Abordagem do app: **WebView nativo** ✅

Avaliamos três caminhos:

| Abordagem | Veredito | Motivo |
|-----------|----------|--------|
| **WebView nativo** | ✅ **Escolhido** | Autocontido, não exige mexer no Pangolin, login por cookie funciona bem, controle total sobre downloads e futura bridge nativa. |
| **TWA (Bubblewrap)** | ⏸️ Futuro | Melhor experiência fullscreen e herda a sessão do Chrome, **mas** exige liberar `/.well-known/assetlinks.json` sem auth no Pangolin (senão a verificação do Digital Asset Links falha — o proxy responde 302 e o crawler do Google quebra). Fica como opção se quiser "app de verdade" sem barra. |
| **Capacitor** | ❌ Descartado | Ganho real só apareceria com auth por header/token ou muitos recursos nativos. Overkill para o uso atual. |

**Por que o login local por cookie desempata a favor do WebView**: não há
redirect para domínio de terceiro no meio do login (que é o que costuma quebrar
OAuth dentro de WebView). O portal do Pangolin é uma página HTML no próprio
domínio; o WebView renderiza e guarda o cookie no seu cookie jar. Loga uma vez,
entra direto depois.

### 2.2 Autenticação: **cookie de sessão persistido no WebView** ✅

- `CookieManager` com `setAcceptCookie(true)` + `setAcceptThirdPartyCookies` e
  `flush()` em `onPause`/`onPageFinished`.
- **Maior risco do projeto**: se o cookie do Pangolin for muito restritivo
  (`SameSite=Strict`), a persistência pode falhar. Testar cedo (Fase 1).

### 2.3 HTTPS obrigatório ✅

- `network_security_config.xml` **bloqueia cleartext** (correto, pois o Pangolin
  serve TLS). Há um bloco `<domain-config>` comentado para, no futuro, permitir
  HTTP puro a um host da LAN (ex: falar direto com a impressora).

### 2.4 Stack e versões ✅

| Item | Versão | Nota |
|------|--------|------|
| Linguagem | Kotlin 2.0.21 | |
| AGP | 8.7.3 | estável, conservador |
| Gradle | 8.9 | |
| compileSdk / targetSdk | 35 | |
| minSdk | 26 (Android 8.0) | cobre praticamente todos os devices atuais; habilita WebView moderno e adaptive icons |
| JDK | 17 | |

### 2.5 Arquitetura orientada a evolução ✅

- WebView é um **componente isolado** (dentro de `SwipeRefreshLayout`), não um
  `loadUrl` colado na Activity. Facilita adicionar features nativas depois.
- URL centralizada em `app/build.gradle.kts` (`buildConfigField SERVER_URL`).
- Gancho `PrinterBridge` comentado em `MainActivity.kt` para a futura integração
  com a impressora via `addJavascriptInterface`.

---

## 3. O que já está pronto (scaffold em `android/`)

- Estrutura Gradle: `settings.gradle.kts`, `build.gradle.kts`,
  `gradle.properties`, `gradle/wrapper/gradle-wrapper.properties`.
- Módulo `app`: `build.gradle.kts` (deps core-ktx, appcompat, activity-ktx,
  androidx.webkit, swiperefreshlayout; `signingConfig` de release opcional via
  propriedades), `proguard-rules.pro`.
- `MainActivity.kt`: WebView (JS + DOM storage), cookies persistentes,
  `DownloadListener` (repassa cookie de sessão), pull-to-refresh, back
  navigation, links externos no navegador do sistema, gancho `PrinterBridge`.
- Recursos: `AndroidManifest.xml`, `network_security_config.xml`, tema escuro
  alinhado à UI web, `strings`, `colors`, ícone adaptativo (vetorial),
  layout `activity_main.xml`.
- `.gitignore` e `README.md` (instruções de build e assinatura).

**Validação já feita** (estática, sem compilar): todos os XML bem-formados;
referências `R.string`/`R.id`/`R.layout`/`@drawable`/`@mipmap`/`@color` resolvem;
`package` == `namespace` == `applicationId` == `org.learnops.filamentdb`;
imports do Kotlin consistentes.

**O que NÃO foi feito**: gerar o `gradle-wrapper.jar` (binário) e compilar/rodar
— a máquina de dev não tinha Gradle nem SDK Android. É a Fase 0.

---

## 4. Roteiro por fases

Legenda: 🤖 Kiro faz · 👤 só Rafael · 🤝 colaborativo (Kiro implementa, Rafael testa no device).

### Fase 0 — Primeiro build (bloqueia todo o resto)
- [ ] 👤 Instalar Android Studio **ou** SDK + Gradle na máquina de build.
- [ ] 👤 Gerar o wrapper: `cd android && gradle wrapper --gradle-version 8.9`
      (ou deixar o Android Studio gerar ao abrir a pasta `android/`).
- [ ] 👤 Criar `android/local.properties` com `sdk.dir=...` (não versionar).
- [ ] 🤝 `./gradlew assembleDebug` — Rafael roda; se falhar, cola o erro e o
      Kiro corrige o código/config.
- [ ] 👤 `./gradlew installDebug` num device real.
- **Pronto quando**: o APK de debug instala e abre no device mostrando o portal
  do Pangolin (mesmo que sem login ainda).

### Fase 1 — Validar o fluxo de auth (maior risco)
- [ ] 👤 Portal do Pangolin renderiza dentro do WebView.
- [ ] 👤 Login chega no dashboard.
- [ ] 👤 Fechar e reabrir o app entra **sem pedir login** (cookie persistiu).
- [ ] 👤 Expiração de sessão: quando o cookie expira, cai no login de novo sem
      travar em tela branca.
- [ ] 🤝 Se a persistência falhar, aplicar a contingência (seção 6.1). Rafael
      diagnostica no device; Kiro implementa a saída escolhida.
- **Pronto quando**: loga uma vez, fecha o app, reabre e cai direto no dashboard
  sem novo login. Este é o critério que valida a decisão do WebView.

### Fase 2 — Estoque e simulações (uso principal)
- [ ] 🤝 CRUD de estoque no celular: formulários, selects, `<input type="color">`.
      Kiro ajusta a UI web (`dashboard.html`/`main.js`); Rafael valida o toque.
- [ ] 🤝 Responsividade das telas de estoque e simulação no viewport móvel.
- [ ] 🤝 Pull-to-refresh sem conflitar com scroll de tabelas (se conflitar, Kiro
      pode desabilitar o swipe quando o scroll interno não está no topo).
- [ ] 🤖 Ajustes de UX móvel são feitos na UI web, não no app Kotlin.
- **Pronto quando**: dá para adicionar/editar/mover um filamento e navegar
  estoque + simulação confortavelmente num celular, sem zoom nem scroll lateral.

### Fase 3 — Downloads de perfil
- [ ] 👤 Baixar `.json` e `.info` pelo app (com cookie de sessão, senão o Pangolin
      bloqueia). O `DownloadListener` já repassa o cookie — validar que funciona.
- [ ] 👤 Nome de arquivo correto via `Content-Disposition`.
- [ ] 👤 Confirmar `DIRECTORY_DOWNLOADS` em Android 10+ (scoped storage) via
      DownloadManager, sem permissão extra.
- **Pronto quando**: baixar um perfil pelo app gera o arquivo correto em
  Downloads, sem erro 401/403 do Pangolin.

### Fase 4 — Acabamento
- [ ] 🤖 Splash screen (API SplashScreen).
- [ ] 🤖 Estado offline: tela amigável quando server/Pangolin não responde (hoje
      só Toast) — trocar por uma view de erro com botão "tentar de novo".
- [ ] 🤖 Ícone definitivo (o atual é placeholder vetorial).
- [ ] 🤝 Insets/notch e `windowLightStatusBar` (Kiro ajusta, Rafael confere no
      device com notch).
- [ ] 🤖 Política de `versionCode`/`versionName`.
- **Pronto quando**: o app tem splash, trata offline sem tela branca, e o ícone
  não é mais placeholder.

### Fase 5 — Distribuição
- [ ] 👤 Keystore de release (ver `android/README.md`).
- [ ] 🤝 `./gradlew assembleRelease` / `bundleRelease` (Kiro deixa o
      `signingConfig` pronto; Rafael tem a keystore e roda).
- [ ] 👤 Canal: sideload do APK (uso pessoal) vs Play Store interna.
- [ ] 🤖 (Opcional) CI no GitHub Actions buildando APK a cada tag.
- **Pronto quando**: existe um APK/AAB assinado instalável fora do modo debug.

---

## 5. Backlog futuro — integração com a impressora (Creality K2)

Longo prazo. Não começar antes das Fases 0–2 sólidas.

- [ ] Definir o canal: API local da impressora? Klipper/Moonraker? Descoberta via
      mDNS na LAN?
- [ ] Implementar `PrinterBridge` (comentário em `MainActivity.kt`) e expor via
      `addJavascriptInterface(bridge, "AndroidPrinter")`.
- [ ] No `main.js`, consumir `window.AndroidPrinter?.…` com fallback quando rodar
      no browser desktop (a bridge só existe no app). **Onde plugar**: o
      `main.js` executa tudo no top-level (não há `DOMContentLoaded`; o `<script>`
      é carregado no fim do `<body>` do `dashboard.html`). As inits ficam no fim
      do arquivo (ex: `initSimulation()`, `loadRanking()`, `loadInventory()`).
      Adicionar uma detecção perto do bloco de estado inicial, algo como:
      `const isAndroidApp = typeof window.AndroidPrinter !== 'undefined';`
      e só chamar métodos da bridge sob esse guard. Nenhum ponto de integração
      nativa existe hoje — é campo aberto.
- [ ] Avaliar permissões (rede local, descoberta de serviços) e o
      `network_security_config` se a comunicação for HTTP na LAN.
- [ ] **Preferir colocar a lógica de impressora no servidor Flask** e o app só
      chamar a API — mantém o app fino. Só usar a bridge nativa para o que exige
      acesso ao device (ex: descoberta na LAN).

---

## 6. Riscos / pontos de atenção

- **Cookie de sessão × WebView**: risco nº 1. `SameSite=Strict` ou cookies muito
  restritivos podem quebrar a persistência. Testar na Fase 1. Contingência em 6.1.
- **Expiração de sessão**: garantir re-login sem travar.
- **HTTPS obrigatório**: HTTP na LAN (impressora) exigirá liberar o host no
  `network_security_config.xml` (bloco comentado já existe).
- **Sem TWA hoje**: adotar TWA depois exige liberar `/.well-known/assetlinks.json`
  sem auth no Pangolin/Traefik.

### 6.1 Contingência — se o cookie de sessão não persistir

Se na Fase 1 o app pedir login toda vez que reabre (cookie não sobreviveu),
seguir esta ordem, do mais simples ao mais invasivo:

1. **Confirmar o `flush()`**: garantir que `CookieManager.getInstance().flush()`
   roda em `onPause` e `onPageFinished` (já está no `MainActivity.kt`). Sem
   `flush`, o cookie fica só em memória e some ao fechar o processo.
2. **Verificar as flags do cookie** (Rafael, via DevTools do Chrome apontando
   para o device, ou logs do Pangolin): se `SameSite=Strict`, o cookie pode não
   ser reenviado em navegações iniciadas pelo app. Testar `setAcceptThirdPartyCookies(webView, true)`
   (já ativo) e, se preciso, pedir ao Pangolin/Traefik `SameSite=Lax`.
3. **Persistência explícita do WebView**: garantir que não há `clearCache`/
   `clearCookies` em lugar nenhum e que o app não usa modo incógnito.
4. **Última saída — token próprio**: se o cookie do Pangolin for realmente
   incompatível, criar um fluxo de login próprio no app que guarda um token em
   `EncryptedSharedPreferences` e injeta o header em cada request via
   `WebViewClient.shouldInterceptRequest`. É mais trabalho e acopla o app à API
   do Pangolin — só fazer se 1–3 falharem.

> Se chegar no item 4, reavaliar se o **TWA** (que herda a sessão do Chrome e
> não tem esse problema de cookie jar isolado) não passou a valer mais a pena —
> ver a decisão 2.1 e o custo de liberar o `assetlinks.json` no Pangolin.

### 6.2 Testes

Decisão: **não há testes automatizados** neste app por ora. Justificativa: é um
WebView fino, a lógica real vive na UI web (já testável no browser desktop) e no
Flask. Testes instrumentados de WebView dariam pouco retorno frente ao custo.
- A validação é **manual em device** (checklists "Pronto quando" de cada fase).
- Se a `PrinterBridge` (seção 5) crescer com lógica nativa de verdade, aí sim
  criar testes unitários Kotlin (JUnit) para essa lógica — reavaliar na época.

---

## 7. Mapa do repositório (para retomar)

| O quê | Onde |
|-------|------|
| Projeto Android | `android/` |
| Código do app | `android/app/src/main/` |
| Instruções de build/assinatura | `android/README.md` |
| URL do servidor (única fonte) | `android/app/build.gradle.kts` → `SERVER_URL` |
| UI que o WebView carrega | `templates/dashboard.html` + `static/main.js` |
| Servidor Flask | `src/web.py` (rota `/` e `/dashboard`) |

### Como retomar numa nova sessão
1. Ler este arquivo (com atenção à **seção 0** — o que o Kiro pode ou não fazer)
   e o `android/README.md`.
2. Ver em que fase o checklist (seção 4) parou.
3. Pegar os itens 🤖 e preparar os 🤝. Para itens 👤, deixar tudo pronto e
   descrever ao Rafael exatamente o que ele precisa rodar/testar no device.
4. Continuar a partir dali.
