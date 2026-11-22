package br.com.arqueiros.app

import android.app.DownloadManager
import android.content.Context
import android.net.Uri
import android.os.Bundle
import android.os.Environment
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL

private val Ink = Color(0xFF0B0B10)
private val Panel = Color(0xFF191920)
private val Red = Color(0xFFB51F2B)
private val Gold = Color(0xFFD6B15E)
private val Muted = Color(0xFFB8B8C2)

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.statusBarColor = android.graphics.Color.rgb(11, 11, 16)
        window.navigationBarColor = android.graphics.Color.rgb(11, 11, 16)
        setContent { MaterialTheme(colorScheme = darkColorScheme(background = Ink, surface = Panel, primary = Red, secondary = Gold)) { ArqueirosApp() } }
    }
}

private suspend fun api(path: String, method: String = "GET", token: String? = null, body: JSONObject? = null): JSONObject =
    withContext(Dispatchers.IO) {
        val c = URL(BuildConfig.API_BASE_URL.trimEnd('/') + "/" + path.trimStart('/')).openConnection() as HttpURLConnection
        c.requestMethod = method
        c.connectTimeout = 25000
        c.readTimeout = 30000
        c.setRequestProperty("Accept", "application/json")
        if (token != null) c.setRequestProperty("Authorization", "Bearer $token")
        if (body != null) {
            c.doOutput = true
            c.setRequestProperty("Content-Type", "application/json; charset=utf-8")
            c.outputStream.use { it.write(body.toString().toByteArray(Charsets.UTF_8)) }
        }
        val code = c.responseCode
        val stream = if (code in 200..299) c.inputStream else c.errorStream
        val raw = stream?.bufferedReader()?.use { it.readText() }.orEmpty()
        c.disconnect()
        val result = try { JSONObject(raw) } catch (_: Exception) { JSONObject() }
        if (code !in 200..299) throw IOException(result.optString("detail", "Erro HTTP $code"))
        result
    }

private fun bodyOf(values: Map<String, String>): JSONObject = JSONObject().apply {
    values.forEach { (key, value) ->
        if (value.isNotBlank()) {
            if (key in listOf("home_score", "away_score", "competition_id", "player_id")) put(key, value.toIntOrNull() ?: 0)
            else put(key, value)
        }
    }
}

private fun listOfJson(array: JSONArray?): List<JSONObject> =
    (0 until (array?.length() ?: 0)).mapNotNull { array?.optJSONObject(it) }

@Composable
private fun ArqueirosApp() {
    val context = LocalContext.current
    val prefs = remember { context.getSharedPreferences("arqueiros", Context.MODE_PRIVATE) }
    var token by remember { mutableStateOf(prefs.getString("token", null)) }
    var data by remember { mutableStateOf(JSONObject()) }
    var user by remember { mutableStateOf(JSONObject()) }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf("") }
    val scope = rememberCoroutineScope()

    suspend fun refresh() {
        val current = token ?: return
        busy = true
        try {
            data = api("api/mobile/bootstrap", token = current)
            user = data.optJSONObject("user") ?: JSONObject()
            error = ""
        } catch (e: Exception) { error = e.message ?: "Falha ao atualizar dados." }
        busy = false
    }

    if (token == null) {
        LoginScreen(busy, error) { username, password ->
            scope.launch {
                busy = true
                try {
                    val result = api("api/mobile/auth/login", "POST", body = JSONObject().put("username", username).put("password", password))
                    token = result.getString("access_token")
                    prefs.edit().putString("token", token).apply()
                    refresh()
                } catch (e: Exception) { error = e.message ?: "Falha no login." }
                busy = false
            }
        }
    } else {
        LaunchedEffect(token) { refresh() }
        MainScreen(data, user, token!!, busy, error,
            onRefresh = { scope.launch { refresh() } },
            onLogout = { prefs.edit().remove("token").apply(); token = null; data = JSONObject() },
            onAction = { path, method, payload ->
                scope.launch {
                    busy = true
                    try { api(path, method, token, payload); refresh() }
                    catch (e: Exception) { error = e.message ?: "Operação não concluída." }
                    busy = false
                }
            })
    }
}

@Composable
private fun LoginScreen(busy: Boolean, error: String, onLogin: (String, String) -> Unit) {
    var username by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    Column(Modifier.fillMaxSize().background(Ink).padding(24.dp), verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally) {
        ArqueirosLogo(Modifier.fillMaxWidth().height(142.dp))
        Spacer(Modifier.height(18.dp))
        Text("ARQUEIROS", color = Color.White, style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Black)
        Text("E-SPORTS • APP OFICIAL", color = Gold)
        Spacer(Modifier.height(30.dp))
        OutlinedTextField(username, { username = it }, label = { Text("Usuário") }, modifier = Modifier.fillMaxWidth(), singleLine = true)
        OutlinedTextField(password, { password = it }, label = { Text("Senha") }, modifier = Modifier.fillMaxWidth(), singleLine = true, visualTransformation = PasswordVisualTransformation())
        if (error.isNotBlank()) Text(error, color = Color(0xFFFF8B8B), modifier = Modifier.padding(8.dp))
        Button(onClick = { onLogin(username.trim(), password) }, enabled = !busy && username.isNotBlank() && password.isNotBlank(),
            modifier = Modifier.fillMaxWidth(), colors = ButtonDefaults.buttonColors(containerColor = Red)) {
            Text(if (busy) "CONECTANDO..." else "ENTRAR")
        }
        Text("Administrador: usuário admin e senha do token do painel. Integrantes: conta criada pela administração.",
            color = Muted, style = MaterialTheme.typography.bodySmall, modifier = Modifier.padding(top = 16.dp))
    }
}

@Composable
private fun MainScreen(data: JSONObject, user: JSONObject, token: String, busy: Boolean, error: String,
                       onRefresh: () -> Unit, onLogout: () -> Unit, onAction: (String, String, JSONObject?) -> Unit) {
    var tab by remember { mutableIntStateOf(0) }
    var form by remember { mutableStateOf<String?>(null) }
    val admin = user.optString("role") == "admin"
    val context = LocalContext.current
    Scaffold(containerColor = Ink, topBar = {
        Row(Modifier.fillMaxWidth().background(Panel).padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
            ArqueirosLogo(Modifier.size(48.dp))
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f)) {
                Text("ARQUEIROS", color = Gold, fontWeight = FontWeight.Black, style = MaterialTheme.typography.titleMedium)
                Text("GESTÃO • E-SPORTS", color = Muted, style = MaterialTheme.typography.labelSmall)
                Text("Olá, " + user.optString("name", "Integrante"), color = Color.White, style = MaterialTheme.typography.bodySmall)
            }
            TextButton(onClick = onRefresh) { Text("ATUALIZAR", color = Gold) }
            TextButton(onClick = onLogout) { Text("SAIR", color = Muted) }
        }
    }, bottomBar = {
        NavigationBar(containerColor = Panel) {
            listOf("Início", "Jogadores", "Competições", "Partidas", "Mais").forEachIndexed { i, label ->
                NavigationBarItem(selected = tab == i, onClick = { tab = i }, icon = { Text(listOf("⌂", "♟", "🏆", "⚽", "☰")[i]) },
                    label = { Text(label) }, colors = NavigationBarItemDefaults.colors(selectedIconColor = Gold, selectedTextColor = Gold, indicatorColor = Red, unselectedTextColor = Muted))
            }
        }
    }) { padding ->
        Column(Modifier.fillMaxSize().padding(padding)) {
            if (busy) LinearProgressIndicator(Modifier.fillMaxWidth(), color = Gold)
            if (error.isNotBlank()) Text(error, color = Color(0xFFFF8B8B), modifier = Modifier.padding(10.dp))
            when (tab) {
                0 -> HomeTab(data)
                1 -> PlayersTab(data, admin, { form = "player" }, onAction)
                2 -> CompetitionsTab(data, admin, { form = "competition" }, onAction)
                3 -> MatchesTab(data, admin, onAction)
                else -> MoreTab(data, admin, { form = it }, onAction) {
                    val request = DownloadManager.Request(Uri.parse(BuildConfig.API_BASE_URL.trimEnd('/') + "/api/mobile/reports/full.pdf"))
                        .addRequestHeader("Authorization", "Bearer $token")
                        .setTitle("Relatório geral Arqueiros").setDescription("Baixando relatório PDF")
                        .setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED)
                        .setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS, "arqueiros-relatorio-geral.pdf")
                    (context.getSystemService(Context.DOWNLOAD_SERVICE) as DownloadManager).enqueue(request)
                }
            }
        }
    }
    form?.let { type ->
        val spec = when (type) {
            "player" -> FormSpec("Novo jogador", listOf("name" to "Nome", "nickname" to "Nick", "position" to "Posição", "team" to "Equipe/divisão", "telegram_chat_id" to "ID Telegram opcional"), "api/mobile/players")
            "competition" -> FormSpec("Nova competição", listOf("name" to "Nome", "kind" to "Tipo: Liga/Copa/Torneio", "season" to "Temporada"), "api/mobile/competitions")
            "match" -> FormSpec("Registrar confronto", listOf("home" to "Equipe Arqueiros", "away" to "Adversário", "home_score" to "Gols Arqueiros", "away_score" to "Gols adversário", "competition_id" to "ID da competição opcional"), "api/mobile/matches")
            "title" -> FormSpec("Registrar título", listOf("name" to "Título", "season" to "Temporada", "competition_id" to "ID competição opcional", "player_id" to "ID jogador opcional", "notes" to "Observações"), "api/mobile/titles")
            "notice" -> FormSpec("Publicar comunicado", listOf("title" to "Título", "body" to "Mensagem"), "api/mobile/notices")
            "discipline" -> FormSpec("Registrar disciplina", listOf("player" to "Jogador", "reason" to "Motivo", "sanction" to "Sanção"), "api/mobile/discipline")
            "recruitment" -> FormSpec("Novo candidato", listOf("nickname" to "Nick", "position" to "Posição", "contact" to "Contato"), "api/mobile/recruitment")
            "user" -> FormSpec("Criar acesso", listOf("username" to "Usuário", "password" to "Senha (mín. 8)", "role" to "member ou admin", "player_id" to "ID jogador opcional"), "api/mobile/users")
            else -> null
        }
        if (spec != null) FormDialog(spec, onDismiss = { form = null }) { values ->
            onAction(spec.path, "POST", bodyOf(values)); form = null
        } else form = null
    }
}

private data class FormSpec(val title: String, val fields: List<Pair<String, String>>, val path: String)

@Composable
private fun FormDialog(spec: FormSpec, onDismiss: () -> Unit, onSave: (Map<String, String>) -> Unit) {
    val values = remember(spec) { mutableStateMapOf<String, String>().apply { spec.fields.forEach { put(it.first, "") } } }
    AlertDialog(onDismissRequest = onDismiss, containerColor = Panel,
        title = { Text(spec.title, color = Color.White) },
        text = { Column(verticalArrangement = Arrangement.spacedBy(7.dp)) {
            spec.fields.forEach { (key, label) ->
                OutlinedTextField(values[key] ?: "", { values[key] = it }, label = { Text(label) },
                    modifier = Modifier.fillMaxWidth(), singleLine = key != "body",
                    visualTransformation = if (key == "password") PasswordVisualTransformation() else androidx.compose.ui.text.input.VisualTransformation.None)
            }
        } },
        confirmButton = { TextButton(onClick = { onSave(values.toMap()) }) { Text("SALVAR", color = Gold) } },
        dismissButton = { TextButton(onClick = onDismiss) { Text("CANCELAR", color = Muted) } })
}

@Composable
private fun HomeTab(data: JSONObject) {
    val d = data.optJSONObject("dashboard") ?: JSONObject()
    LazyColumn(Modifier.fillMaxSize().padding(14.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        item {
            Card(modifier = Modifier.fillMaxWidth(), shape = RoundedCornerShape(20.dp),
                colors = CardDefaults.cardColors(containerColor = Panel)) {
                Row(Modifier.padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
                    ArqueirosLogo(Modifier.size(76.dp))
                    Spacer(Modifier.width(14.dp))
                    Column {
                        Text("ARQUEIROS E-SPORTS", color = Gold, fontWeight = FontWeight.Black,
                            style = MaterialTheme.typography.titleMedium)
                        Text("CENTRAL DE GESTÃO DA EQUIPE", color = Muted,
                            style = MaterialTheme.typography.labelSmall)
                    }
                }
            }
        }
        item { SectionTitle("PAINEL DA EQUIPE") }
        item { Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            StatCard("Jogadores", d.optInt("players"), Modifier.weight(1f)); StatCard("Competições", d.optInt("competitions"), Modifier.weight(1f))
        } }
        item { Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            StatCard("Aprovados", d.optInt("approved"), Modifier.weight(1f)); StatCard("Pendentes", d.optInt("pending"), Modifier.weight(1f)); StatCard("Títulos", d.optInt("titles"), Modifier.weight(1f))
        } }
        item { SectionTitle("CLASSIFICAÇÃO") }
        items(listOfJson(data.optJSONArray("rankings"))) { r ->
            InfoCard(r.optString("team") + " • " + r.optInt("PTS") + " pts",
                r.optInt("J").toString() + "J  " + r.optInt("V") + "V  " + r.optInt("E") + "E  " + r.optInt("D") + "D  •  SG " + r.optInt("SG"))
        }
        item { SectionTitle("COMUNICADOS") }
        items(listOfJson(data.optJSONArray("notices"))) { n ->
            Row(Modifier.fillMaxWidth().background(Panel, RoundedCornerShape(13.dp)).padding(12.dp),
                verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text(n.optString("title"), color = Color.White, fontWeight = FontWeight.Bold)
                    Text(n.optString("body"), color = Muted, style = MaterialTheme.typography.bodySmall)
                }
                if (admin) TextButton(onClick = {
                    onAction("api/mobile/notices/${n.optInt("id")}", "DELETE", null)
                }) { Text("EXCLUIR", color = Color(0xFFFF8B8B)) }
            }
        }
    }
}

@Composable
private fun StatCard(label: String, value: Int, modifier: Modifier = Modifier) {
    Card(modifier, colors = CardDefaults.cardColors(containerColor = Panel)) {
        Column(Modifier.padding(12.dp)) {
            Text(label.uppercase(), color = Muted, style = MaterialTheme.typography.labelSmall)
            Text(value.toString(), color = Gold, style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Black)
        }
    }
}

@Composable
private fun PlayersTab(data: JSONObject, admin: Boolean, onAdd: () -> Unit, onAction: (String, String, JSONObject?) -> Unit) {
    val players = listOfJson(data.optJSONArray("players")).filter {
        val n = it.optString("name").trim().lowercase()
        n != "cancelar" && n != "❌ cancelar"
    }
    LazyColumn(Modifier.fillMaxSize().padding(horizontal = 14.dp, vertical = 12.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)) {
        item {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    SectionTitle("ELENCO OFICIAL")
                    Text("${players.size} integrantes cadastrados", color = Muted, style = MaterialTheme.typography.bodySmall)
                }
                if (admin) Button(onClick = onAdd, colors = ButtonDefaults.buttonColors(containerColor = Red)) { Text("+ JOGADOR") }
            }
        }
        items(players) { p ->
            val status = p.optString("status", "Ativo")
            Card(modifier = Modifier.fillMaxWidth(), shape = RoundedCornerShape(18.dp),
                colors = CardDefaults.cardColors(containerColor = Panel),
                elevation = CardDefaults.cardElevation(defaultElevation = 3.dp)) {
                Column(Modifier.fillMaxWidth().padding(15.dp), verticalArrangement = Arrangement.spacedBy(9.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Box(Modifier.size(48.dp).background(Red, RoundedCornerShape(14.dp)), contentAlignment = Alignment.Center) {
                            Text(p.optString("name").trim().take(1).uppercase(), color = Color.White,
                                style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Black)
                        }
                        Spacer(Modifier.width(12.dp))
                        Column(Modifier.weight(1f)) {
                            Text(p.optString("name"), color = Color.White, fontWeight = FontWeight.Bold,
                                style = MaterialTheme.typography.titleMedium)
                            if (p.optString("nickname").isNotBlank())
                                Text("@${p.optString("nickname")}", color = Gold, style = MaterialTheme.typography.bodySmall)
                        }
                        Surface(color = if (status == "Ativo") Color(0xFF174D38) else Color(0xFF45351D),
                            shape = RoundedCornerShape(50)) {
                            Text(status.uppercase(), color = if (status == "Ativo") Color(0xFF8BE0B4) else Gold,
                                modifier = Modifier.padding(horizontal = 10.dp, vertical = 5.dp),
                                style = MaterialTheme.typography.labelSmall, fontWeight = FontWeight.Bold)
                        }
                    }
                    HorizontalDivider(color = Color(0xFF34343E))
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        if (p.optString("position").isNotBlank()) InfoChip("POSIÇÃO", p.optString("position"))
                        if (p.optString("team").isNotBlank()) InfoChip("EQUIPE", p.optString("team"))
                    }
                    if (admin) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Text("Gerenciar situação", color = Muted, style = MaterialTheme.typography.labelSmall)
                            Spacer(Modifier.weight(1f))
                            TextButton(onClick = {
                                onAction("api/mobile/players/${p.optInt("id")}/status", "PUT",
                                    JSONObject().put("status", nextStatus(status)))
                            }) { Text("ALTERAR STATUS", color = Gold, fontWeight = FontWeight.Bold) }
                        }
                    }
                }
            }
        }
        if (players.isEmpty()) item { InfoCard("Nenhum jogador cadastrado", "Adicione integrantes para montar o elenco.") }
    }
}

@Composable
private fun InfoChip(label: String, value: String) {
    Surface(color = Color(0xFF25252E), shape = RoundedCornerShape(9.dp)) {
        Column(Modifier.padding(horizontal = 10.dp, vertical = 7.dp)) {
            Text(label, color = Muted, style = MaterialTheme.typography.labelSmall)
            Text(value, color = Color.White, style = MaterialTheme.typography.bodySmall, fontWeight = FontWeight.SemiBold)
        }
    }
}

private fun nextStatus(s: String) = when (s) { "Ativo" -> "Reserva"; "Reserva" -> "Afastado"; "Afastado" -> "Desligado"; else -> "Ativo" }

@Composable
private fun CompetitionsTab(data: JSONObject, admin: Boolean, onAdd: () -> Unit, onAction: (String, String, JSONObject?) -> Unit) {
    LazyColumn(Modifier.fillMaxSize().padding(14.dp), verticalArrangement = Arrangement.spacedBy(9.dp)) {
        item { Row(verticalAlignment = Alignment.CenterVertically) { SectionTitle("COMPETIÇÕES"); Spacer(Modifier.weight(1f)); if (admin) Button(onClick = onAdd, colors = ButtonDefaults.buttonColors(containerColor = Red)) { Text("+ COMPETIÇÃO") } } }
        items(listOfJson(data.optJSONArray("competitions"))) { c ->
            Card(modifier = Modifier.fillMaxWidth(), shape = RoundedCornerShape(15.dp),
                colors = CardDefaults.cardColors(containerColor = Panel)) {
                Row(Modifier.fillMaxWidth().padding(13.dp), verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text(c.optString("name"), color = Color.White, fontWeight = FontWeight.Bold)
                        Text(c.optString("kind") + " • " + c.optString("season"), color = Muted,
                            style = MaterialTheme.typography.bodySmall)
                    }
                    if (admin) TextButton(onClick = {
                        onAction("api/mobile/competitions/${c.optInt("id")}", "DELETE", null)
                    }) { Text("EXCLUIR", color = Color(0xFFFF8B8B)) }
                }
            }
        }
    }
}

@Composable
private fun MatchesTab(data: JSONObject, admin: Boolean, onAction: (String, String, JSONObject?) -> Unit) {
    LazyColumn(Modifier.fillMaxSize().padding(14.dp), verticalArrangement = Arrangement.spacedBy(9.dp)) {
        item { SectionTitle("CONFRONTOS E RESULTADOS") }
        items(listOfJson(data.optJSONArray("matches"))) { m ->
            Column(Modifier.fillMaxWidth().background(Panel, RoundedCornerShape(13.dp)).padding(13.dp)) {
                Text(m.optString("home") + "  " + m.opt("home_score") + " × " + m.opt("away_score") + "  " + m.optString("away"), color = Color.White, fontWeight = FontWeight.Bold)
                Text(m.optString("competition", "Sem competição") + " • " + m.optString("status"), color = Muted)
                if (admin && m.optString("status") == "Pendente") Row {
                    TextButton(onClick = { onAction("api/mobile/matches/${m.optInt("id")}/approve", "POST", null) }) { Text("APROVAR", color = Gold) }
                    TextButton(onClick = { onAction("api/mobile/matches/${m.optInt("id")}/reject", "POST", null) }) { Text("REJEITAR", color = Color(0xFFFF8B8B)) }
                }
            }
        }
    }
}

@Composable
private fun MoreTab(data: JSONObject, admin: Boolean, onAdd: (String) -> Unit,
                    onAction: (String, String, JSONObject?) -> Unit, onReport: () -> Unit) {
    LazyColumn(Modifier.fillMaxSize().padding(14.dp), verticalArrangement = Arrangement.spacedBy(9.dp)) {
        item { SectionTitle("TÍTULOS DA EQUIPE") }
        items(listOfJson(data.optJSONArray("titles"))) { t -> InfoCard("🏆 " + t.optString("name"), t.optString("season") + if (t.optString("player").isNotBlank()) " • " + t.optString("player") else " • Equipe") }
        item { SectionTitle("COMUNICADOS") }
        items(listOfJson(data.optJSONArray("notices"))) { n -> InfoCard(n.optString("title"), n.optString("body")) }
        if (admin) {
            item { SectionTitle("ADMINISTRAÇÃO") }
            listOf("match" to "Registrar confronto", "title" to "Registrar título", "notice" to "Publicar comunicado",
                "discipline" to "Registrar disciplina", "recruitment" to "Adicionar candidato", "user" to "Criar acesso de integrante").forEach { (key, label) ->
                item { Button(onClick = { onAdd(key) }, modifier = Modifier.fillMaxWidth(), colors = ButtonDefaults.buttonColors(containerColor = Panel)) { Text(label, color = Color.White) } }
            }
            item { Button(onClick = onReport, modifier = Modifier.fillMaxWidth(), colors = ButtonDefaults.buttonColors(containerColor = Red)) { Text("BAIXAR RELATÓRIO GERAL PDF") } }
            item { SectionTitle("DISCIPLINA") }
            items(listOfJson(data.optJSONArray("discipline"))) { x -> InfoCard(x.optString("player"), x.optString("reason") + " • " + x.optString("sanction")) }
            item { SectionTitle("RECRUTAMENTO") }
            items(listOfJson(data.optJSONArray("recruitment"))) { x -> InfoCard(x.optString("nickname"), x.optString("position") + " • " + x.optString("contact") + " • " + x.optString("status")) }
            item { SectionTitle("USUÁRIOS DO APP") }
            items(listOfJson(data.optJSONArray("users"))) { x ->
                Row(Modifier.fillMaxWidth().background(Panel, RoundedCornerShape(13.dp)).padding(12.dp),
                    verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text(x.optString("username"), color = Color.White, fontWeight = FontWeight.Bold)
                        Text(x.optString("role") + " • " + if (x.optBoolean("active")) "Ativo" else "Bloqueado",
                            color = Muted, style = MaterialTheme.typography.bodySmall)
                    }
                    TextButton(onClick = {
                        onAction("api/mobile/users/${x.optInt("id")}/active", "PUT",
                            JSONObject().put("active", !x.optBoolean("active")))
                    }) { Text(if (x.optBoolean("active")) "BLOQUEAR" else "ATIVAR",
                        color = if (x.optBoolean("active")) Color(0xFFFF8B8B) else Gold) }
                }
            }
        }
    }
}

@Composable
private fun SectionTitle(text: String) { Text(text, color = Gold, fontWeight = FontWeight.Black, style = MaterialTheme.typography.titleMedium) }

@Composable
private fun InfoCard(title: String, subtitle: String) {
    Column(Modifier.fillMaxWidth().background(Panel, RoundedCornerShape(13.dp)).padding(13.dp)) {
        Text(title, color = Color.White, fontWeight = FontWeight.Bold)
        if (subtitle.isNotBlank()) Text(subtitle, color = Muted, style = MaterialTheme.typography.bodySmall)
    }
}
