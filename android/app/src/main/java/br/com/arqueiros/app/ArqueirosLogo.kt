package br.com.arqueiros.manager

import android.graphics.BitmapFactory
import android.util.Base64
import androidx.compose.foundation.Image
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext

@Composable
fun ArqueirosLogo(modifier: Modifier = Modifier) {
    val context = LocalContext.current
    val bitmap = remember {
        val encoded = context.assets.open("arqueiros-logo.jpg.b64").bufferedReader().use { it.readText() }
        val bytes = Base64.decode(encoded, Base64.DEFAULT)
        BitmapFactory.decodeByteArray(bytes, 0, bytes.size)
    }
    if (bitmap != null) {
        Image(bitmap = bitmap.asImageBitmap(), contentDescription = "Logo Arqueiros E-Sports",
            modifier = modifier, contentScale = ContentScale.Fit)
    }
}
