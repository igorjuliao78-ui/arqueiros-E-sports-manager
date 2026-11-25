package br.com.arqueiros.manager
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.*
import okhttp3.*
import org.json.JSONObject
import org.json.JSONArray

private const val BASE="https://arqueiros-e-sports-manager.onrender.com/api/mobile"
private val http=OkHttpClient()
private fun req(url:String, token:String?=null, body:String?=null):String {
 val b=Request.Builder().url(url)
 if(token!=null)b.header("Authorization","Bearer "+token)
 if(body!=null)b.post(body.toRequestBody("application/json".toMediaType()))
 val r=http.newCall(b.build()).execute()
 val text=r.body?.string() ?: ""
 if(!r.isSuccessful) throw Exception(if(text.isNotEmpty()) text else "HTTP "+r.code)
 return text
}
private fun String.toRequestBody(type:MediaType?=null)=okhttp3.RequestBody.create(type,this)
private fun String.toMediaType()=MediaType.parse(this)
class MainActivity:ComponentActivity(){override fun onCreate(savedInstanceState:Bundle?){super.onCreate(savedInstanceState);setContent{NativeApp()}}}
@OptIn(ExperimentalMaterial3Api::class)
@Composable fun NativeApp(){
 var token by remember { mutableStateOf("") }; var username by remember{mutableStateOf("")};var password by remember{mutableStateOf("")};var data by remember{mutableStateOf<JSONObject?>(null)};var error by remember{mutableStateOf("")};var loading by remember{mutableStateOf(false)};var tab by remember{mutableStateOf("Resumo")}
 val scope= rememberCoroutineScope()
 fun load(){loading=true;error="";scope.launch(Dispatchers.IO){try{val j=JSONObject(req("$BASE/bootstrap",token));withContext(Dispatchers.Main){data=j;loading=false}}catch(e:Exception){withContext(Dispatchers.Main){error=e.message ?: "Erro";loading=false}}}}
 MaterialTheme(colorScheme=darkColorScheme(primary=Color(0xFFE53935),background=Color(0xFF101010),surface=Color(0xFF1C1C1C))){
 if(token.isBlank()) { Column(Modifier.fillMaxSize().padding(24.dp),verticalArrangement=Arrangement.Center){Text("ARQUEIROS E-SPORTS",style=MaterialTheme.typography.headlineMedium,color=Color.Red);Text("Manager • Aplicativo nativo",color=Color.LightGray);Spacer(Modifier.height(20.dp));OutlinedTextField(username,{username=it},label={Text("Usuário")},singleLine=true);OutlinedTextField(password,{password=it},label={Text("Senha")},singleLine=true);Button(onClick={loading=true;scope.launch(Dispatchers.IO){try{val j=JSONObject(req("$BASE/auth/login",body=JSONObject().put("username",username).put("password",password).toString()));withContext(Dispatchers.Main){token=j.getString("access_token");load()}}catch(e:Exception){withContext(Dispatchers.Main){error=e.message ?: "Login";loading=false}}}},Modifier.fillMaxWidth()){Text(if(loading)"Entrando..." else "Entrar")};Text(error,color=Color.Red)}}
 else {Scaffold(topBar={TopAppBar(title={Text("Arqueiros Manager")},actions={IconButton(onClick={load()}){Icon(Icons.Default.Refresh,"Atualizar")};IconButton(onClick={token="";data=null}){Icon(Icons.Default.Logout,"Sair")}})},bottomBar={NavigationBar{listOf("Resumo","Jogadores","Partidas","Ranking","Avisos").forEach{NavigationBarItem(selected=tab==it,onClick={tab=it},icon={Icon(when(it){"Resumo"->Icons.Default.Home;"Jogadores"->Icons.Default.Groups;"Partidas"->Icons.Default.SportsSoccer;"Ranking"->Icons.Default.Leaderboard;else->Icons.Default.Notifications},"")},label={Text(it)})}}}){pad->Column(Modifier.padding(pad).fillMaxSize().padding(12.dp)){if(loading)LinearProgressIndicator(Modifier.fillMaxWidth());if(error.isNotEmpty())Text(error,color=Color.Red);val d=data
 if(d==null)Button(onClick={load()}){Text("Carregar")}
 else when(tab){
 "Resumo"-> {Text("Painel",style=MaterialTheme.typography.headlineSmall);Card(Modifier.fillMaxWidth()){Column(Modifier.padding(16.dp)){Text(d.optJSONObject("dashboard")?.toString(2) ?: "Dados do painel");Text("Elenco: "+d.optJSONArray("players")?.length().toString())}}}
 "Jogadores"->{Text("Elenco",style=MaterialTheme.typography.headlineSmall);val arr=d.optJSONArray("players")?:JSONArray();LazyColumn{items(arr.length()){i->val p=arr.optJSONObject(i);Card(Modifier.fillMaxWidth().padding(vertical=4.dp)){Column(Modifier.padding(12.dp)){Text(p?.optString("name") ?: "Jogador",style=MaterialTheme.typography.titleMedium);Text("Status: "+p?.optString("status"));Text("ID: "+p?.optInt("id"))}}}}}
 "Partidas"->{Text("Confrontos",style=MaterialTheme.typography.headlineSmall);val arr=d.optJSONArray("matches")?:JSONArray();LazyColumn{items(arr.length()){i->val m=arr.optJSONObject(i);Card(Modifier.fillMaxWidth().padding(vertical=4.dp)){Column(Modifier.padding(12.dp)){Text((m?.optString("home")?:"")+" "+(m?.optString("home_score")?:"")+" × "+(m?.optString("away_score")?:"")+" "+(m?.optString("away")?:""),style=MaterialTheme.typography.titleMedium);Text("Status: "+m?.optString("status"));Text("Competição: "+m?.optString("competition"))}}}}}
 "Ranking"->{Text("Ranking",style=MaterialTheme.typography.headlineSmall);val arr=d.optJSONArray("rankings")?:JSONArray();LazyColumn{items(arr.length()){i->Text((i+1).toString()+". "+arr.optJSONObject(i)?.toString(),Modifier.padding(8.dp))}}}
 else->{Text("Comunicados",style=MaterialTheme.typography.headlineSmall);val arr=d.optJSONArray("notices")?:JSONArray();LazyColumn{items(arr.length()){i->Card(Modifier.fillMaxWidth().padding(vertical=4.dp)){Column(Modifier.padding(12.dp)){Text(arr.optJSONObject(i)?.optString("title")?:"");Text(arr.optJSONObject(i)?.optString("body")?:"")}}}}}
 }}}}
 }
 }
}
