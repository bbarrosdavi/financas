import java.util.Properties
import org.jetbrains.kotlin.gradle.dsl.JvmTarget

plugins {
    id("com.android.application")
    id("com.chaquo.python")
    id("org.jetbrains.kotlin.plugin.compose")
}

// Raiz do repositório: o app/ (o Python do servidor) entra no APK direto de lá; a tela é nativa (Compose).
val repo: File = rootDir.parentFile

// Chave de assinatura: fora do repositório (nunca no git). O arquivo .properties aponta o keystore e as senhas.
// Padrão: ~/.local/share/financas-android/keystore.properties (ou a variável FINANCAS_KEYSTORE).
val propsAssinatura = File(System.getenv("FINANCAS_KEYSTORE")
    ?: "${System.getProperty("user.home")}/.local/share/financas-android/keystore.properties")
val assinatura = Properties().apply { if (propsAssinatura.exists()) propsAssinatura.inputStream().use { load(it) } }

android {
    namespace = "io.github.bbarrosdavi.financas"
    compileSdk = 37

    defaultConfig {
        applicationId = "io.github.bbarrosdavi.financas"
        minSdk = 26
        targetSdk = 36
        versionCode = 1
        versionName = "1.0.0"
        // Python 3.12 no Android só tem estas duas: celulares atuais e o emulador x86_64.
        ndk { abiFilters += listOf("arm64-v8a", "x86_64") }
    }

    signingConfigs {
        if (propsAssinatura.exists()) {
            create("release") {
                storeFile = File(assinatura.getProperty("storeFile"))
                storePassword = assinatura.getProperty("storePassword")
                keyAlias = assinatura.getProperty("keyAlias")
                keyPassword = assinatura.getProperty("keyPassword")
            }
        }
    }

    buildTypes {
        release {
            // R8 tira do Compose o que o app não usa (o .apk cai uns 15 MB); o Chaquopy traz as próprias regras.
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"))
            // Sem o keystore local, cai na chave de depuração (instala, mas não atualiza um APK assinado de verdade).
            signingConfig = signingConfigs.findByName("release") ?: signingConfigs.getByName("debug")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    buildFeatures {
        buildConfig = true
        compose = true
    }
}

kotlin {
    compilerOptions { jvmTarget = JvmTarget.JVM_17 }
}

chaquopy {
    defaultConfig {
        version = "3.12"
        pip {
            // FastAPI com pydantic 1 (puro Python): o pydantic 2 depende de código nativo sem build para Android.
            install("fastapi==0.115.14")
            install("pydantic==1.10.26")
            install("python-multipart==0.0.32")
            install("openpyxl==3.1.5")
            install("tzdata")
        }
    }
    sourceSets {
        getByName("main") {
            srcDir(layout.buildDirectory.dir("python-repo"))
        }
    }
}

// O pacote app/ do servidor, sem o preenchedor do .ods (LibreOffice não existe no celular).
val copiarApp by tasks.registering(Sync::class) {
    from(File(repo, "app")) {
        include("**/*.py")
        exclude("ods_preencher.py", "**/__pycache__/**")
    }
    into(layout.buildDirectory.dir("python-repo/app"))
}

tasks.configureEach {
    if ("Python" in name || name == "preBuild") dependsOn(copiarApp)
}

dependencies {
    implementation(platform("androidx.compose:compose-bom:2026.09.00"))
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.foundation:foundation")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.activity:activity-compose:1.13.0")
    implementation("androidx.core:core-ktx:1.19.1")
    implementation("androidx.work:work-runtime-ktx:2.12.0")
}
