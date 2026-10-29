package io.github.bbarrosdavi.financas.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import kotlinx.coroutines.launch
import org.json.JSONArray
import org.json.JSONObject
import kotlin.math.abs
import kotlin.math.roundToLong

val ORIGEM = mapOf("manual" to "lançado à mão", "push" to "pelo celular")

fun arred(v: Double) = (v * 100).roundToLong() / 100.0

/** Uma parte já decidida: gasto/renda com categoria, acerto com pessoa, poupança com meta, ou transferência. */
fun parteOk(p: JSONObject): Boolean {
    val n = p.s("natureza")
    return !((n == "gasto" || n == "renda") && p.sn("categoria") == null) && !(n == "acerto" && p.sn("pessoa") == null) &&
        !(n == "poupanca" && p.dn("meta") == null)
}

fun nomeParte(p: JSONObject): String = when {
    p.sn("categoria") != null -> Vocab.categoria(p.s("categoria"))?.s("nome") ?: p.s("categoria")
    p.sn("pessoa") != null -> "acerto " + (Vocab.pessoa(p.s("pessoa"))?.s("nome") ?: "")
    p.dn("meta") != null -> "meta " + (Vocab.meta(p.optInt("meta"))?.s("nome") ?: "")
    else -> NATUREZA[p.s("natureza")] ?: p.s("natureza")
}

fun descreverPartes(ps: List<JSONObject>) = ps.joinToString(" + ") { nomeParte(it) + if (ps.size > 1) " " + brl(it.d("valor")) else "" }

/** A linha de baixo do nome: data, conta, descrição do banco, parcela, origem e a sua observação. */
fun detalheLanc(l: JSONObject, comDescricao: Boolean = true) = listOfNotNull(
    dataBR(l.s("data")), Vocab.nomeConta(l.s("conta")), l.s("descricao").takeIf { comDescricao && it.isNotEmpty() },
    l.sn("parcela")?.takeIf { it.isNotEmpty() }?.let { "parcela $it" }, ORIGEM[l.s("origem")], l.sn("nota")?.takeIf { it.isNotEmpty() },
).joinToString(" · ")

@Composable
fun TelaPendentes() {
    val c = carregar { Api.lista("/api/lancamentos?pendentes=true").objs()       // por data, para a triagem
        .sortedWith(compareByDescending<JSONObject> { it.s("data") }.thenByDescending { it.optInt("id") }) }
    val ls = c.dado ?: return EstadoCarga(c)
    var lembrar by rememberSaveable { mutableStateOf(true) }
    var editando by remember { mutableStateOf<JSONObject?>(null) }
    LazyColumn(Modifier.fillMaxWidth(), contentPadding = androidx.compose.foundation.layout.PaddingValues(horizontal = 10.dp, vertical = 8.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp)) {
        item {
            Cartao(modifier = Modifier.alvo("pendentes")) {
                Text(if (ls.isEmpty()) "Tudo classificado." else "${ls.size} esperando você", color = cores.texto, fontWeight = FontWeight.SemiBold, fontSize = 16.sp)
                Text("Toque na sugestão ou numa categoria.", color = cores.texto2, fontSize = 13.sp)
                Marcar("sugerir a mesma classificação da próxima vez para o mesmo lugar", lembrar) { lembrar = it }
            }
        }
        items(ls, key = { it.optInt("id") }) { l -> ItemPendente(l, lembrar) { editando = l } }
    }
    editando?.let { l -> EditorPartes(l) { editando = null } }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun ItemPendente(l: JSONObject, lembrar: Boolean, aoDividir: () -> Unit) {
    val escopo = rememberCoroutineScope()
    val partes = l.lista("partes")
    val conhecidas = partes.filter(::parteOk)
    val poupSemMeta = partes.firstOrNull { it.s("natureza") == "poupanca" && it.dn("meta") == null }
    val falta = arred(l.d("valor") - conhecidas.sumOf { it.d("valor") })
    val tipo = if (falta < 0) "gasto" else "renda"
    val cats = Vocab.categorias.filter { it.s("tipo") == tipo }
    val pergunta = partes.firstOrNull { !parteOk(it) }?.let { p -> p.s("motivo").ifEmpty { p.s("obs") } }?.takeIf { it.isNotEmpty() }
    val sugestao = l.optJSONArray("sugestao")?.objs()
    val metas = Vocab.metas.filter { it.optInt("ativa") == 1 }
    var todas by remember { mutableStateOf(false) }
    var ocupado by remember { mutableStateOf(false) }

    fun classificar(ps: List<JSONObject>, lembrarEste: Boolean) {
        if (ocupado) return
        ocupado = true
        escopo.launch {
            gravar { Api.put("/api/lancamentos/${l.optInt("id")}/partes", JSONObject().put("partes", JSONArray(ps)).put("lembrar", lembrarEste)) }
            ocupado = false
        }
    }
    fun nova(parte: JSONObject) {
        val ps = conhecidas + parte.put("valor", falta).put("obs", "")
        classificar(ps, lembrar && ps.size == 1)
    }

    Cartao {
        Row(verticalAlignment = Alignment.Top) {
            Column(Modifier.weight(1f)) {
                Text(l.s("contraparte").ifEmpty { l.s("descricao") }, color = cores.texto, fontWeight = FontWeight.SemiBold, fontSize = 15.sp)
                Text(detalheLanc(l), color = cores.mudo, fontSize = 12.sp)
                if (conhecidas.isNotEmpty()) Text("já separado: " + conhecidas.joinToString(", ") { (it.s("motivo").ifEmpty { it.s("obs") }.ifEmpty { NATUREZA[it.s("natureza")] ?: "" }) + " " + brl(it.d("valor")) },
                    color = cores.texto2, fontSize = 12.sp)
                if (pergunta != null) Text(pergunta, color = cores.texto2, fontSize = 12.sp)
            }
            Text(brl(falta), color = if (l.d("valor") < 0) cores.ruim else cores.ok, fontWeight = FontWeight.Bold, fontSize = 16.sp, modifier = Modifier.padding(start = 8.dp))
        }
        Spacer(Modifier.height(8.dp))
        FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            if (sugestao != null) Ficha("Sugestão: " + descreverPartes(sugestao), primario = true) { classificar(sugestao, false) }
            if (poupSemMeta != null) metas.forEach { m ->
                Ficha("Meta: ${m.s("nome")}", primario = true) {
                    classificar(partes.map { p -> if (p === poupSemMeta) JSONObject(p.toString()).put("meta", m.optInt("id")) else p }, false)
                }
            }
            cats.sortedByDescending { it.optInt("uso") }.take(6).forEach { cat -> Ficha(cat.s("nome")) { nova(jsonDe("natureza" to tipo, "categoria" to cat.s("id"))) } }
            Vocab.pessoas.filter { it.s("tipo") != "credor" }.take(3).forEach { p ->
                Ficha("Acerto: ${p.s("nome")}") { nova(jsonDe("natureza" to "acerto", "pessoa" to p.s("id"))) }
            }
            Ficha(if (todas) "menos" else "outras...", ativo = todas) { todas = !todas }
            Ficha("Dividir...") { aoDividir() }
        }
        if (todas) {
            cats.groupBy { it.s("grupo") }.forEach { (g, cs) ->
                Rotulo(g, Modifier.padding(top = 10.dp, bottom = 4.dp))
                FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    cs.forEach { cat -> Ficha(cat.s("nome")) { nova(jsonDe("natureza" to tipo, "categoria" to cat.s("id"))) } }
                }
            }
            Rotulo("Não é $tipo seu", Modifier.padding(top = 10.dp, bottom = 4.dp))
            FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Vocab.pessoas.forEach { p -> Ficha("Acerto: ${p.s("nome")}") { nova(jsonDe("natureza" to "acerto", "pessoa" to p.s("id"))) } }
                Ficha("Transferência entre contas suas") { nova(jsonDe("natureza" to "transferencia")) }
                metas.forEach { m -> Ficha((if (falta < 0) "Guardar em: " else "Resgate de: ") + m.s("nome")) {
                    nova(jsonDe("natureza" to "poupanca", "meta" to m.optInt("id"))) } }
            }
        }
    }
}

/** Uma parte em edição. Valor como texto para o campo aceitar "12,50" enquanto se digita. */
private data class ParteEd(val valor: String, val natureza: String, val categoria: String? = null, val pessoa: String? = null,
                           val meta: Int? = null, val obs: String = "", val motivo: String = "") {
    fun json() = jsonDe("valor" to (numero(valor) ?: 0.0), "natureza" to natureza, "categoria" to categoria, "pessoa" to pessoa,
        "meta" to meta, "obs" to obs, "motivo" to motivo)

    companion object {
        fun de(p: JSONObject) = ParteEd(valorTexto(p.d("valor")), p.s("natureza"), p.sn("categoria"), p.sn("pessoa"),
            p.dn("meta")?.toInt(), p.s("obs"), p.s("motivo"))
    }
}

/** Valor para um campo de edição: "90", "-89,90". */
fun valorTexto(v: Double): String = arred(v).let { if (it == Math.floor(it)) it.toLong().toString() else String.format(java.util.Locale.ROOT, "%.2f", it).replace('.', ',') }

/** O editor de partes do site: separar um lançamento em gasto, renda, acerto com pessoa, poupança ou transferência. */
@Composable
fun EditorPartes(l: JSONObject, aoFechar: () -> Unit) {
    val escopo = rememberCoroutineScope()
    val inicial = l.lista("partes").ifEmpty { l.optJSONArray("sugestao")?.objs() ?: emptyList() }
    val partes = remember {
        mutableStateListOf<ParteEd>().apply {
            if (inicial.isNotEmpty()) addAll(inicial.map(ParteEd::de))
            else add(ParteEd(valorTexto(l.d("valor")), if (l.d("valor") < 0) "gasto" else "renda"))
        }
    }
    var nota by remember { mutableStateOf(l.s("nota")) }
    var lembrar by remember { mutableStateOf(false) }
    var erro by remember { mutableStateOf<String?>(null) }
    var apagar by remember { mutableStateOf(false) }
    val soma = arred(partes.sumOf { numero(it.valor) ?: 0.0 })
    val id = l.optInt("id")

    Dialog(onDismissRequest = aoFechar, properties = DialogProperties(usePlatformDefaultWidth = false)) {
        Surface(shape = RoundedCornerShape(16.dp), color = cores.painelForte, modifier = Modifier.fillMaxWidth(.94f)) {
            Column(Modifier.verticalScroll(rememberScrollState()).padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(l.s("contraparte").ifEmpty { l.s("descricao") }, color = cores.texto, fontWeight = FontWeight.Bold, fontSize = 18.sp)
                Text(detalheLanc(l) + " · " + brl(l.d("valor")), color = cores.mudo, fontSize = 12.sp)
                Campo(nota, { nota = it }, "Obs", dica = "sua observação sobre este lançamento")
                partes.forEachIndexed { i, p ->
                    Surface(shape = RoundedCornerShape(10.dp), color = cores.fundo) {
                        Column(Modifier.padding(10.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                Campo(p.valor, { partes[i] = p.copy(valor = it) }, "Valor", Modifier.weight(1f), numerico = true)
                                Seletor("Tipo", NATUREZA.toList(), p.natureza, Modifier.weight(1.2f)) {
                                    partes[i] = p.copy(natureza = it, categoria = null, pessoa = null, meta = null, motivo = "")
                                }
                                IconButton(onClick = { partes.removeAt(i) }) { Icon(Icones.fechar, "Remover parte", tint = cores.mudo) }
                            }
                            when (p.natureza) {
                                "acerto" -> Seletor("Pessoa", Vocab.pessoas.map { it.s("id") to it.s("nome") }, p.pessoa) { partes[i] = p.copy(pessoa = it, motivo = "") }
                                "poupanca" -> Seletor("Meta", Vocab.metas.map { it.optInt("id").toString() to it.s("nome") }, p.meta?.toString()) {
                                    partes[i] = p.copy(meta = it.toInt(), motivo = "") }
                                "transferencia" -> Text("entre contas suas", color = cores.mudo, fontSize = 13.sp)
                                else -> SeletorCategoria(p.natureza, p.categoria) { partes[i] = p.copy(categoria = it, motivo = "") }
                            }
                            Campo(p.obs, { partes[i] = p.copy(obs = it) }, "Obs desta parte")
                            if (p.motivo.isNotEmpty()) Text(p.motivo, color = cores.mudo, fontSize = 12.sp)
                        }
                    }
                }
                Row(verticalAlignment = Alignment.CenterVertically) {
                    TextButton(onClick = { partes.add(ParteEd(valorTexto(l.d("valor") - soma), "gasto")) }) { Text("+ parte", color = cores.acento) }
                    Spacer(Modifier.weight(1f))
                    Text("soma ${brl(soma)} de ${brl(l.d("valor"))}", color = if (abs(soma - l.d("valor")) > .005) cores.ruim else cores.mudo, fontSize = 13.sp)
                }
                Marcar("sugerir isto da próxima vez para o mesmo lugar (só com uma parte)", lembrar) { lembrar = it }
                erro?.let { Text(it, color = cores.ruim, fontSize = 13.sp) }
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                    BotaoPrimario("Salvar") {
                        escopo.launch {
                            try {
                                Api.put("/api/lancamentos/$id/partes", JSONObject().put("partes", JSONArray(partes.map { it.json() })).put("nota", nota)
                                    .put("lembrar", lembrar && partes.size == 1))
                                Vocab.carregar(); Estado.mudou(); aoFechar()
                            } catch (e: Exception) { erro = e.message }
                        }
                    }
                    BotaoSecundario("Cancelar", aoTocar = aoFechar)
                    if (l.s("origem") in ORIGEM) TextButton(onClick = { apagar = true }) { Text("Apagar", color = cores.ruim) }
                }
            }
        }
    }
    if (apagar) Confirmar("Apagar lançamento", "Apagar este lançamento?", "Apagar", { apagar = false }) {
        escopo.launch { if (gravar("Lançamento apagado.") { Api.delete("/api/lancamentos/$id") }) aoFechar() }
    }
}
