package io.github.bbarrosdavi.financas.ui

import android.net.Uri
import android.provider.OpenableColumns
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject
import kotlin.math.max
import kotlin.math.min

// ---------------------------------------------------------------- importar

@Composable
fun TelaImportar() {
    val ctx = LocalContext.current
    val escopo = rememberCoroutineScope()
    var lendo by remember { mutableStateOf(false) }
    var resultado by remember { mutableStateOf<List<JSONObject>?>(null) }
    val escolher = rememberLauncherForActivityResult(ActivityResultContracts.OpenMultipleDocuments()) { uris: List<Uri> ->
        if (uris.isEmpty()) return@rememberLauncherForActivityResult
        lendo = true
        escopo.launch {
            try {
                val arquivos = withContext(Dispatchers.IO) {
                    uris.map { u ->
                        val nome = ctx.contentResolver.query(u, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use { c ->
                            if (c.moveToFirst()) c.getString(0) else null } ?: u.lastPathSegment ?: "arquivo"
                        nome to (ctx.contentResolver.openInputStream(u)?.use { it.readBytes() } ?: ByteArray(0))
                    }
                }
                resultado = Api.importar(arquivos).objs()
                Vocab.carregar(); Estado.mudou()
            } catch (e: Exception) { Estado.mensagem = e.message }
            lendo = false
        }
    }
    val listas = carregar { Api.lista("/api/ignorados").objs() to Api.lista("/api/importacoes").objs() }
    Column(Modifier.verticalScroll(rememberScrollState()).padding(horizontal = 10.dp, vertical = 8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Cartao("Extrato e fatura do banco", Modifier.alvo("importarArquivos"), sub = "Nubank ou Bradesco") {
            Text("Quantos quiser de uma vez: .csv ou .xlsx (o .pdf só no computador). O que já existe não duplica, e a compra que veio pelo celular é casada com a linha do arquivo. " +
                "Extrato que não fecha com o total do banco é recusado.", color = cores.texto2, fontSize = 13.sp)
            Spacer(Modifier.height(10.dp))
            BotaoPrimario(if (lendo) "Lendo..." else "Escolher arquivos", Modifier.fillMaxWidth(), habilitado = !lendo) {
                escolher.launch(arrayOf("text/csv", "text/comma-separated-values", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    "application/pdf", "application/octet-stream", "text/plain"))
            }
            resultado?.let { r ->
                Spacer(Modifier.height(10.dp))
                r.forEach { x ->
                    Column(Modifier.padding(vertical = 5.dp)) {
                        Text(x.s("arquivo"), color = cores.texto, fontWeight = FontWeight.SemiBold, fontSize = 14.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
                        if (x.sn("erro") != null) Text(x.s("erro"), color = cores.ruim, fontSize = 13.sp)
                        else {
                            Text("${x.s("tipo")} · ${x.optInt("novos")} novo(s) · ${x.optInt("casados")} casado(s) com o celular · ${x.optInt("repetidos")} já existia(m)",
                                color = cores.texto2, fontSize = 12.sp)
                            val avisos = x.optJSONArray("avisos")?.let { a -> (0 until a.length()).map { a.getString(it) } }.orEmpty()
                            if (avisos.isNotEmpty()) Text(avisos.joinToString("; "), color = cores.atencao, fontSize = 12.sp)
                        }
                    }
                }
            }
        }
        val (ign, imp) = listas.dado ?: return@Column EstadoCarga(listas)
        Cartao("Notificações descartadas", Modifier.alvo("importarDescartadas"), sub = "se alguma era compra, resgate") {
            if (ign.isEmpty()) Vazio("Nenhuma.")
            ign.forEach { i ->
                Row(Modifier.padding(vertical = 6.dp), verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text("${i.s("title")} | ${i.s("body")}", color = cores.texto, fontSize = 13.sp, maxLines = 3, overflow = TextOverflow.Ellipsis)
                        Text("${i.s("quando").take(16).replace('T', ' ')} · ${i.s("motivo")}", color = cores.mudo, fontSize = 11.sp)
                    }
                    TextButton(onClick = { escopo.launch { gravar("Resgatada: está em Pendentes.") { Api.post("/api/ignorados/${i.optInt("id")}/resgatar", JSONObject()) } } }) {
                        Text("Resgatar", color = cores.acento)
                    }
                }
            }
        }
        Cartao("Últimas importações") {
            if (imp.isEmpty()) Vazio("Nenhuma ainda.")
            Recentes(imp) { i ->
                Column(Modifier.padding(vertical = 5.dp)) {
                    Text(i.s("arquivo"), color = cores.texto, fontSize = 14.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    Text("${i.s("quando").take(16).replace('T', ' ')} · ${i.s("tipo")} · ${i.optInt("novos")} novo(s), ${i.optInt("casados")} casado(s), ${i.optInt("repetidos")} já existia(m)",
                        color = cores.mudo, fontSize = 11.sp)
                }
            }
        }
    }
}

// ---------------------------------------------------------------- pessoas

@Composable
fun TelaPessoas() {
    val c = carregar { Api.obj("/api/painel") to Api.lista("/api/lancamentos").objs() }
    var pagou by remember { mutableStateOf(false) }
    Column(Modifier.verticalScroll(rememberScrollState()).padding(horizontal = 10.dp, vertical = 8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        val (p, ls) = c.dado ?: return@Column EstadoCarga(c)
        val pessoas = p.lista("pessoas").filter { it.d("saldo") != 0.0 || it.d("a_vencer") != 0.0 }
        Cartao("Saldos", Modifier.alvo("pessoasSaldos"), sub = "positivo: te deve") {
            if (pessoas.isEmpty()) Vazio("Ninguém te deve e você não deve a ninguém.")
            pessoas.forEach { x ->
                Row(Modifier.padding(vertical = 6.dp), verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text(x.s("nome"), color = cores.texto, fontSize = 15.sp, fontWeight = FontWeight.SemiBold)
                        Text((if (x.d("saldo") < 0) "você deve" else "te deve") + (if (x.d("a_vencer") != 0.0) " · ${brl(x.d("a_vencer"))} em parcelas a vencer" else ""),
                            color = cores.mudo, fontSize = 12.sp)
                    }
                    Text(brl(x.d("saldo")), color = if (x.d("saldo") < 0) cores.ruim else cores.ok, fontWeight = FontWeight.Bold, fontSize = 15.sp)
                }
            }
        }
        Cartao("Alguém pagou por você", Modifier.alvo("pessoasPagou")) {
            Text("Condomínio, luz, gás, mercado da casa: o gasto é seu, o dinheiro saiu de outra pessoa. Vira gasto na categoria e dívida com ela, sem mexer no saldo da conta.",
                color = cores.texto2, fontSize = 13.sp)
            Spacer(Modifier.height(8.dp))
            BotaoPrimario("Lançar conta que alguém pagou", Modifier.fillMaxWidth()) { pagou = true }
        }
        CadastroPessoas()
        val acertos = ls.flatMap { l -> l.lista("partes").filter { it.s("natureza") == "acerto" }.map { l to it } }
        Cartao("Acertos recentes") {
            if (acertos.isEmpty()) Vazio("Nenhum acerto ainda.")
            Recentes(acertos) { (l, pt) ->
                Row(Modifier.padding(vertical = 5.dp), verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text("${Vocab.pessoa(pt.s("pessoa"))?.s("nome") ?: ""} · ${l.s("contraparte").ifEmpty { l.s("descricao") }}", color = cores.texto, fontSize = 14.sp,
                            maxLines = 1, overflow = TextOverflow.Ellipsis)
                        val obs = listOf(l.s("nota"), pt.s("obs"), pt.s("motivo")).filter { it.isNotEmpty() }.joinToString(" · ")
                        Text(dataBR(l.s("data")) + if (obs.isNotEmpty()) " · $obs" else "", color = cores.mudo, fontSize = 11.sp, maxLines = 2, overflow = TextOverflow.Ellipsis)
                    }
                    Text(brl(pt.d("valor")), color = cores.texto, fontWeight = FontWeight.SemiBold, fontSize = 14.sp)
                }
            }
        }
    }
    if (pagou) AlguemPagou { pagou = false }
}

@Composable
private fun AlguemPagou(aoFechar: () -> Unit) {
    val escopo = rememberCoroutineScope()
    var pessoa by remember { mutableStateOf(Vocab.pessoas.firstOrNull()?.s("id")) }
    var categoria by remember { mutableStateOf<String?>(null) }
    var valor by remember { mutableStateOf("") }
    var desc by remember { mutableStateOf("") }
    var data by remember { mutableStateOf(hojeISO()) }
    var erro by remember { mutableStateOf<String?>(null) }
    AlertDialog(onDismissRequest = aoFechar, containerColor = cores.painelForte, title = { Text("Alguém pagou por você") },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                if (Vocab.pessoas.isEmpty()) Text("Cadastre a pessoa em Ajustes > Pessoas.", color = cores.atencao)
                Seletor("Quem pagou", Vocab.pessoas.map { it.s("id") to it.s("nome") }, pessoa) { pessoa = it }
                Campo(valor, { valor = it }, "Sua parte (R$)", numerico = true)
                SeletorCategoria("gasto", categoria) { categoria = it }
                Campo(desc, { desc = it }, "O que foi", dica = "Luz de novembro")
                Campo(data, { data = it }, "Data (AAAA-MM-DD)")
                erro?.let { Text(it, color = cores.ruim, fontSize = 13.sp) }
            }
        },
        confirmButton = { TextButton(onClick = {
            val v = numero(valor)
            val nome = Vocab.pessoa(pessoa)?.s("nome")
            if (v == null || v <= 0 || nome == null || categoria == null || desc.isBlank()) { erro = "Preencha quem pagou, o valor, a categoria e o que foi."; return@TextButton }
            val partes = org.json.JSONArray()
                .put(jsonDe("valor" to -v, "natureza" to "gasto", "categoria" to categoria, "motivo" to "conta paga por $nome"))
                .put(jsonDe("valor" to v, "natureza" to "acerto", "pessoa" to pessoa, "motivo" to "$nome pagou por você"))
            escopo.launch {
                try {
                    Api.post("/api/lancamentos", jsonDe("data" to data.trim(), "conta" to "nubank_conta", "valor" to 0, "descricao" to desc.trim(), "contraparte" to nome)
                        .put("partes", partes))
                    Vocab.carregar(); Estado.mudou(); Estado.mensagem = "Lançado."; aoFechar()
                } catch (e: Exception) { erro = e.message }
            }
        }) { Text("Lançar", color = cores.acento) } },
        dismissButton = { TextButton(onClick = aoFechar) { Text("Cancelar", color = cores.texto2) } })
}

// ---------------------------------------------------------------- projeção

private val TIPO_EV = linkedMapOf("renda_mensal" to "Renda mensal muda", "gasto_mensal" to "Gasto mensal muda", "entrada_unica" to "Entrada única", "saida_unica" to "Saída única")

@Composable
fun TelaProjecao() {
    val c = carregar { Triple(Api.obj("/api/painel"), Api.obj("/api/parametros"), Api.lista("/api/eventos").objs()) }
    var evento by remember { mutableStateOf<JSONObject?>(null) }
    var novo by remember { mutableStateOf(false) }
    var premissas by remember { mutableStateOf(false) }
    Column(Modifier.verticalScroll(rememberScrollState()).padding(horizontal = 10.dp, vertical = 8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        val (p, prm, evs) = c.dado ?: return@Column EstadoCarga(c)
        val pl = p.getJSONObject("plano")
        val linhas = pl.lista("linhas")
        val fim = linhas.lastOrNull()
        val quitado = linhas.firstOrNull { it.d("deve_pessoas") == 0.0 }
        Cartao("Até ${mesCurto(pl.s("horizonte") + "-01")}", Modifier.alvo("projResumo")) {
            Row {
                Column(Modifier.weight(1f)) { Rotulo("Falta cobrir"); Text(brl(pl.d("falta_total")), color = if (pl.d("falta_total") > 0) cores.atencao else cores.ok,
                    fontWeight = FontWeight.Bold, fontSize = 17.sp); Text("soma dos meses no vermelho", color = cores.mudo, fontSize = 11.sp) }
                Column(Modifier.weight(1f)) { Rotulo("Saldo livre no fim"); Text(brl(fim?.d("livre") ?: 0.0), color = if ((fim?.d("livre") ?: 0.0) > 0) cores.ok else cores.atencao,
                    fontWeight = FontWeight.Bold, fontSize = 17.sp); Text("${brl(fim?.d("metas") ?: 0.0)} nas metas", color = cores.mudo, fontSize = 11.sp) }
            }
            LinhaKV("Quem você deve, quitado em", quitado?.let { mesLongo(it.s("mes")) } ?: "não quita no período")
            Spacer(Modifier.height(10.dp))
            GraficoProjecao(linhas)
            Text("Cartão: só as parcelas que ainda vão cair.", color = cores.mudo, fontSize = 12.sp)
        }
        Cartao("Mês a mês") {
            linhas.forEach { l ->
                Column(Modifier.padding(vertical = 6.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text(mesCurto(l.s("mes") + "-01"), color = cores.texto, fontWeight = FontWeight.SemiBold, modifier = Modifier.width(64.dp))
                        Text(sinal(l.d("resultado")), color = if (l.d("resultado") < 0) cores.ruim else cores.ok, fontWeight = FontWeight.Bold, fontSize = 14.sp, modifier = Modifier.weight(1f))
                        if (l.d("falta") > 0) Text("falta ${brl(l.d("falta"))}  ", color = cores.atencao, fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
                        Text("livre ${brl(l.d("livre"))}", color = cores.texto2, fontSize = 12.sp)
                    }
                    Text("renda ${brl(l.d("renda"))} · reemb. ${brl(l.d("reembolsos"))}" + (if (l.d("unicos") != 0.0) " · únicos ${sinal(l.d("unicos"))}" else "") +
                        " · custo ${brl(l.d("custo"))} · cartão ${brl(l.d("cartao"))} · metas ${brl(l.d("aportes"))} · devo ${brl(l.d("deve_pessoas"))}",
                        color = cores.mudo, fontSize = 11.sp)
                }
            }
        }
        Cartao("Premissas") {
            LinhaKV("Renda mensal base", brl(prm.optString("salario_mensal").toDoubleOrNull() ?: 0.0))
            LinhaKV("Horizonte", mesLongo(pl.s("horizonte")))
            LinhaKV("Taxa da ponte do PicPay", prm.optString("taxa_ponte_picpay"))
            TextButton(onClick = { premissas = true }) { Text("Mudar", color = cores.acento) }
            if (premissas) Premissas(prm, pl.s("horizonte")) { premissas = false }
        }
        Cartao("Eventos", Modifier.alvo("projEventos"), sub = "o que muda e quando") {
            if (evs.isEmpty()) Vazio("Nenhum evento. Um aumento, uma renda que acaba, uma viagem, o 13º...")
            evs.forEach { e ->
                Row(Modifier.fillMaxWidth().clickable { evento = e }.padding(vertical = 6.dp), verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text(e.s("nome"), color = if (e.optInt("ativo", 1) == 1) cores.texto else cores.mudo, fontSize = 14.sp, fontWeight = FontWeight.SemiBold)
                        Text("${TIPO_EV[e.s("tipo")]} · de ${mesCurto(e.s("inicio") + "-01")}" + (e.sn("fim")?.takeIf { it.isNotEmpty() }?.let { " até ${mesCurto("$it-01")}" } ?: "") +
                            if (e.optInt("ativo", 1) == 1) "" else " · desligado", color = cores.mudo, fontSize = 11.sp)
                    }
                    Text(sinal(e.d("valor")), color = if (e.d("valor") < 0) cores.ruim else cores.ok, fontWeight = FontWeight.SemiBold, fontSize = 14.sp)
                }
            }
            Spacer(Modifier.height(6.dp))
            BotaoPrimario("Novo evento") { novo = true }
        }
    }
    evento?.let { EditarEvento(it) { evento = null } }
    if (novo) EditarEvento(null) { novo = false }
}

/** Barras do resultado de cada mês (verde sobra, vermelho falta) e a linha do saldo livre acumulado. */
@Composable
private fun GraficoProjecao(linhas: List<JSONObject>) {
    if (linhas.isEmpty()) return
    val ok = cores.ok; val ruim = cores.ruim; val acento = cores.acento; val linha = cores.linha
    val vals = linhas.flatMap { listOf(it.d("resultado"), it.d("livre")) }
    val topo = max(100.0, vals.max()); val base = min(0.0, vals.min())
    Canvas(Modifier.fillMaxWidth().height(150.dp)) {
        val n = linhas.size; val gw = size.width / n; val bw = gw * .55f
        fun y(v: Double) = ((topo - v) / (topo - base) * size.height).toFloat()
        drawLine(linha, Offset(0f, y(0.0)), Offset(size.width, y(0.0)), 2f)
        linhas.forEachIndexed { i, l ->
            val y0 = y(0.0); val y1 = y(l.d("resultado"))
            drawRect(if (l.d("resultado") < 0) ruim else ok, Offset(i * gw + (gw - bw) / 2, min(y0, y1)), Size(bw, max(kotlin.math.abs(y1 - y0), 1f)))
        }
        val caminho = Path()
        linhas.forEachIndexed { i, l -> val x = i * gw + gw / 2; if (i == 0) caminho.moveTo(x, y(l.d("livre"))) else caminho.lineTo(x, y(l.d("livre"))) }
        drawPath(caminho, acento, style = Stroke(5f))
    }
    Row { linhas.forEachIndexed { i, l -> Text(if (linhas.size <= 8 || i % 2 == 0) mesCurto(l.s("mes") + "-01").take(3) else "", color = cores.mudo, fontSize = 9.sp,
        modifier = Modifier.weight(1f), textAlign = TextAlign.Center, maxLines = 1) } }
}

@Composable
private fun Premissas(prm: JSONObject, horizonte: String, aoFechar: () -> Unit) {
    val escopo = rememberCoroutineScope()
    var salario by remember { mutableStateOf(prm.optString("salario_mensal")) }
    var hz by remember { mutableStateOf(horizonte) }
    var taxa by remember { mutableStateOf(prm.optString("taxa_ponte_picpay")) }
    AlertDialog(onDismissRequest = aoFechar, containerColor = cores.painelForte, title = { Text("Premissas") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Campo(salario, { salario = it }, "Renda mensal base", numerico = true)
                Campo(hz, { hz = it }, "Horizonte (AAAA-MM)")
                Campo(taxa, { taxa = it }, "Taxa da ponte do PicPay", numerico = true)
                Text("A renda base é o padrão do salário no Orçamento.", color = cores.mudo, fontSize = 12.sp)
            }
        },
        confirmButton = { TextButton(onClick = {
            escopo.launch {
                gravar("Recalculado.") {
                    Api.put("/api/parametros/salario_mensal", jsonDe("valor" to (numero(salario)?.toString() ?: salario)))
                    Api.put("/api/parametros/horizonte", jsonDe("valor" to hz.trim()))
                    Api.put("/api/parametros/taxa_ponte_picpay", jsonDe("valor" to (numero(taxa)?.toString() ?: taxa)))
                }
                aoFechar()
            }
        }) { Text("Recalcular", color = cores.acento) } },
        dismissButton = { TextButton(onClick = aoFechar) { Text("Cancelar", color = cores.texto2) } })
}

@Composable
private fun EditarEvento(e: JSONObject?, aoFechar: () -> Unit) {
    val escopo = rememberCoroutineScope()
    var nome by remember { mutableStateOf(e?.s("nome") ?: "") }
    var tipo by remember { mutableStateOf(e?.s("tipo") ?: "renda_mensal") }
    var inicio by remember { mutableStateOf(e?.s("inicio") ?: "") }
    var fim by remember { mutableStateOf(e?.sn("fim") ?: "") }
    var valor by remember { mutableStateOf(e?.d("valor")?.let(::valorTexto) ?: "") }
    var ativo by remember { mutableStateOf(e == null || e.optInt("ativo", 1) == 1) }
    var erro by remember { mutableStateOf<String?>(null) }
    AlertDialog(onDismissRequest = aoFechar, containerColor = cores.painelForte, title = { Text(if (e == null) "Novo evento" else e.s("nome")) },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Campo(nome, { nome = it }, "Nome", dica = "Estágio, bolsa nova, viagem...")
                Seletor("Tipo", TIPO_EV.toList(), tipo) { tipo = it }
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Campo(inicio, { inicio = it }, "A partir de", Modifier.weight(1f), dica = "2027-07")
                    Campo(fim, { fim = it }, "Até (opcional)", Modifier.weight(1f))
                }
                Campo(valor, { valor = it }, "Valor (+ aumenta, - diminui)", numerico = true)
                if (e != null) Marcar("ativo", ativo) { ativo = it }
                erro?.let { Text(it, color = cores.ruim, fontSize = 13.sp) }
                if (e != null) TextButton(onClick = {
                    escopo.launch { if (gravar("Evento apagado.") { Api.delete("/api/eventos/${e.optInt("id")}") }) aoFechar() }
                }) { Text("Apagar evento", color = cores.ruim) }
            }
        },
        confirmButton = { TextButton(onClick = {
            val v = numero(valor) ?: run { erro = "Valor inválido."; return@TextButton }
            val corpo = jsonDe("nome" to nome.trim(), "tipo" to tipo, "inicio" to inicio.trim(), "fim" to fim.trim().ifEmpty { null }, "valor" to v, "ativo" to ativo)
            escopo.launch {
                try {
                    if (e == null) Api.post("/api/eventos", corpo) else Api.put("/api/eventos/${e.optInt("id")}", corpo)
                    Estado.mudou(); aoFechar()
                } catch (x: Exception) { erro = x.message }
            }
        }) { Text("Salvar", color = cores.acento) } },
        dismissButton = { TextButton(onClick = aoFechar) { Text("Cancelar", color = cores.texto2) } })
}

/** Lista que cresce sem fim (acertos, importações): só as mais recentes, e mais sob demanda. */
@Composable
private fun <T> Recentes(itens: List<T>, passo: Int = 10, linha: @Composable (T) -> Unit) {
    var n by remember(itens.size) { mutableStateOf(passo) }
    itens.take(n).forEach { linha(it) }
    if (itens.size > n) TextButton(onClick = { n += passo }) {
        Text("mostrar mais (${itens.size - n} restantes)", color = cores.acento, fontSize = 13.sp)
    }
}
