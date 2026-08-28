# FilamentDB — App Android (WebView)

Container Android que carrega o FilamentDB servido em
`https://filamentdb.learnops.duckdns.org/` (Flask atrás do Pangolin).

O app é um WebView com cookies persistentes: você loga uma vez no portal do
Pangolin (email/senha) dentro do próprio app e a sessão fica salva para as
próximas aberturas. Estruturado para evoluir depois (bridge JS↔Kotlin para
integração com a impressora — ver `MainActivity.kt`, seção `PrinterBridge`).

> **Roteiro e decisões**: o plano de trabalho, as fases pendentes e o histórico
> de decisões estão em [`../mobile-roadmap.md`](../mobile-roadmap.md) (raiz do
> repo). Este README cobre só o build.

## Requisitos

- Android Studio (Ladybug ou mais recente) **ou** SDK Android via linha de comando
- JDK 17
- Um device/emulador com Android 8.0+ (API 26+)

Este scaffold **não inclui o `gradle-wrapper.jar`** (binário) — ele é gerado
localmente, veja abaixo.

## Primeiro build

### Opção A — Android Studio (recomendado)

1. `File > Open` e selecione a pasta `android/`.
2. O Studio baixa o Gradle (8.9), AGP (8.7.3) e o SDK (compileSdk 35) sozinho.
3. Se pedir, deixe o Studio gerar o Gradle wrapper.
4. `Run` no device/emulador.

### Opção B — Linha de comando

Gere o wrapper uma vez (precisa de um Gradle no PATH, ex: via SDKMAN ou Homebrew):

```bash
cd android
gradle wrapper --gradle-version 8.9
```

Aponte o SDK Android criando `android/local.properties`:

```properties
sdk.dir=/caminho/para/Android/Sdk
```

Depois:

```bash
./gradlew assembleDebug        # APK de debug -> app/build/outputs/apk/debug/
./gradlew installDebug         # instala no device conectado (adb)
```

## Build de release (APK/AAB assinado)

1. Gere uma keystore (uma vez):

   ```bash
   keytool -genkeypair -v -keystore keystore/filamentdb.jks \
     -alias filamentdb -keyalg RSA -keysize 2048 -validity 10000
   ```

   (a pasta `keystore/` e `*.jks` já estão no `.gitignore`.)

2. Adicione as credenciais em `~/.gradle/gradle.properties` (fora do repo):

   ```properties
   FILAMENTDB_STORE_FILE=/caminho/absoluto/keystore/filamentdb.jks
   FILAMENTDB_STORE_PASSWORD=...
   FILAMENTDB_KEY_ALIAS=filamentdb
   FILAMENTDB_KEY_PASSWORD=...
   ```

   > Este scaffold ainda não amarra o `signingConfig` no `build.gradle.kts`.
   > Para release por linha de comando, adicione um bloco `signingConfigs`
   > lendo essas propriedades. Pelo Android Studio, use
   > `Build > Generate Signed Bundle / APK` e selecione a keystore acima.

3. Build:

   ```bash
   ./gradlew assembleRelease    # APK
   ./gradlew bundleRelease      # AAB (Play Store)
   ```

## Trocar a URL do servidor

A URL vive em um único lugar: `app/build.gradle.kts` →
`buildConfigField("String", "SERVER_URL", ...)`. Alterou ali, rebuild.

## Notas de arquitetura

- **HTTPS obrigatório**: `network_security_config.xml` bloqueia cleartext
  (correto, pois o Pangolin serve TLS). Se um dia quiser apontar direto para o
  Flask na LAN via HTTP, descomente o `<domain-config>` de exemplo naquele
  arquivo com o IP local.
- **Login do Pangolin**: portal web por cookie de sessão. O `CookieManager`
  persiste em disco (`flush()` em `onPause`/`onPageFinished`). Como o login é
  local (sem IdP externo), não há redirects cross-domain problemáticos.
- **Downloads de perfil** (`.json`/`.info`): tratados por `DownloadListener` +
  `DownloadManager`, repassando o cookie de sessão. Vão para a pasta Downloads.
- **Navegação**: links do próprio domínio ficam no WebView; links externos
  abrem no navegador do sistema. Botão voltar navega o histórico do WebView.
- **Evolução futura** (impressora): descomente/implemente `PrinterBridge` em
  `MainActivity.kt` e exponha via `addJavascriptInterface`. O `main.js` acessaria
  como `window.AndroidPrinter`.

## Estrutura

```
android/
├── settings.gradle.kts
├── build.gradle.kts
├── gradle.properties
├── gradle/wrapper/gradle-wrapper.properties   (jar gerado localmente)
└── app/
    ├── build.gradle.kts
    ├── proguard-rules.pro
    └── src/main/
        ├── AndroidManifest.xml
        ├── java/org/learnops/filamentdb/MainActivity.kt
        └── res/
            ├── drawable/         (adaptive icon)
            ├── layout/           (activity_main.xml)
            ├── mipmap-anydpi-v26/(ic_launcher)
            ├── values/           (colors, strings, themes)
            └── xml/              (network_security_config)
```
