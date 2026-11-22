plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}
android {
    namespace = "br.com.arqueiros.app"
    compileSdk = 35
    defaultConfig {
        applicationId = "br.com.arqueiros.app"
        minSdk = 26
        targetSdk = 35
        versionCode = 1
        versionName = "1.0.0"
        buildConfigField("String", "API_BASE_URL", "\"https://arqueiros-e-sports-manager.onrender.com/\"")
    }
    buildFeatures { compose = true; buildConfig = true }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
}
dependencies {
    implementation(platform("androidx.compose:compose-bom:2025.01.00"))
    implementation("androidx.activity:activity-compose:1.10.0")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.foundation:foundation")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.9.0")
}

 
// Gera os ícones do launcher diretamente do recorte da logo oficial incluído em assets.
val generateArqueirosLauncherIcons by tasks.registering {
    val logoFile = file("src/main/assets/arqueiros-logo.jpg.b64")
    inputs.file(logoFile)
    outputs.dir(file("src/main/res"))
    doLast {
        val encoded = logoFile.readText().trim()
        val bytes = java.util.Base64.getDecoder().decode(encoded)
        val source = javax.imageio.ImageIO.read(java.io.ByteArrayInputStream(bytes))
        val sizes = mapOf("mdpi" to 48, "hdpi" to 72, "xhdpi" to 96, "xxhdpi" to 144, "xxxhdpi" to 192)
        sizes.forEach { (density, size) ->
            val directory = file("src/main/res/mipmap-" + density)
            directory.mkdirs()
            val canvas = java.awt.image.BufferedImage(size, size, java.awt.image.BufferedImage.TYPE_INT_ARGB)
            val graphics = canvas.createGraphics()
            graphics.color = java.awt.Color(11, 11, 16)
            graphics.fillRect(0, 0, size, size)
            val scale = minOf((size * 0.90) / source.width, (size * 0.64) / source.height)
            val width = (source.width * scale).toInt()
            val height = (source.height * scale).toInt()
            graphics.drawImage(source, (size - width) / 2, (size - height) / 2, width, height, null)
            graphics.dispose()
            javax.imageio.ImageIO.write(canvas, "png", file(directory, "ic_launcher.png"))
        }
    }
}
tasks.named("preBuild").configure { dependsOn(generateArqueirosLauncherIcons) }
