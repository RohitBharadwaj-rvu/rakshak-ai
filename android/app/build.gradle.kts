plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "ai.guardianline"
    compileSdk = 34

    defaultConfig {
        applicationId = "ai.guardianline"
        minSdk = 29 // Android 10 (Q) required for CallScreeningService
        targetSdk = 34
        versionCode = 1
        versionName = "1.0.0"

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"

        // Configurable gateway number via Gradle property or default placeholder
        val gatewayNumber = project.findProperty("GUARDIAN_GATEWAY_NUMBER") as String? ?: ""
        buildConfigField("String", "BOLNA_GATEWAY_NUMBER", "\"$gatewayNumber\"")
    }

    buildFeatures {
        buildConfig = true
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }

    testOptions {
        unitTests.all {
            it.useJUnitPlatform()
        }
    }

    // Shared screening cases live once, in tests/data, and are read by both pytest and JUnit
    sourceSets {
        getByName("test") {
            resources.srcDir("../../tests/data")
        }
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.12.0")
    implementation("androidx.appcompat:appcompat:1.6.1")
    implementation("com.google.android.material:material:1.11.0")
    implementation("androidx.work:work-runtime-ktx:2.9.0")

    // JUnit 5 Jupiter exclusively
    testImplementation("org.junit.jupiter:junit-jupiter-api:5.10.2")
    testImplementation("org.junit.jupiter:junit-jupiter-params:5.10.2")
    testRuntimeOnly("org.junit.jupiter:junit-jupiter-engine:5.10.2")
    testImplementation("org.assertj:assertj-core:3.25.3")
    testImplementation("com.google.code.gson:gson:2.10.1")
}
