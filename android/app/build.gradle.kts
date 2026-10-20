import org.jetbrains.kotlin.gradle.dsl.JvmTarget

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "at.loon.kgift"
    compileSdk = 35

    defaultConfig {
        applicationId = "at.loon.kgift"
        minSdk = 26
        targetSdk = 35
        versionCode = 3
        versionName = "3.0"
    }

    // Release-Schlüssel kommt aus ~/.gradle/gradle.properties (KGIFT_*), nie aus dem Repo;
    // fehlen die Einträge, entsteht eine unsignierte Release-APK
    val storeFilePath = providers.gradleProperty("KGIFT_STORE_FILE").orNull
    signingConfigs {
        if (storeFilePath != null) {
            create("release") {
                storeFile = file(storeFilePath)
                storePassword = providers.gradleProperty("KGIFT_STORE_PASSWORD").get()
                keyAlias = providers.gradleProperty("KGIFT_KEY_ALIAS").get()
                keyPassword = providers.gradleProperty("KGIFT_KEY_PASSWORD").get()
            }
        }
    }

    buildTypes {
        release {
            signingConfig = signingConfigs.findByName("release")
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"))
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}

kotlin {
    compilerOptions {
        jvmTarget.set(JvmTarget.JVM_17)
    }
}
