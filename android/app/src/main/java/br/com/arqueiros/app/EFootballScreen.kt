package br.com.arqueiros.app

import android.net.Uri
import android.util.Base64
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.snapshots.SnapshotStateMap
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.launch
import org.json.JSONArray
import org.json.JSONObject

private val EFPanel = Color(0xFF151821)
private val EFRed = Color(0xFFC62836)
private val EFMuted = Color(0xFF9BA2B1)
private val EFWhite = Color(0xFFF5F6FA)

@Composable
internal fun EFootballPage(
    data: JSONObject,
    api: Api,
    scope: CoroutineScope,
    errorSetter: (String) -> Unit,
) {
    val context = LocalContext.current
    val players = remember(data) { efJsonArray(data, "players") }
    var section by remember { mutableStateOf("Player Builder") }
    var builds by remember { mutableStateOf<List<JSONObject>>(emptyList()) }
    var plans by remember { mutableStateOf<List<JSONObject>>(emptyList()) }
    var cardName by remember { mutableStateOf("") }
    var playerId by remember { mutableStateOf("") }
    var buildName by remember { mutableStateOf("Build principal") }
    var cardType by remember { mutableStateOf("") }
    var position by remember { mutableStateOf("CF") }
    var level by remember { mutableStateOf("30") }
    var maxLevel by remember { mutableStateOf("30") }
    var overall by remember { mutableStateOf("") }
    var booster by remember { mutableStateOf("") }
    var baseStats by remember { mutableStateOf("") }
    var progression by remember { mutableStateOf("{\"SHO\":0,\"PAS\":0,\"DRI\":0,\"DEX\":0,\"LBS\":0,\"AERIAL\":0,\"DEF\":0,\"GK1\":0,\"GK2\":0,\"GK3\":0}") }
    var boosterEffects by remember { mutableStateOf("{}") }
    var notes by remember { mutableStateOf("") }
    var simulation by remember { mutableStateOf<JSONObject?>(null) }
    var compareIds by remember { mutableStateOf(setOf<Int>()) }
    var compareText by remember { mutableStateOf("") }
    var tacticName by remember { mutableStateOf("Escalação principal") }
    var formation by remember { mutableStateOf("4-2-1-3") }
    var playstyle by remember { mutableStateOf("Contra-ataque rápido") }
    val lineup: SnapshotStateMap<String, String> = remember { mutableStateMapOf() }

    fun refresh() {
        scope.launch {
            try {
                builds = efJsonArray(api.request("/api/mobile/efootball/builds"), "builds")
                plans = efJsonArray(api.request("/api/mobile/efootball/squad-plans"), "plans")
            } catch (e: Exception) {
                errorSetter(e.message ?: "Não foi possível carregar o eFootball Lab.")
            }
        }
    }

    LaunchedEffect(Unit) { refresh() }

    val imagePicker = rememberLauncherForActivityResult(ActivityResultContracts.GetContent()) { uri: Uri? ->
        if (uri != null) {
            scope.launch {
                try {
                    val bytes = context.contentResolver.openInputStream(uri)?.use { it.readBytes() } ?: byteArrayOf()
                    if (bytes.isEmpty() || bytes.size > 8 * 1024 * 1024) {
                        errorSetter("A imagem precisa ter até 8 MB.")
                    } else {
                        val encoded = Base64.encodeToString(bytes, Base64.NO_WRAP)
                        val result = api.request(
                            "/api/mobile/efootball/import-image",
                            "POST",
                            JSONObject().put("image_base64", encoded).put("card_name", cardName).put("player_id", playerId.toIntOrNull() ?: JSONObject.NULL)
                        )
                        val attrs = result.optJSONObject("attributes") ?: JSONObject()
                        baseStats = attrs.toString(2)
                        if (cardName.isBlank()) cardName = result.optString("card_name")
                        errorSetter("OCR concluído. Revise os atributos extraídos antes de salvar.")
                    }
                } catch (e: Exception) {
                    errorSetter(e.message ?: "Falha ao ler o print.")
                }
            }
        }
    }

    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 16.dp, vertical = 8.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp)
    ) {
        Text("eFOOTBALL LAB", color = EFWhite, fontSize = 22.sp, fontWeight = FontWeight.Black)
        Text("Construtor de cartas • evolução • escalação • análise", color = EFMuted, fontSize = 12.sp)
        Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            listOf("Player Builder", "Comparar", "Tática").forEach { item ->
                Text(
                    item,
                    color = if (section == item) EFWhite else EFMuted,
                    fontWeight = FontWeight.Bold,
                    fontSize = 11.sp,
                    modifier = Modifier
                        .background(if (section == item) EFRed else EFPanel, RoundedCornerShape(8.dp))
                        .clickable { section = item }
                        .padding(horizontal = 12.dp, vertical = 11.dp)
                )
            }
        }

        when (section) {
            "Player Builder" -> {
                EFCard {
                    Text("DADOS DA CARTA", color = EFWhite, fontWeight = FontWeight.Bold)
                    EFInput("Nome da carta / jogador", cardName, { cardName = it })
                    EFInput("Nome da build", buildName, { buildName = it })
                    EFPlayerPicker("Vincular ao elenco (opcional)", players, playerId) { playerId = it }
                    EFInput("Tipo da carta", cardType, { cardType = it })
                    EFInput("Posição (CF, SS, LWF, RWF, AMF, CMF, DMF, LB, RB, CB, GK)", position, { position = it })
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        EFInput("Nível atual", level, { level = it }, Modifier.weight(1f))
                        EFInput("Nível máximo", maxLevel, { maxLevel = it }, Modifier.weight(1f))
                        EFInput("Overall base", overall, { overall = it }, Modifier.weight(1f))
                    }
                    EFInput("Booster", booster, { booster = it })
                }
                EFCard {
                    Text("ATRIBUTOS BASE (JSON)", color = EFWhite, fontWeight = FontWeight.Bold)
                    Text("Informe os valores antes da progressão. Use chaves como speed, acceleration, finishing, low_pass, stamina.", color = EFMuted, fontSize = 11.sp)
                    EFInput("Atributos base", baseStats, { baseStats = it }, minLines = 5)
                    Text("PROGRESSÃO POR CATEGORIA (CP)", color = EFWhite, fontWeight = FontWeight.Bold)
                    EFInput("Distribuição", progression, { progression = it }, minLines = 4)
                    Text("EFEITOS DO BOOSTER (JSON)", color = EFWhite, fontWeight = FontWeight.Bold)
                    EFInput("Ex.: {\"speed\":2,\"acceleration\":2}", boosterEffects, { boosterEffects = it }, minLines = 2)
                    EFInput("Observações", notes, { notes = it }, minLines = 2)
                    Button(
                        onClick = { imagePicker.launch("image/*") },
                        modifier = Modifier.fillMaxWidth(),
                        colors = ButtonDefaults.buttonColors(containerColor = EFPanel)
                    ) { Text("IMPORTAR ATRIBUTOS DE UM PRINT", color = EFWhite) }
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Button(
                            onClick = {
                                scope.launch {
                                    try {
                                        val result = api.request("/api/mobile/efootball/simulate", "POST", buildPayload(
                                            cardName, playerId, buildName, cardType, position, level, maxLevel,
                                            overall, booster, baseStats, progression, boosterEffects, notes
                                        ))
                                        simulation = result
                                    } catch (e: Exception) { errorSetter(e.message ?: "Falha na simulação.") }
                                }
                            },
                            modifier = Modifier.weight(1f),
                            colors = ButtonDefaults.buttonColors(containerColor = EFPanel)
                        ) { Text("SIMULAR", color = EFWhite) }
                        Button(
                            onClick = {
                                scope.launch {
                                    try {
                                        val result = api.request("/api/mobile/efootball/optimize", "POST", buildPayload(
                                            cardName, playerId, buildName, cardType, position, level, maxLevel,
                                            overall, booster, baseStats, progression, boosterEffects, notes
                                        ))
                                        progression = (result.optJSONObject("category_points") ?: JSONObject()).toString(2)
                                        simulation = result
                                    } catch (e: Exception) { errorSetter(e.message ?: "Falha na otimização.") }
                                }
                            },
                            modifier = Modifier.weight(1f),
                            colors = ButtonDefaults.buttonColors(containerColor = EFRed)
                        ) { Text("OTIMIZAR", color = EFWhite) }
                    }
                    Button(
                        onClick = {
                            scope.launch {
                                try {
                                    val result = api.request("/api/mobile/efootball/builds", "POST", buildPayload(
                                        cardName, playerId, buildName, cardType, position, level, maxLevel,
                                        overall, booster, baseStats, progression, boosterEffects, notes
                                    ))
                                    errorSetter("Build salva: ${result.optString("card_name")}.")
                                    refresh()
                                } catch (e: Exception) { errorSetter(e.message ?: "Falha ao salvar build.") }
                            }
                        },
                        modifier = Modifier.fillMaxWidth(),
                        colors = ButtonDefaults.buttonColors(containerColor = EFRed)
                    ) { Text("SALVAR BUILD", color = EFWhite, fontWeight = FontWeight.Bold) }
                }
                simulation?.let { result ->
                    EFCard {
                        Text("RESULTADO DA SIMULAÇÃO", color = EFWhite, fontWeight = FontWeight.Bold)
                        Text("PP usados: ${result.optInt("spent_pp")} / ${result.optInt("available_pp")} • Restantes: ${result.optInt("remaining_pp")}", color = EFRed, fontWeight = FontWeight.Bold)
                        if (result.has("role_fit_score")) Text("Adequação estimada à posição: ${result.optDouble("role_fit_score")}", color = EFWhite)
                        Text((result.optJSONObject("final_stats") ?: JSONObject()).toString(2), color = EFMuted, fontSize = 11.sp)
                        Text("O cálculo não reproduz o Overall Rating oficial da Konami.", color = EFMuted, fontSize = 10.sp)
                    }
                }
                EFCard {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text("BUILDS SALVAS", color = EFWhite, fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f))
                        TextButton(onClick = { refresh() }) { Text("ATUALIZAR", color = EFRed) }
                    }
                    if (builds.isEmpty()) Text("Nenhuma build cadastrada.", color = EFMuted, fontSize = 12.sp)
                    builds.forEach { b ->
                        Divider(color = Color(0xFF343944))
                        Text("${b.optString("card_name")} • ${b.optString("name")}", color = EFWhite, fontWeight = FontWeight.Bold)
                        Text("${b.optString("position")} • Nível ${b.optInt("level")}/${b.optInt("max_level")} • ${b.optInt("overall")} OVR", color = EFMuted, fontSize = 11.sp)
                        Text("PP: ${b.optJSONObject("calculation")?.optInt("spent_pp") ?: 0}/${b.optJSONObject("calculation")?.optInt("available_pp") ?: 0}", color = EFRed, fontSize = 11.sp)
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Checkbox(checked = compareIds.contains(b.optInt("id")), onCheckedChange = { checked ->
                                compareIds = if (checked) (compareIds + b.optInt("id")).takeLast(2).toSet() else compareIds - b.optInt("id")
                            })
                            Text("Selecionar para comparação", color = EFMuted, fontSize = 11.sp)
                            Spacer(Modifier.weight(1f))
                            TextButton(onClick = {
                                scope.launch {
                                    try {
                                        api.request("/api/mobile/efootball/builds/${b.optInt("id")}", "DELETE")
                                        refresh()
                                    } catch (e: Exception) { errorSetter(e.message ?: "Erro ao excluir build.") }
                                }
                            }) { Text("EXCLUIR", color = EFRed) }
                        }
                    }
                }
            }
            "Comparar" -> {
                EFCard {
                    Text("COMPARAÇÃO DE BUILDS", color = EFWhite, fontWeight = FontWeight.Bold)
                    Text("Marque duas builds na aba Player Builder para comparar os atributos finais.", color = EFMuted, fontSize = 12.sp)
                    val selected = builds.filter { compareIds.contains(it.optInt("id")) }
                    if (selected.size == 2) {
                        val first = selected[0]
                        val second = selected[1]
                        val a = first.optJSONObject("calculation")?.optJSONObject("final_stats") ?: JSONObject()
                        val b = second.optJSONObject("calculation")?.optJSONObject("final_stats") ?: JSONObject()
                        Text("${first.optString("card_name")} × ${second.optString("card_name")}", color = EFRed, fontWeight = FontWeight.Bold)
                        (a.keys().asSequence() + b.keys().asSequence()).toSet().sorted().forEach { key ->
                            Text("$key: ${a.optInt(key, 0)} × ${b.optInt(key, 0)}", color = EFWhite, fontSize = 12.sp)
                        }
                    } else {
                        Text("Selecione exatamente duas builds salvas.", color = EFMuted, fontSize = 12.sp)
                    }
                }
            }
            else -> {
                EFCard {
                    Text("MONTADOR TÁTICO", color = EFWhite, fontWeight = FontWeight.Bold)
                    EFInput("Nome do plano", tacticName, { tacticName = it })
                    Text("Formação", color = EFMuted, fontSize = 11.sp)
                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        listOf("4-2-1-3", "4-3-3", "4-2-2-2").forEach { f ->
                            Text(f, color = if (formation == f) EFWhite else EFMuted,
                                modifier = Modifier.background(if (formation == f) EFRed else EFPanel, RoundedCornerShape(7.dp))
                                    .clickable { formation = f; lineup.clear() }.padding(9.dp), fontSize = 11.sp)
                        }
                    }
                    EFInput("Estilo de jogo", playstyle, { playstyle = it })
                    formationSlots(formation).forEach { slot ->
                        EFPlayerPicker(slot, players, lineup[slot] ?: "") { id -> lineup[slot] = id }
                    }
                    Button(
                        onClick = {
                            scope.launch {
                                try {
                                    val arr = JSONArray()
                                    formationSlots(formation).forEach { slot ->
                                        val id = lineup[slot]?.toIntOrNull()
                                        arr.put(JSONObject().put("slot", slot).put("player_id", id ?: JSONObject.NULL).put("role", slot))
                                    }
                                    val payload = JSONObject().put("name", tacticName).put("formation", formation)
                                        .put("playstyle", playstyle).put("lineup", arr)
                                    val saved = api.request("/api/mobile/efootball/squad-plans", "POST", payload)
                                    errorSetter("Plano tático salvo (#${saved.optInt("id")}).")
                                    refresh()
                                } catch (e: Exception) { errorSetter(e.message ?: "Falha ao salvar plano tático.") }
                            }
                        },
                        modifier = Modifier.fillMaxWidth(),
                        colors = ButtonDefaults.buttonColors(containerColor = EFRed)
                    ) { Text("SALVAR ESCALAÇÃO", color = EFWhite, fontWeight = FontWeight.Bold) }
                }
                EFCard {
                    Text("PLANOS SALVOS", color = EFWhite, fontWeight = FontWeight.Bold)
                    if (plans.isEmpty()) Text("Nenhum plano tático cadastrado.", color = EFMuted, fontSize = 12.sp)
                    plans.forEach { plan ->
                        Divider(color = Color(0xFF343944))
                        Text(plan.optString("name"), color = EFWhite, fontWeight = FontWeight.Bold)
                        Text("${plan.optString("formation")} • ${plan.optString("playstyle")}", color = EFMuted, fontSize = 11.sp)
                        TextButton(onClick = {
                            scope.launch {
                                try {
                                    api.request("/api/mobile/efootball/squad-plans/${plan.optInt("id")}", "DELETE")
                                    refresh()
                                } catch (e: Exception) { errorSetter(e.message ?: "Erro ao excluir plano.") }
                            }
                        }) { Text("EXCLUIR PLANO", color = EFRed) }
                    }
                }
            }
        }
    }
}

@Composable
private fun EFCard(content: @Composable ColumnScope.() -> Unit) {
    Column(
        Modifier.fillMaxWidth().background(EFPanel, RoundedCornerShape(13.dp)).padding(14.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
        content = content
    )
}

@Composable
private fun EFInput(
    label: String,
    value: String,
    onChange: (String) -> Unit,
    modifier: Modifier = Modifier,
    minLines: Int = 1,
) {
    OutlinedTextField(
        value = value,
        onValueChange = onChange,
        label = { Text(label) },
        modifier = modifier.fillMaxWidth(),
        minLines = minLines,
        textStyle = androidx.compose.ui.text.TextStyle(color = EFWhite, fontSize = 12.sp),
        colors = OutlinedTextFieldDefaults.colors(
            focusedBorderColor = EFRed,
            unfocusedBorderColor = Color(0xFF454B59),
            focusedLabelColor = EFRed,
            unfocusedLabelColor = EFMuted,
            cursorColor = EFRed,
        )
    )
}

@Composable
private fun EFPlayerPicker(
    slot: String,
    players: List<JSONObject>,
    selectedId: String,
    onSelect: (String) -> Unit,
) {
    var expanded by remember { mutableStateOf(false) }
    val selectedName = players.firstOrNull { it.optInt("id").toString() == selectedId }?.optString("name") ?: "Selecionar jogador"
    Box {
        OutlinedButton(onClick = { expanded = true }, modifier = Modifier.fillMaxWidth()) {
            Text("$slot • $selectedName", color = EFWhite, fontSize = 11.sp)
        }
        DropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
            DropdownMenuItem(text = { Text("Sem jogador") }, onClick = { onSelect(""); expanded = false })
            players.forEach { player ->
                DropdownMenuItem(
                    text = { Text(player.optString("name") + " • " + player.optString("position")) },
                    onClick = { onSelect(player.optInt("id").toString()); expanded = false }
                )
            }
        }
    }
}

private fun buildPayload(
    cardName: String, playerId: String, buildName: String, cardType: String, position: String,
    level: String, maxLevel: String, overall: String, booster: String,
    attributes: String, progression: String, boosterEffects: String, notes: String,
): JSONObject {
    return JSONObject()
        .put("card_name", cardName.trim())
        .put("player_id", playerId.toIntOrNull() ?: JSONObject.NULL)
        .put("name", buildName)
        .put("card_type", cardType)
        .put("position", position)
        .put("level", level.toIntOrNull() ?: 1)
        .put("max_level", maxLevel.toIntOrNull() ?: 30)
        .put("overall", overall.toIntOrNull() ?: JSONObject.NULL)
        .put("booster", booster)
        .put("attributes", JSONObject(attributes.ifBlank { "{}" }))
        .put("progression", JSONObject(progression.ifBlank { "{}" }))
        .put("booster_effects", JSONObject(boosterEffects.ifBlank { "{}" }))
        .put("notes", notes)
}

private fun formationSlots(formation: String): List<String> = when (formation) {
    "4-3-3" -> listOf("GK","LB","CB1","CB2","RB","DMF","CMF1","CMF2","LWF","CF","RWF")
    "4-2-2-2" -> listOf("GK","LB","CB1","CB2","RB","DMF1","DMF2","AMF1","AMF2","CF1","CF2")
    else -> listOf("GK","LB","CB1","CB2","RB","DMF","CMF","AMF","LWF","CF","RWF")
}

private fun efJsonArray(obj: JSONObject, key: String): List<JSONObject> {
    val array = obj.optJSONArray(key) ?: return emptyList()
    return (0 until array.length()).mapNotNull { array.optJSONObject(it) }
}
