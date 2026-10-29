package io.github.bbarrosdavi.financas.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.DatePicker
import androidx.compose.material3.DatePickerDialog
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExtendedFloatingActionButton
import androidx.compose.material3.Icon
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberDatePickerState
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import org.json.JSONArray
import org.json.JSONObject
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneOffset
import kotlin.math.abs

/** O tipo que a tabela do site mostra para cada lançamento. */
fun tipoLanc(l: JSONObject): String {
    if (l.optBoolean("pendente")) return "Pendente"
    val nats = l.lista("partes").map { it.s("natureza") }.toSet()
    if (nats.size > 1) return "Dividido"
    return when (nats.firstOrNull()) {
        "poupanca" -> "Poupança"; "renda" -> "Entrada"; "transferencia" -> "Transferência"
        "gasto" -> if (l.d("valor") > 0) "Estorno" else "Saída"
        else -> "Acerto"
    }
}

private val TIPOS = listOf("Entrada", "Saída", "Transferência", "Acerto", "Dividido", "Estorno", "Poupança", "Pendente")

@Composable
private fun corTipo(t: String): Color = when (t) {
    "Pendente" -> cores.atencao; "Entrada", "Estorno" -> cores.ok; "Saída" -> cores.ruim; "Transferência", "Poupança" -> cores.acento
    else -> cores.s3
}

@Composable
fun TelaLancamentos() {
    val base = carregar { Api.lista("/api/meses").let { a -> (0 until a.length()).map { a.getString(it) } } to Api.lista("/api/contas").objs() }
    val (meses, contas) = base.dado ?: return EstadoCarga(base)
    var categoria by rememberSaveable { mutableStateOf("") }
    var tipo by rememberSaveable { mutableStateOf("") }
    var busca by rememberSaveable { mutableStateOf("") }
    var de by rememberSaveable { mutableStateOf("") }
    var ate by rememberSaveable { mutableStateOf("") }
    var buscaAtiva by remember { mutableStateOf(busca) }
    LaunchedEffect(busca) { delay(300); buscaAtiva = busca }
    val c = carregar(de, ate, categoria, tipo, buscaAtiva) {
        val q = listOfNotNull(de.takeIf { it.isNotEmpty() }?.let { "de=$it" },
            ate.takeIf { it.isNotEmpty() }?.let { "ate=$it" }, categoria.takeIf { it.isNotEmpty() }?.let { "categoria=${Api.q(it)}" },
            buscaAtiva.takeIf { it.isNotBlank() }?.let { "busca=${Api.q(it)}" }, if (tipo == "Pendente") "pendentes=true" else null).joinToString("&")
        Api.lista("/api/lancamentos?$q").objs().filter { tipo.isEmpty() || tipoLanc(it) == tipo }
    }
    var editando by remember { mutableStateOf<JSONObject?>(null) }
    var lancando by remember { mutableStateOf(false) }

    Box(Modifier.fillMaxSize()) {
        LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(start = 10.dp, end = 10.dp, top = 8.dp, bottom = 80.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)) {
            item { Resumo(c.dado, contas, "") }
            // Os filtros no modelo da navegação do Orçamento.
            item {
                Cartao(modifier = Modifier.alvo("lancFiltros")) {
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Seletor("Tipo", listOf("" to "todos") + TIPOS.map { it to it }, tipo, Modifier.weight(1f)) { tipo = it }
                        var escolher by remember { mutableStateOf(false) }
                        CampoToque("Categoria", if (categoria.isEmpty()) "todas" else Vocab.categoria(categoria)?.s("nome"), Modifier.weight(1f)) { escolher = true }
                        if (escolher) EscolherDaLista("Categoria", listOf("" to "todas as categorias") +
                            Vocab.categorias.map { it.s("id") to "${it.s("grupo")}: ${it.s("nome")}" }, { escolher = false }) { categoria = it }
                    }
                    Row(Modifier.padding(top = 6.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        CampoData("De", de, Modifier.weight(1f)) { de = it }
                        Text("a", color = cores.mudo, fontSize = 12.sp)
                        CampoData("Até", ate, Modifier.weight(1f)) { ate = it }
                    }
                    Row(Modifier.padding(top = 6.dp), verticalAlignment = Alignment.CenterVertically) {
                        Campo(busca, { busca = it }, "", Modifier.weight(1f), dica = "Buscar")
                        if (de.isNotEmpty() || ate.isNotEmpty() || categoria.isNotEmpty() || tipo.isNotEmpty() || busca.isNotEmpty())
                            TextButton(onClick = { de = ""; ate = ""; categoria = ""; tipo = ""; busca = "" }) {
                                Text("Limpar", color = cores.acento, fontSize = 13.sp)
                            }
                    }
                }
            }
            val ls = c.dado
            if (ls == null) item { EstadoCarga(c) }
            else if (ls.isEmpty()) item { Vazio("Nenhum lançamento com estes filtros.") }
            else items(ls, key = { it.optInt("id") }) { l ->
                val primeiro = l === ls.first()
                LinhaLanc(l, if (primeiro) Modifier.alvo("lancLista") else Modifier) { editando = l }
            }
        }
        ExtendedFloatingActionButton(onClick = { lancando = true }, containerColor = cores.acento, contentColor = Color.White,
            icon = { Icon(Icones.adicionar, null) }, text = { Text("Lançar") },
            // O rótulo do botão estendido chega vazio ao leitor de tela; a descrição vai no próprio botão.
            modifier = Modifier.align(Alignment.BottomEnd).padding(16.dp).alvo("lancNovo").semantics { contentDescription = "Lançar" })
    }
    editando?.let { l -> EditorPartes(l) { editando = null } }
    if (lancando) NovoLancamento { lancando = false }
}

@Composable
private fun Resumo(dados: List<JSONObject>?, contas: List<JSONObject>, mes: String) {
    // Com um mês escolhido, a renda conta no mês em que entra (Ajustes > Mês da entrada, a mesma regra do Painel)
    // e o gasto conta pela data.
    val ls = dados.orEmpty()
    fun soma(linhas: List<JSONObject>, natureza: String) = linhas.flatMap { it.lista("partes") }.filter { it.s("natureza") == natureza }.sumOf { it.d("valor") }
    val ent = soma(ls.filter { mes.isEmpty() || it.s("mes_renda") == mes }, "renda")
    val gas = -soma(ls.filter { mes.isEmpty() || it.s("data").startsWith(mes) }, "gasto")
    val conta = contas.firstOrNull { it.s("id") == "nubank_conta" }
    val falta = conta?.takeIf { it.dn("saldo_real") != null }?.d("diferenca")
    var informar by remember { mutableStateOf(false) }
    Cartao("Resumo", Modifier.alvo("lancResumo"), sub = "do que está filtrado", subJunto = true,
        ajuda = "Entradas, gastos e resultado do que está filtrado; com um mês escolhido, a renda conta no mês em que entra, como no Painel, e o gasto pela data. " +
            "**Falta lançar na conta** é a diferença entre o saldo que o app do banco mostra e o que os lançamentos somam, e não depende do filtro.") {
        Row {
            Column(Modifier.weight(1f)) { Rotulo("Entradas"); Text(brl(ent), color = cores.texto, fontWeight = FontWeight.Bold, fontSize = 17.sp) }
            Column(Modifier.weight(1f)) { Rotulo("Gastos"); Text(brl(gas), color = cores.texto, fontWeight = FontWeight.Bold, fontSize = 17.sp) }
        }
        Spacer(Modifier.height(10.dp))
        Row {
            Column(Modifier.weight(1f)) {
                Rotulo("Resultado")
                Text(sinal(ent - gas), color = if (ent - gas < 0) cores.ruim else cores.ok, fontWeight = FontWeight.Bold, fontSize = 17.sp)
                Text("${dados?.size ?: 0} lançamento(s) · ${dados.orEmpty().count { it.optBoolean("pendente") }} pendente(s)", color = cores.mudo, fontSize = 11.sp)
            }
            Column(Modifier.weight(1f).clickable { informar = true }) {
                Rotulo("Falta lançar na conta")
                val bate = falta != null && abs(falta) < .005
                Text(if (falta == null) "?" else brl(abs(falta)), color = when { falta == null -> cores.mudo; bate -> cores.ok; else -> cores.atencao },
                    fontWeight = FontWeight.Bold, fontSize = 17.sp)
                Text(when { falta == null -> "toque para informar o saldo do app"; bate -> "o saldo do app bate"
                    else -> (if (falta < 0) "gasto" else "entrada") + " que o app já mostra e ainda não entrou aqui" }, color = cores.mudo, fontSize = 11.sp)
            }
        }
    }
    if (informar) InformarSaldo { informar = false }
}

@Composable
private fun LinhaLanc(l: JSONObject, modifier: Modifier, aoTocar: () -> Unit) {
    val t = tipoLanc(l)
    val partes = l.lista("partes")
    Cartao(modifier = modifier.tocarOuSegurar(categoria = partes.firstOrNull { it.s("categoria").isNotEmpty() }?.s("categoria"), aoTocar = aoTocar)) {
        Row(verticalAlignment = Alignment.Top) {
            Column(Modifier.weight(1f)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(t, color = corTipo(t), fontSize = 11.sp, fontWeight = FontWeight.SemiBold,
                        modifier = Modifier.background(corTipo(t).copy(alpha = .12f), RoundedCornerShape(6.dp)).padding(horizontal = 6.dp, vertical = 2.dp))
                    Text("  ${dataCurta(l.s("data"))} · ${Vocab.nomeConta(l.s("conta"))}", color = cores.mudo, fontSize = 12.sp)
                }
                Text(l.s("contraparte").ifEmpty { l.s("descricao") }, color = cores.texto, fontSize = 15.sp, fontWeight = FontWeight.SemiBold,
                    maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.padding(top = 3.dp))
                Text(if (l.optBoolean("pendente")) "a classificar" else partes.joinToString(" + ") { nomeParte(it).removePrefix("acerto ") + if (partes.size > 1) " " + brl(it.d("valor")) else "" },
                    color = if (l.optBoolean("pendente")) cores.atencao else cores.texto2, fontSize = 13.sp, maxLines = 2, overflow = TextOverflow.Ellipsis)
                val extra = listOfNotNull(l.s("descricao").takeIf { l.s("contraparte").isNotEmpty() && it.isNotEmpty() },
                    l.sn("parcela")?.takeIf { it.isNotEmpty() }?.let { "parcela $it" },
                    l.s("mes_renda").takeIf { it.length == 7 && !l.s("data").startsWith(it) }?.let { "entra em ${mesCurto(it)}" },
                    ORIGEM[l.s("origem")], l.sn("nota")?.takeIf { it.isNotEmpty() })
                if (extra.isNotEmpty()) Text(extra.joinToString(" · "), color = cores.mudo, fontSize = 11.sp, maxLines = 2, overflow = TextOverflow.Ellipsis)
            }
            Column(horizontalAlignment = Alignment.End, modifier = Modifier.padding(start = 8.dp)) {
                Text(brl(l.d("valor")), color = if (l.d("valor") > 0) cores.ok else cores.texto, fontWeight = FontWeight.Bold, fontSize = 15.sp)
                if (l.has("saldo_conta") && !l.isNull("saldo_conta"))
                    Text("saldo ${brl(l.d("saldo_conta"))}", color = if (l.d("saldo_conta") < 0) cores.ruim else cores.mudo, fontSize = 11.sp)
            }
        }
    }
}

private val TIPOS_NOVO = listOf("saida" to "Saída", "entrada" to "Entrada", "guardar" to "Guardar em meta", "resgatar" to "Resgatar de meta",
    "paguei" to "Acerto: paguei", "recebi" to "Acerto: recebi", "transf" to "Transferência")

/** Lançar à mão (a linha nova da tabela do site): dinheiro vivo, uma conta, um acerto, uma transferência. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun NovoLancamento(aoFechar: () -> Unit) {
    val escopo = rememberCoroutineScope()
    val folha = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    var tipo by remember { mutableStateOf("saida") }
    var alvo by remember { mutableStateOf<String?>(null) }
    var valor by remember { mutableStateOf("") }
    var desc by remember { mutableStateOf("") }
    var data by remember { mutableStateOf(LocalDate.now()) }
    var conta by remember { mutableStateOf(Vocab.contas.firstOrNull()?.s("id") ?: "nubank_conta") }
    var entrou by remember { mutableStateOf(false) }
    var escolherData by remember { mutableStateOf(false) }
    var erro by remember { mutableStateOf<String?>(null) }

    ModalBottomSheet(onDismissRequest = aoFechar, sheetState = folha, containerColor = cores.painelForte) {
        Column(Modifier.verticalScroll(rememberScrollState()).padding(horizontal = 16.dp).padding(bottom = 16.dp).navigationBarsPadding(),
            verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text("Lançar", color = cores.texto, fontSize = 20.sp, fontWeight = FontWeight.Bold)
            Seletor("Tipo", TIPOS_NOVO, tipo) { tipo = it; alvo = null }
            when (tipo) {
                "saida", "entrada" -> SeletorCategoria(if (tipo == "saida") "gasto" else "renda", alvo) { alvo = it }
                "guardar", "resgatar" -> {
                    val metas = Vocab.metas.filter { it.optInt("ativa") == 1 }
                    if (metas.isEmpty()) Vazio("Crie uma meta em Orçamento > Metas.")
                    else Seletor("Meta", metas.map { it.optInt("id").toString() to it.s("nome") }, alvo) { alvo = it }
                }
                "paguei", "recebi" -> Seletor("Pessoa", Vocab.pessoas.map { it.s("id") to it.s("nome") }, alvo) { alvo = it }
                else -> Segmentos(listOf("saiu" to "Saiu desta conta", "entrou" to "Entrou nesta conta"), if (entrou) "entrou" else "saiu") { entrou = it == "entrou" }
            }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Campo(valor, { valor = it }, "Valor", Modifier.weight(1f), numerico = true, dica = "0,00")
                CampoToque("Data", dataBR(data.toString()), Modifier.weight(1f).padding(top = 8.dp)) { escolherData = true }
            }
            Campo(desc, { desc = it }, "O que foi")
            Seletor("Conta", Vocab.contas.map { it.s("id") to Vocab.nomeConta(it.s("id")) }, conta) { conta = it }
            erro?.let { Text(it, color = cores.ruim, fontSize = 13.sp) }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                BotaoPrimario("Lançar", Modifier.weight(1f)) {
                    val v = numero(valor)?.let { abs(it) }
                    if (v == null || v == 0.0 || desc.isBlank()) { erro = "Preencha o valor e o que foi."; return@BotaoPrimario }
                    if (tipo != "transf" && alvo == null) { erro = "Escolha a categoria, a meta ou a pessoa."; return@BotaoPrimario }
                    val saida = tipo in setOf("saida", "guardar", "paguei") || (tipo == "transf" && !entrou)
                    val vv = if (saida) -v else v
                    val parte = when (tipo) {
                        "saida" -> jsonDe("natureza" to "gasto", "categoria" to alvo)
                        "entrada" -> jsonDe("natureza" to "renda", "categoria" to alvo)
                        "guardar", "resgatar" -> jsonDe("natureza" to "poupanca", "meta" to alvo?.toIntOrNull())
                        "paguei", "recebi" -> jsonDe("natureza" to "acerto", "pessoa" to alvo)
                        else -> jsonDe("natureza" to "transferencia")
                    }.put("valor", vv).put("obs", "")
                    escopo.launch {
                        try {
                            Api.post("/api/lancamentos", jsonDe("data" to data.toString(), "conta" to conta, "valor" to vv, "descricao" to desc.trim())
                                .put("partes", JSONArray().put(parte)))
                            Vocab.carregar(); Estado.mudou(); Estado.mensagem = "Lançado."; aoFechar()
                        } catch (e: Exception) { erro = e.message }
                    }
                }
                BotaoSecundario("Cancelar", aoTocar = aoFechar)
            }
        }
    }
    if (escolherData) {
        val estado = rememberDatePickerState(initialSelectedDateMillis = data.atStartOfDay().toInstant(ZoneOffset.UTC).toEpochMilli())
        DatePickerDialog(onDismissRequest = { escolherData = false },
            confirmButton = { TextButton(onClick = {
                estado.selectedDateMillis?.let { data = Instant.ofEpochMilli(it).atZone(ZoneOffset.UTC).toLocalDate() }; escolherData = false
            }) { Text("OK", color = cores.acento) } },
            dismissButton = { TextButton(onClick = { escolherData = false }) { Text("Cancelar", color = cores.texto2) } }) {
            DatePicker(estado)
        }
    }
}


/** Uma data do filtro (AAAA-MM-DD, ou vazia): toque escolhe no calendário, "Limpar" tira. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun CampoData(rotulo: String, valor: String, modifier: Modifier = Modifier, aoEscolher: (String) -> Unit) {
    var aberto by remember { mutableStateOf(false) }
    CampoToque(rotulo, valor.takeIf { it.length == 10 }?.let { "${it.substring(8, 10)}/${it.substring(5, 7)}/${it.substring(2, 4)}" } ?: "qualquer", modifier) { aberto = true }
    if (aberto) {
        val inicial = valor.takeIf { it.length == 10 }?.let { LocalDate.parse(it) } ?: LocalDate.now()
        val estado = rememberDatePickerState(initialSelectedDateMillis = inicial.atStartOfDay().toInstant(ZoneOffset.UTC).toEpochMilli())
        DatePickerDialog(onDismissRequest = { aberto = false },
            confirmButton = { TextButton(onClick = {
                estado.selectedDateMillis?.let { aoEscolher(Instant.ofEpochMilli(it).atZone(ZoneOffset.UTC).toLocalDate().toString()) }; aberto = false
            }) { Text("OK", color = cores.acento) } },
            dismissButton = { TextButton(onClick = { aoEscolher(""); aberto = false }) { Text("Limpar", color = cores.texto2) } }) {
            DatePicker(estado)
        }
    }
}
