package br.com.arqueiros.app

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.launch
import org.json.JSONObject

@Composable
internal fun FederationPage(
    data: JSONObject,
    api: Api,
    scope: CoroutineScope,
    refresh: () -> Unit,
    errorSetter: (String) -> Unit,
) {
    val competitions = federationArray(data, "competitions")
    val fixtures = federationArray(data, "federation_fixtures")
    var opponent by remember { mutableStateOf("") }
    var round by remember { mutableStateOf("RDD 1") }
    var format by remember { mutableStateOf("5x5") }
    var competitionId by remember { mutableStateOf("") }
    var scoreFor by remember { mutableStateOf("") }
    var scoreAgainst by remember { mutableStateOf("") }
    var lineup by remember { mutableStateOf("") }

    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp)
    ) {
        Text("FEDERAÇÕES • RODADAS", color = Color.White, fontSize = 21.sp, fontWeight = FontWeight.Black)
        Text("Registre cada confronto da Arqueiros, o formato e as vitórias de cada lado.", color = Color(0xFF9BA2B1), fontSize = 12.sp)
        Card(colors = CardDefaults.cardColors(containerColor = Color(0xFF151821))) {
            Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("NOVO CONFRONTO", color = Color.White, fontWeight = FontWeight.Bold)
                OutlinedTextField(value = opponent, onValueChange = { opponent = it }, label = { Text("Equipe adversária") }, modifier = Modifier.fillMaxWidth())
                OutlinedTextField(value = round, onValueChange = { round = it }, label = { Text("Rodada / RDD") }, modifier = Modifier.fillMaxWidth())
                OutlinedTextField(value = competitionId, onValueChange = { competitionId = it }, label = { Text("ID da competição (opcional)") }, modifier = Modifier.fillMaxWidth())
                Text("Formato", color = Color(0xFF9BA2B1), fontSize = 11.sp)
                Row(horizontalArrangement = Arrangement.spacedBy(7.dp)) {
                    listOf("3x3", "5x5", "6x6").forEach { item ->
                        FilterChip(
                            selected = format == item,
                            onClick = { format = item },
                            label = { Text(item) },
                            colors = FilterChipDefaults.filterChipColors(
                                selectedContainerColor = Color(0xFFC62836),
                                selectedLabelColor = Color.White
                            )
                        )
                    }
                }
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedTextField(value = scoreFor, onValueChange = { scoreFor = it }, label = { Text("Vitórias Arqueiros") }, modifier = Modifier.weight(1f))
                    OutlinedTextField(value = scoreAgainst, onValueChange = { scoreAgainst = it }, label = { Text("Vitórias adversário") }, modifier = Modifier.weight(1f))
                }
                OutlinedTextField(value = lineup, onValueChange = { lineup = it }, label = { Text("Escalação / confrontos (opcional)") }, modifier = Modifier.fillMaxWidth(), minLines = 2)
                Button(
                    onClick = {
                        scope.launch {
                            try {
                                val payload = JSONObject()
                                    .put("opponent", opponent.trim())
                                    .put("round", round.trim())
                                    .put("format", format)
                                    .put("competition_id", competitionId.toIntOrNull() ?: JSONObject.NULL)
                                    .put("score_for", scoreFor.toIntOrNull() ?: JSONObject.NULL)
                                    .put("score_against", scoreAgainst.toIntOrNull() ?: JSONObject.NULL)
                                    .put("lineup", lineup)
                                api.request("/api/mobile/federation", "POST", payload)
                                opponent = ""; scoreFor = ""; scoreAgainst = ""; lineup = ""
                                errorSetter("Confronto registrado para revisão.")
                                refresh()
                            } catch (e: Exception) { errorSetter(e.message ?: "Falha ao registrar confronto.") }
                        }
                    },
                    enabled = opponent.isNotBlank(),
                    modifier = Modifier.fillMaxWidth(),
                    colors = ButtonDefaults.buttonColors(containerColor = Color(0xFFC62836))
                ) { Text("REGISTRAR CONFRONTO", fontWeight = FontWeight.Bold) }
            }
        }

        Text("HISTÓRICO DE CONFRONTOS", color = Color.White, fontWeight = FontWeight.Bold)
        if (fixtures.isEmpty()) Text("Nenhum confronto de federação cadastrado.", color = Color(0xFF9BA2B1), fontSize = 12.sp)
        fixtures.forEach { fixture ->
            Card(colors = CardDefaults.cardColors(containerColor = Color(0xFF151821))) {
                Column(Modifier.padding(13.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text("${fixture.optString("round")} • ${fixture.optString("opponent")}", color = Color.White, fontWeight = FontWeight.Bold)
                    Text("${fixture.optString("format")} • ${fixture.optString("competition", "Sem competição")}", color = Color(0xFF9BA2B1), fontSize = 11.sp)
                    Text("Arqueiros ${if (fixture.isNull("score_for")) "—" else fixture.optInt("score_for")} × ${if (fixture.isNull("score_against")) "—" else fixture.optInt("score_against")} adversário", color = Color(0xFFC62836), fontWeight = FontWeight.Bold)
                    Text("Status: ${fixture.optString("status")}", color = Color(0xFF9BA2B1), fontSize = 11.sp)
                    if (fixture.optString("lineup").isNotBlank()) Text(fixture.optString("lineup"), color = Color(0xFF9BA2B1), fontSize = 11.sp)
                    if (fixture.optString("status") == "Pendente") {
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            Button(onClick = {
                                scope.launch {
                                    try {
                                        api.request("/api/mobile/federation/${fixture.optInt("id")}/approve", "POST")
                                        errorSetter("Confronto aprovado.")
                                        refresh()
                                    } catch (e: Exception) { errorSetter(e.message ?: "Não foi possível aprovar.") }
                                }
                            }, colors = ButtonDefaults.buttonColors(containerColor = Color(0xFFC62836)), modifier = Modifier.weight(1f)) {
                                Text("APROVAR")
                            }
                            OutlinedButton(onClick = {
                                scope.launch {
                                    try {
                                        api.request("/api/mobile/federation/${fixture.optInt("id")}/reject", "POST")
                                        errorSetter("Confronto rejeitado.")
                                        refresh()
                                    } catch (e: Exception) { errorSetter(e.message ?: "Não foi possível rejeitar.") }
                                }
                            }, modifier = Modifier.weight(1f)) { Text("REJEITAR") }
                        }
                    }
                }
            }
        }
    }
}

private fun federationArray(obj: JSONObject, key: String): List<JSONObject> {
    val array = obj.optJSONArray(key) ?: return emptyList()
    return (0 until array.length()).mapNotNull { array.optJSONObject(it) }
}
