package br.com.arqueiros.app

import android.graphics.BitmapFactory
import android.util.Base64
import androidx.compose.foundation.Image
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale

private const val ARQUEIROS_LOGO_JPEG = "$"+"{b64}"

@Composable
fun ArqueirosLogo(modifier: Modifier = Modifier) {
    val bitmap = remember {
        val bytes = Base64.decode(ARQUEIROS_LOGO_JPEG, Base64.DEFAULT)
        BitmapFactory.decodeByteArray(bytes, 0, bytes.size)
    }
    Image(bitmap = bitmap.asImageBitmap(), contentDescription = "Logo Arqueiros E-Sports",
        modifier = modifier, contentScale = ContentScale.Fit)
}
