package br.com.arqueiros.app

import android.content.Context
import android.graphics.BitmapFactory
import android.net.Uri
import android.os.Bundle
import android.util.Base64
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.Image
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

private val Black = Color(0xFF090A0E)
private val Panel = Color(0xFF151821)
private val Red = Color(0xFFC62836)
private val Muted = Color(0xFF9BA2B1)
private val White = Color(0xFFF5F6FA)

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent { MaterialTheme(colorScheme = darkColorScheme(primary=Red, background=Black, surface=Panel, onSurface=White)) { ArqueirosApp() } }
    }
}

internal class Api(private val context: Context) {
    private val base = "https://arqueiros-e-sports-manager.onrender.com"
    private val prefs = context.getSharedPreferences("arqueiros", Context.MODE_PRIVATE)
    var token: String?
        get() = prefs.getString("token", null)
        set(value) { prefs.edit().putString("token", value).apply() }

    suspend fun request(path: String, method: String = "GET", body: JSONObject? = null): JSONObject = withContext(Dispatchers.IO) {
        val conn = (URL(base + path).openConnection() as HttpURLConnection)
        conn.requestMethod = method
        conn.connectTimeout = 20000
        conn.readTimeout = 30000
        conn.setRequestProperty("Accept", "application/json")
        token?.let { conn.setRequestProperty("Authorization", "Bearer $it") }
        if (body != null) {
            conn.doOutput = true
            conn.setRequestProperty("Content-Type", "application/json; charset=utf-8")
            conn.outputStream.use { it.write(body.toString().toByteArray(Charsets.UTF_8)) }
        }
        val code = conn.responseCode
        val stream = if (code in 200..299) conn.inputStream else conn.errorStream
        val text = stream?.bufferedReader()?.use { it.readText() } ?: "{}"
        conn.disconnect()
        val json = try { JSONObject(text) } catch (_: Exception) { JSONObject().put("detail", text) }
        if (code !in 200..299) throw IllegalStateException(json.optString("detail", "Falha na comunicação ($code)"))
        json
    }

    suspend fun login(user: String, password: String): JSONObject {
        val result = request("/api/mobile/auth/login", "POST", JSONObject().put("username",user).put("password",password))
        token = result.getString("access_token")
        return result.optJSONObject("user") ?: JSONObject()
    }
}

@Composable
private fun ArqueirosApp() {
    val context = LocalContext.current
    val api = remember { Api(context) }
    val scope = rememberCoroutineScope()
    var logged by remember { mutableStateOf(api.token != null) }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf("") }
    var user by remember { mutableStateOf(JSONObject()) }
    var data by remember { mutableStateOf(JSONObject()) }
    var page by remember { mutableStateOf("Início") }

    fun refresh() {
        scope.launch {
            busy = true
            try { data = api.request("/api/mobile/bootstrap"); user = data.optJSONObject("user") ?: user; error = "" }
            catch (e: Exception) { error = e.message ?: "Erro"; if (error.contains("401") || error.contains("403")) { api.token=null; logged=false } }
            busy = false
        }
    }
    LaunchedEffect(logged) { if (logged) refresh() }

    if (!logged) {
        LoginScreen(busy,error) { u,p ->
            scope.launch { busy=true; error=""; try { user=api.login(u,p); logged=true } catch(e:Exception){error=e.message ?: "Falha no login"}; busy=false }
        }
    } else {
        Column(Modifier.fillMaxSize().background(Black)) {
            Row(Modifier.fillMaxWidth().background(Color(0xFF11131A)).padding(horizontal=18.dp, vertical=16.dp), verticalAlignment=Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text("ARQUEIROS", color=White, fontWeight=FontWeight.Black, fontSize=21.sp, letterSpacing=2.sp)
                    Text("E-SPORTS MANAGER", color=Red, fontSize=10.sp, fontWeight=FontWeight.Bold, letterSpacing=2.sp)
                }
                Text("● ONLINE", color=Color(0xFF69C58B), fontSize=11.sp, fontWeight=FontWeight.Bold)
                Spacer(Modifier.width(12.dp))
                Text("SAIR", color=Muted, modifier=Modifier.clickable { api.token=null; logged=false }.padding(6.dp), fontSize=11.sp)
            }
            Row(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()).padding(horizontal=12.dp, vertical=8.dp), horizontalArrangement=Arrangement.spacedBy(6.dp)) {
                listOf("Início","Elenco","Partidas","Ranking","eFootball","Admin").forEach { item ->
                    val selected = page==item
                    Text(item, color=if(selected) White else Muted, fontSize=11.sp, fontWeight=FontWeight.Bold,
                        modifier=Modifier.background(if(selected) Red else Panel, RoundedCornerShape(9.dp)).clickable { page=item }.padding(horizontal=13.dp, vertical=12.dp), textAlign=androidx.compose.ui.text.style.TextAlign.Center)
                }
            }
            if (error.isNotBlank()) Text(error, color=Color(0xFFFF7777), modifier=Modifier.padding(horizontal=16.dp, vertical=6.dp), fontSize=12.sp)
            when(page) {
                "Início" -> HomePage(data, busy, ::refresh)
                "Elenco" -> PlayersPage(data, api, scope, ::refresh, errorSetter={error=it})
                "Partidas" -> MatchesPage(data, api, scope, ::refresh, errorSetter={error=it})
                "Ranking" -> RankingPage(data)
                "eFootball" -> EFootballPage(data, api, scope, errorSetter={error=it})
                else -> AdminPage(data, api, scope, ::refresh, errorSetter={error=it})
            }
        }
    }
}

@Composable
private fun LoginScreen(busy:Boolean, error:String, onLogin:(String,String)->Unit) {
    var username by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var showPassword by remember { mutableStateOf(false) }
    val context = LocalContext.current
    val logo = remember(context) { try { val encoded=context.assets.open("arqueiros-logo.jpg.b64").bufferedReader().use{it.readText()}; BitmapFactory.decodeByteArray(Base64.decode(encoded,Base64.DEFAULT),0,Base64.decode(encoded,Base64.DEFAULT).size)?.asImageBitmap() } catch (_:Exception) { null } }
    Column(Modifier.fillMaxSize().background(Black).padding(26.dp), verticalArrangement=Arrangement.Center, horizontalAlignment=Alignment.CenterHorizontally) {
        if (logo != null) Image(bitmap=logo,contentDescription="Logo oficial Arqueiros",modifier=Modifier.fillMaxWidth().height(140.dp),contentScale=ContentScale.Fit)
        Text("ARQUEIROS", color=White, fontSize=32.sp, fontWeight=FontWeight.Black, letterSpacing=3.sp)
        Text("E-SPORTS MANAGER", color=Red, fontSize=13.sp, fontWeight=FontWeight.Bold, letterSpacing=3.sp)
        Spacer(Modifier.height(42.dp))
        Text("ACESSO DO ADMINISTRADOR", color=White, fontSize=19.sp, fontWeight=FontWeight.Bold)
        Spacer(Modifier.height(18.dp))
        Field("Usuário",username,{username=it})
        Spacer(Modifier.height(12.dp))
        Row(verticalAlignment=Alignment.CenterVertically) { Field("Senha",password,{password=it},!showPassword,Modifier.weight(1f)); Text(if(showPassword) "OCULTAR" else "MOSTRAR",color=Red,fontSize=10.sp,fontWeight=FontWeight.Bold,modifier=Modifier.clickable { showPassword=!showPassword }.padding(start=10.dp)) }
        if(error.isNotBlank()) Text(error,color=Color(0xFFFF7777),fontSize=12.sp,modifier=Modifier.padding(top=12.dp))
        Spacer(Modifier.height(22.dp))
        Button(onClick={onLogin(username.trim(),password)}, enabled=!busy && username.isNotBlank() && password.isNotBlank(), modifier=Modifier.fillMaxWidth().height(52.dp), colors=ButtonDefaults.buttonColors(containerColor=Red)) { Text(if(busy) "CONECTANDO..." else "ENTRAR",fontWeight=FontWeight.Bold) }
        Spacer(Modifier.height(18.dp))
        Text("Gestão oficial • Arqueiros E-Sports",color=Muted,fontSize=11.sp)
    }
}

@Composable
private fun HomePage(data:JSONObject,busy:Boolean,refresh:()->Unit) {
    val dash=data.optJSONObject("dashboard") ?: JSONObject()
    LazyColumn(Modifier.fillMaxSize().padding(horizontal=16.dp), verticalArrangement=Arrangement.spacedBy(12.dp), contentPadding=PaddingValues(bottom=28.dp)) {
        item { Spacer(Modifier.height(4.dp)); Text("PAINEL GERAL",color=White,fontSize=22.sp,fontWeight=FontWeight.Black); Text("Visão geral da operação da equipe",color=Muted,fontSize=12.sp) }
        item {
            val cards=listOf("JOGADORES" to dash.optInt("players"),"COMPETIÇÕES" to dash.optInt("competitions"),"PARTIDAS" to dash.optInt("approved"),"PENDENTES" to dash.optInt("pending"),"TÍTULOS" to dash.optInt("titles"))
            Column(verticalArrangement=Arrangement.spacedBy(9.dp)) {
                cards.chunked(2).forEach { row -> Row(horizontalArrangement=Arrangement.spacedBy(9.dp)) { row.forEach { (label,value)-> StatCard(label,value.toString(),Modifier.weight(1f)) }; if(row.size==1) Spacer(Modifier.weight(1f)) } }
            }
        }
        item { SectionTitle("ÚLTIMAS PARTIDAS") }
        items(jsonArray(data,"matches").take(8)) { m -> MatchCard(m) }
        item { Button(onClick=refresh,enabled=!busy,modifier=Modifier.fillMaxWidth(),colors=ButtonDefaults.buttonColors(containerColor=Red)){Text(if(busy)"ATUALIZANDO..." else "ATUALIZAR DADOS")} }
    }
}

@Composable
private fun PlayersPage(data:JSONObject,api:Api,scope:kotlinx.coroutines.CoroutineScope,refresh:()->Unit,errorSetter:(String)->Unit) {
    var search by remember { mutableStateOf("") }
    var showAdd by remember { mutableStateOf(false) }
    var name by remember { mutableStateOf("") }; var nick by remember { mutableStateOf("") }; var position by remember { mutableStateOf("") }
    val players=jsonArray(data,"players").filter { it.optString("name").contains(search,true) || it.optString("nickname").contains(search,true) }
    Column(Modifier.fillMaxSize().padding(horizontal=16.dp)) {
        Row(verticalAlignment=Alignment.CenterVertically) { Column(Modifier.weight(1f)){Text("ELENCO",color=White,fontSize=22.sp,fontWeight=FontWeight.Black);Text("${players.size} jogadores",color=Muted,fontSize=12.sp)}; Button(onClick={showAdd=!showAdd},colors=ButtonDefaults.buttonColors(containerColor=Red)){Text("＋ NOVO")} }
        Spacer(Modifier.height(8.dp)); Field("Buscar jogador",search,{search=it})
        if(showAdd) {
            Spacer(Modifier.height(8.dp)); Field("Nome completo",name,{name=it}); Field("Nick",nick,{nick=it}); Field("Posição",position,{position=it})
            Button(onClick={scope.launch { try { api.request("/api/mobile/players","POST",JSONObject().put("name",name).put("nickname",nick).put("position",position)); name="";nick="";position="";showAdd=false;refresh() } catch(e:Exception){errorSetter(e.message?:"Erro")} } },enabled=name.isNotBlank(),colors=ButtonDefaults.buttonColors(containerColor=Red)){Text("SALVAR JOGADOR")}
        }
        LazyColumn(verticalArrangement=Arrangement.spacedBy(8.dp),contentPadding=PaddingValues(vertical=12.dp)) {
            items(players) { p -> PanelCard {
                Row(verticalAlignment=Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) { Text(p.optString("name"),color=White,fontWeight=FontWeight.Bold); Text(listOf(p.optString("nickname"),p.optString("position"),p.optString("status")).filter{it.isNotBlank()}.joinToString(" • "),color=Muted,fontSize=11.sp) }
                    Text("PERFIL",color=Red,fontSize=10.sp,fontWeight=FontWeight.Bold)
                }
            } }
        }
    }
}

@Composable
private fun MatchesPage(data:JSONObject,api:Api,scope:kotlinx.coroutines.CoroutineScope,refresh:()->Unit,errorSetter:(String)->Unit) {
    var showAdd by remember { mutableStateOf(false) }
    var home by remember { mutableStateOf("ARQUEIROS E-SPORTS") }; var away by remember { mutableStateOf("") }; var hs by remember { mutableStateOf("0") }; var ascore by remember { mutableStateOf("0") }
    Column(Modifier.fillMaxSize().padding(horizontal=16.dp)) {
        Row(verticalAlignment=Alignment.CenterVertically){Column(Modifier.weight(1f)){Text("PARTIDAS",color=White,fontSize=22.sp,fontWeight=FontWeight.Black);Text("Resultados e aprovações",color=Muted,fontSize=12.sp)};Button(onClick={showAdd=!showAdd},colors=ButtonDefaults.buttonColors(containerColor=Red)){Text("＋ REGISTRAR")}}
        if(showAdd) {
            Spacer(Modifier.height(8.dp));Field("Equipe da casa",home,{home=it});Field("Adversário",away,{away=it});Row(horizontalArrangement=Arrangement.spacedBy(8.dp)){Field("Arqueiros",hs,{hs=it},modifier=Modifier.weight(1f));Field("Adversário",ascore,{ascore=it},modifier=Modifier.weight(1f))}
            Button(onClick={scope.launch { try { api.request("/api/mobile/matches","POST",JSONObject().put("home",home).put("away",away).put("home_score",hs.toInt()).put("away_score",ascore.toInt()));showAdd=false;refresh() } catch(e:Exception){errorSetter(e.message?:"Erro")} } },enabled=away.isNotBlank(),colors=ButtonDefaults.buttonColors(containerColor=Red)){Text("SALVAR PARTIDA")}
        }
        LazyColumn(verticalArrangement=Arrangement.spacedBy(8.dp),contentPadding=PaddingValues(vertical=12.dp)) { items(jsonArray(data,"matches")) { m-> MatchCard(m) } }
    }
}

@Composable
private fun RankingPage(data:JSONObject) {
    val ranking=jsonArray(data,"player_ranking")
    Column(Modifier.fillMaxSize().padding(16.dp)) {
        Text("RANKING INDIVIDUAL",color=White,fontSize=22.sp,fontWeight=FontWeight.Black)
        Text("Classificação por pontos, gols e desempenho",color=Muted,fontSize=12.sp)
        LazyColumn(verticalArrangement=Arrangement.spacedBy(8.dp),contentPadding=PaddingValues(vertical=14.dp)) {
            items(ranking) { p -> PanelCard { Row(verticalAlignment=Alignment.CenterVertically){Text("#${ranking.indexOf(p)+1}",color=Red,fontWeight=FontWeight.Black,modifier=Modifier.width(36.dp));Column(Modifier.weight(1f)){Text(p.optString("name"),color=White,fontWeight=FontWeight.Bold);Text("${p.optInt("games")} jogos • ${p.optInt("goals")} gols • ${p.optInt("assists")} assistências",color=Muted,fontSize=11.sp)};Text("${p.optInt("points")} pts",color=Red,fontWeight=FontWeight.Black)} } }
        }
    }
}

@Composable
private fun AdminPage(data:JSONObject,api:Api,scope:kotlinx.coroutines.CoroutineScope,refresh:()->Unit,errorSetter:(String)->Unit) {
    var tab by remember { mutableStateOf("OCR") }
    var preview by remember { mutableStateOf<JSONObject?>(null) }
    var imageB64 by remember { mutableStateOf("") }
    var teamSide by remember { mutableStateOf("first") }
    var selectedCompetitionId by remember { mutableStateOf("") }
    val context= LocalContext.current
    val picker= rememberLauncherForActivityResult(ActivityResultContracts.GetContent()) { uri:Uri? ->
        if(uri!=null) scope.launch { try { val bytes=context.contentResolver.openInputStream(uri)?.use{it.readBytes()} ?: byteArrayOf(); imageB64=Base64.encodeToString(bytes,Base64.NO_WRAP); preview=api.request("/api/mobile/matches/image/preview","POST",JSONObject().put("image_base64",imageB64).put("team_side",teamSide)); selectedCompetitionId=preview?.optString("competition_id","") ?: "" } catch(e:Exception){errorSetter(e.message?:"Falha ao ler print")} }
    }
    Column(Modifier.fillMaxSize().padding(horizontal=16.dp)) {
        Text("ADMINISTRAÇÃO",color=White,fontSize=22.sp,fontWeight=FontWeight.Black)
        Row(horizontalArrangement=Arrangement.spacedBy(6.dp),modifier=Modifier.padding(vertical=10.dp)){listOf("OCR","Pendências","Competições","Federações").forEach{t->Text(t,color=if(tab==t)White else Muted,modifier=Modifier.background(if(tab==t)Red else Panel,RoundedCornerShape(8.dp)).clickable{tab=t}.padding(10.dp),fontSize=11.sp,fontWeight=FontWeight.Bold)}}
        when(tab) {
            "OCR" -> {
                PanelCard {
                    Text("IMPORTAÇÃO INTELIGENTE",color=White,fontWeight=FontWeight.Bold)
                    Text("Selecione o print do confronto. A leitura será apresentada para conferência antes de enviar.",color=Muted,fontSize=12.sp)
                    Spacer(Modifier.height(10.dp))
                    Text("A Arqueiros aparece em qual lado do print?",color=Muted,fontSize=11.sp)
                    Row(horizontalArrangement=Arrangement.spacedBy(8.dp)) {
                        listOf("first" to "PRIMEIRO LADO","second" to "SEGUNDO LADO").forEach { (value,label) ->
                            Text(label,color=if(teamSide==value) White else Muted,modifier=Modifier.background(if(teamSide==value) Red else Black,RoundedCornerShape(8.dp)).clickable { teamSide=value }.padding(10.dp),fontSize=10.sp,fontWeight=FontWeight.Bold)
                        }
                    }
                    Spacer(Modifier.height(12.dp))
                    Button(onClick={picker.launch("image/*")},colors=ButtonDefaults.buttonColors(containerColor=Red)){Text("SELECIONAR PRINT")}
                }
                preview?.let { p ->
                    Spacer(Modifier.height(10.dp)); PanelCard {
                        Text("PRÉ-VISUALIZAÇÃO • ${p.optInt("recognized")} jogadores",color=White,fontWeight=FontWeight.Bold)
                        Text("Adversário: ${p.optString("team")}",color=Muted,fontSize=12.sp)
                        Text("COMPETIÇÃO (selecione para registrar)",color=Muted,fontSize=10.sp,fontWeight=FontWeight.Bold)
                        jsonArray(data,"competitions").forEach { comp ->
                            Text((if(selectedCompetitionId==comp.optString("id")) "✓ " else "") + comp.optString("name"),color=if(selectedCompetitionId==comp.optString("id")) Red else White,fontSize=12.sp,modifier=Modifier.clickable { selectedCompetitionId=comp.optString("id") }.padding(vertical=3.dp))
                        }
                        Text("Placar: ${scoreText(p.optJSONArray("scores"))}",color=Muted,fontSize=12.sp)
                        jsonArray(p,"stats").forEach { st -> Text("${st.optString("detected_name")}  ${st.optInt("goals_for")} x ${st.optInt("goals_against")}${if(st.optBoolean("is_new_player"))" • NOVO JOGADOR" else ""}",color=if(st.optBoolean("is_new_player"))Red else White,fontSize=12.sp,modifier=Modifier.padding(vertical=3.dp)) }
                        Text("Novos jogadores só serão incluídos após conferência administrativa.",color=Muted,fontSize=11.sp)
                        Button(onClick={scope.launch { try { val payload=JSONObject(p.toString()).put("stats",p.optJSONArray("stats")?:JSONArray()).put("team_side",p.optString("team_side",teamSide)).put("competition_id",selectedCompetitionId.toIntOrNull() ?: p.optInt("competition_id")); val result=api.request("/api/mobile/matches/image/confirm","POST",payload); errorSetter("Importação enviada: ${result.optString("status","Pendente")}.");preview=null;refresh() } catch(e:Exception){errorSetter(e.message?:"Erro na importação")} } },colors=ButtonDefaults.buttonColors(containerColor=Red)){Text("CONFIRMAR IMPORTAÇÃO")}
                    }
                }
            }
            "Pendências" -> {
                Text("CONFRONTOS PENDENTES",color=White,fontWeight=FontWeight.Bold)
                jsonArray(data,"matches").filter{it.optString("status")=="Pendente"}.forEach { m ->
                    PanelCard { MatchCard(m); Row(horizontalArrangement=Arrangement.spacedBy(8.dp)){Button(onClick={scope.launch{try{api.request("/api/mobile/matches/${m.optInt("id")}/approve","POST");refresh()}catch(e:Exception){errorSetter(e.message?:"Erro")}}},colors=ButtonDefaults.buttonColors(containerColor=Red)){Text("APROVAR")};OutlinedButton(onClick={scope.launch{try{api.request("/api/mobile/matches/${m.optInt("id")}/reject","POST");refresh()}catch(e:Exception){errorSetter(e.message?:"Erro")}}}){Text("REJEITAR")} } }
                }
            }
            "Federações" -> FederationPage(data, api, scope, refresh, errorSetter)
            else -> {
                Text("COMPETIÇÕES",color=White,fontWeight=FontWeight.Bold)
                jsonArray(data,"competitions").forEach { c -> PanelCard { Text(c.optString("name"),color=White,fontWeight=FontWeight.Bold);Text("${c.optString("kind")} • ${c.optString("season")}",color=Muted,fontSize=11.sp) } }
            }
        }
    }
}

@Composable private fun MatchCard(m:JSONObject) {
    PanelCard {
        Row(verticalAlignment=Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) { Text(m.optString("home")+"  ×  "+m.optString("away"),color=White,fontWeight=FontWeight.Bold,fontSize=13.sp);Text(m.optString("competition","Sem competição"),color=Muted,fontSize=10.sp) }
            Text("${m.opt("home_score")?: "-"} : ${m.opt("away_score")?: "-"}",color=Red,fontWeight=FontWeight.Black,fontSize=18.sp)
        }
        Text(m.optString("status"),color=Muted,fontSize=10.sp)
    }
}
@Composable private fun StatCard(label:String,value:String,modifier:Modifier=Modifier) { PanelCard(modifier){Text(label,color=Muted,fontSize=10.sp,fontWeight=FontWeight.Bold);Text(value,color=White,fontSize=27.sp,fontWeight=FontWeight.Black)} }
@Composable private fun SectionTitle(value:String){Text(value,color=White,fontSize=14.sp,fontWeight=FontWeight.Bold)}
@Composable private fun PanelCard(modifier:Modifier=Modifier,content:@Composable ColumnScope.()->Unit){Column(modifier.fillMaxWidth().background(Panel,RoundedCornerShape(13.dp)).padding(14.dp),verticalArrangement=Arrangement.spacedBy(6.dp),content=content)}
@Composable private fun Field(label:String,value:String,onValue:(String)->Unit,password:Boolean=false,modifier:Modifier=Modifier) {
    Column(modifier.fillMaxWidth().background(Panel,RoundedCornerShape(10.dp)).padding(horizontal=13.dp,vertical=10.dp)) {
        Text(label,color=Muted,fontSize=10.sp)
        BasicTextField(value=value,onValueChange=onValue,singleLine=true,visualTransformation=if(password) PasswordVisualTransformation() else VisualTransformation.None,textStyle=androidx.compose.ui.text.TextStyle(color=White,fontSize=14.sp),modifier=Modifier.fillMaxWidth().padding(top=5.dp))
    }
}
private fun jsonArray(obj:JSONObject,key:String):List<JSONObject>{val a=obj.optJSONArray(key)?:return emptyList();return (0 until a.length()).mapNotNull{a.optJSONObject(it)}}

private fun scoreText(a:JSONArray?):String { if(a==null || a.length()<2) return "Não identificado"; return "${a.opt(0)} x ${a.opt(1)}" }
