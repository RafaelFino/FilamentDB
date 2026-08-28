plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "org.learnops.filamentdb"
    compileSdk = 35

    defaultConfig {
        applicationId = "org.learnops.filamentdb"
        minSdk = 26
        targetSdk = 35
        versionCode = 1
        versionName = "1.0.0"

        // URL do servidor (Pangolin -> Flask). Exposta em BuildConfig e como
        // string resource para uso futuro (ex: tela de config de host).
        buildConfigField("String", "SERVER_URL", "\"https://filamentdb.learnops.duckdns.org/\"")
    }

    signingConfigs {
        // Assinatura de release opcional via propriedades em ~/.gradle/gradle.properties
        // (FILAMENTDB_STORE_FILE etc). Se ausentes, o build de release fica sem
        // signingConfig e voce assina pelo Android Studio (Generate Signed Bundle).
        val storeFilePath = (project.findProperty("FILAMENTDB_STORE_FILE") as String?)
        if (storeFilePath != null) {
            create("release") {
                storeFile = file(storeFilePath)
                storePassword = project.findProperty("FILAMENTDB_STORE_PASSWORD") as String?
                keyAlias = project.findProperty("FILAMENTDB_KEY_ALIAS") as String?
                keyPassword = project.findProperty("FILAMENTDB_KEY_PASSWORD") as String?
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro",
            )
            signingConfig = signingConfigs.findByName("release")
        }
    }

    buildFeatures {
        buildConfig = true
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("androidx.activity:activity-ktx:1.9.3")
    // APIs modernas de WebView com compatibilidade retroativa.
    implementation("androidx.webkit:webkit:1.12.1")
    // Pull-to-refresh no WebView.
    implementation("androidx.swiperefreshlayout:swiperefreshlayout:1.1.0")
}
