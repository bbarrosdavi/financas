package io.github.bbarrosdavi.financas.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.launch
import org.json.JSONObject
import java.time.LocalDate
import kotlin.math.max
import kotlin.math.roundToInt

@Composable
fun TelaPainel(irPara: (String) -> Unit) {
    var periodo by rememberSaveable { mutableStateOf("") }
    val c = carregar(periodo) { Api.obj("/api/painel" + if (periodo.isNotEmpty()) "?periodo=$periodo" else "") }
    val p = c.dado ?: return EstadoCarga(c)
    Column(Modifier.verticalScroll(rememberScrollState()).padding(horizontal = 10.dp, vertical = 8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Periodo(p) { periodo = it }
        Resultado(p)
        PodeGastar(p)
        Kpis(p, irPara)
        Categorias(p)
        Grafico(p)
        Composicao(p)
        Entradas(p)
        Metas(p, irPara)
        Cobrancas(p)
        Destinos(p)
        ProjecaoResumo(p, irPara)
        Spacer(Modifier.height(8.dp))
    }
}

@Composable
private fun Periodo(p: JSONObject, ir: (String) -> Unit) {
    val tipo = p.s("tipo")
    val hoje = LocalDate.parse(p.s("hoje"))
    Cartao(modifier = Modifier.alvo("periodo")) {
        Segmentos(listOf("semana" to "Semana", "mes" to "Mês", "ano" to "Ano"), tipo) { t ->
            val ref = LocalDate.parse(p.s("inicio")).let { if (!hoje.isBefore(it) && !hoje.isAfter(LocalDate.parse(p.s("fim")))) hoje else it }
            ir(periodoDo(t, ref))
        }
        Row(Modifier.padding(top = 8.dp), verticalAlignment = Alignment.CenterVertically) {
            IconButton(onClick = { ir(p.s("anterior")) }) { Icon(Icones.setaEsq, "Período anterior", tint = cores.texto) }
            Text(rotuloPeriodo(tipo, p.s("periodo"), p.s("inicio"), p.s("fim")), color = cores.texto, fontWeight = FontWeight.SemiBold,
                fontSize = 16.sp, modifier = Modifier.weight(1f), textAlign = androidx.compose.ui.text.style.TextAlign.Center)
            IconButton(onClick = { ir(p.s("proximo")) }) { Icon(Icones.seta, "Período seguinte", tint = cores.texto) }
            TextButton(onClick = { ir(periodoDo(tipo, hoje)) }) { Text("Hoje", color = cores.acento) }
        }
    }
}

@Composable
private fun Resultado(p: JSONObject) {
    val t = p.getJSONObject("totais")
    val tipo = p.s("tipo")
    val guardado = p.lista("metas").sumOf { it.d("guardado_periodo") }
    Cartao("Resultado " + when (tipo) { "semana" -> "da semana"; "ano" -> "do ano"; else -> "do mês" }, Modifier.alvo("resultado")) {
        Grande(sinal(t.d("resultado")), if (t.d("resultado") < 0) cores.ruim else cores.ok)
        Spacer(Modifier.height(6.dp))
        LinhaKV("Entradas", brl(t.d("renda")))
        LinhaKV("Gastos", brl(t.d("gasto")))
        LinhaKV("Juros e taxas", brl(t.d("juros")), if (t.d("juros") > 0) cores.ruim else cores.texto)
        if (guardado != 0.0) LinhaKV("Guardado em metas", brl(guardado), cores.ok)
    }
}

@Composable
private fun PodeGastar(p: JSONObject) {
    val teto = p.d("teto_variavel"); val gasto = p.d("gasto_variavel"); val ritmo = p.d("ritmo"); val pode = p.d("pode_gastar")
    val uso = if (teto > 0) gasto / teto else 0.0
    val cor = when { pode < 0 || uso > 1 -> cores.ruim; uso > ritmo + .1 -> cores.atencao; else -> cores.ok }
    Cartao("Ainda pode gastar", Modifier.alvo("podeGastar"), sub = "categorias variáveis") {
        Grande(brl(pode), if (pode < 0) cores.ruim else if (uso > ritmo + .1) cores.atencao else cores.ok)
        Spacer(Modifier.height(8.dp))
        Barra(uso, cor, ritmo, 10.dp)
        Spacer(Modifier.height(6.dp))
        LinhaKV("Gasto", "${brl(gasto)} de ${brl(teto)}")
        if (ritmo > 0 && ritmo < 1) LinhaKV("No ritmo certo, até hoje", brl(teto * ritmo))
        if (teto == 0.0) Vazio("Sem teto nas categorias variáveis: defina em Orçamento > Categorias.")
    }
}

@Composable
private fun Kpis(p: JSONObject, irPara: (String) -> Unit) {
    val conta = p.lista("contas").firstOrNull { it.s("id") == "nubank_conta" }
    val cartao = p.getJSONObject("cartao")
    val pessoas = p.lista("pessoas")
    val devo = pessoas.filter { it.d("saldo") < 0 }.sumOf { -it.d("saldo") }
    val devem = pessoas.filter { it.d("saldo") > 0 }.sumOf { it.d("saldo") }
    var informar by remember { mutableStateOf(false) }
    Cartao(modifier = Modifier.alvo("kpis")) {
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Kpi("Conta", Modifier.weight(1f).clickable { informar = true }) {
                if (conta == null) Vazio("-")
                else if (conta.dn("saldo_real") == null) {
                    Text(brl(conta.d("saldo")), color = cores.atencao, fontWeight = FontWeight.Bold, fontSize = 17.sp)
                    Text((if (conta.s("cobertura").isEmpty()) "sem extrato ainda" else "pelo extrato até ${dataBR(conta.s("cobertura"))}") +
                        " · toque para informar o saldo do app", color = cores.mudo, fontSize = 11.sp)
                } else {
                    val dif = conta.d("diferenca")
                    // O saldo de hoje: o que o app do banco mostrou naquele dia mais o que foi lançado depois.
                    Text(brl(conta.d("saldo_atual")), color = cores.texto, fontWeight = FontWeight.Bold, fontSize = 17.sp)
                    Text("saldo do app em ${dataBR(conta.s("data_real"))} (${brl(conta.d("saldo_real"))})" +
                        (if (conta.s("data_real") < hojeISO()) " + lançamentos depois" else "") + " · " +
                        if (kotlin.math.abs(dif) < .005) "bate com os lançamentos" else "${brl(dif)} não lançados",
                        color = if (kotlin.math.abs(dif) < .005) cores.mudo else cores.atencao, fontSize = 11.sp)
                }
            }
            Kpi("Dívida do cartão", Modifier.weight(1f)) {
                Text(brl(cartao.d("divida")), color = cores.ruim, fontWeight = FontWeight.Bold, fontSize = 17.sp)
                Text("limite livre ${brl(cartao.d("limite_livre"))} de ${brl(cartao.d("limite"))}",
                    color = if (cartao.d("limite") > 0 && cartao.d("limite_livre") < 300) cores.ruim else cores.mudo, fontSize = 11.sp)
            }
        }
        Spacer(Modifier.height(12.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Kpi("Você deve / te devem", Modifier.weight(1f).clickable { irPara("pessoas") }) {
                Text("${brl(devo)} / ${brl(devem)}", color = cores.texto, fontWeight = FontWeight.Bold, fontSize = 17.sp)
                Text("ver pessoas", color = cores.acento, fontSize = 11.sp)
            }
            Kpi("Pendentes", Modifier.weight(1f).clickable { irPara("pendentes") }) {
                val n = p.optInt("pendentes")
                Text("$n", color = if (n > 0) cores.atencao else cores.ok, fontWeight = FontWeight.Bold, fontSize = 17.sp)
                Text(if (n > 0) "classificar agora" else "tudo classificado", color = if (n > 0) cores.acento else cores.mudo, fontSize = 11.sp)
            }
        }
    }
    if (informar) InformarSaldo { informar = false }
}

@Composable
private fun Kpi(rotulo: String, modifier: Modifier, conteudo: @Composable () -> Unit) {
    Column(modifier) { Rotulo(rotulo); conteudo() }
}

@Composable
fun InformarSaldo(aoFechar: () -> Unit) {
    var texto by remember { mutableStateOf("") }
    val escopo = rememberCoroutineScope()
    AlertDialog(onDismissRequest = aoFechar, containerColor = cores.painelForte, title = { Text("Saldo do app do banco") },
        text = { Column { Text("O saldo que o app do Nubank mostra agora.", color = cores.texto2); Campo(texto, { texto = it }, "Saldo", numerico = true, dica = "162,18") } },
        confirmButton = { TextButton(onClick = {
            val v = numero(texto) ?: return@TextButton
            escopo.launch { gravar("Saldo informado.") { Api.put("/api/contas/nubank_conta/saldo", jsonDe("valor" to v, "data" to hojeISO())) }; aoFechar() }
        }) { Text("Salvar", color = cores.acento) } },
        dismissButton = { TextButton(onClick = aoFechar) { Text("Cancelar", color = cores.texto2) } })
}

@Composable
private fun Categorias(p: JSONObject) {
    val ritmo = p.d("ritmo")
    val cats = p.lista("categorias").filter { it.d("gasto") != 0.0 || it.d("parcelas") != 0.0 }
    val grupos = cats.groupBy { it.s("grupo") }.map { (g, cs) ->
        val comTeto = cs.any { it.dn("teto") != null }
        Triple(g, cs.sortedWith(compareByDescending<JSONObject> { it.d("acima") }.thenByDescending { it.d("gasto") }),
            doubleArrayOf(cs.sumOf { it.d("gasto") }, if (comTeto) cs.sumOf { it.d("teto") } else -1.0, cs.sumOf { it.d("parcelas") }, cs.sumOf { it.d("acima") }))
    }.sortedWith(compareByDescending<Triple<String, List<JSONObject>, DoubleArray>> { it.third[3] }.thenByDescending { it.third[0] })
    var evolucao by remember { mutableStateOf<Pair<String, String>?>(null) }
    val acimaTot = cats.sumOf { it.d("acima") }
    Cartao("Categorias", Modifier.alvo("categorias"), sub = when (p.s("tipo")) { "ano" -> "teto acumulado no ano"; "semana" -> "teto do mês ÷ 4"; else -> "teto do mês" }) {
        if (acimaTot > 0) Text("${brl(acimaTot)} acima do teto em ${cats.count { it.d("acima") > 0 }} categoria(s)", color = cores.ruim,
            fontWeight = FontWeight.SemiBold, fontSize = 13.sp, modifier = Modifier.padding(bottom = 6.dp))
        if (grupos.isEmpty()) Vazio("Nenhum gasto no período.")
        grupos.forEach { (g, cs, tot) ->
            var aberto by rememberSaveable(g) { mutableStateOf(tot[3] > 0) }
            val teto = tot[1].takeIf { it >= 0 }
            LinhaGasto(nome = g, cor = corGrupo(g), gasto = tot[0], teto = teto, acima = if (teto != null) max(0.0, tot[0] - teto) else 0.0,
                parcelas = tot[2], ritmo = null, negrito = true, aoTocar = { aberto = !aberto }, sufixo = if (aberto) "▴" else "▾")
            if (aberto) cs.forEach { cat ->
                LinhaGasto(nome = cat.s("nome"), cor = corCategoria(cat.s("id")), gasto = cat.d("gasto"), teto = cat.dn("teto"), acima = cat.d("acima"),
                    parcelas = cat.d("parcelas"), ritmo = if (cat.optInt("fixa") == 0) ritmo else null, recuo = true,
                    aoTocar = { evolucao = "categoria=${Api.q(cat.s("id"))}" to cat.s("nome") })
            }
            Divisor()
        }
    }
    evolucao?.let { (q, nome) -> Evolucao(q, nome, p.s("tipo")) { evolucao = null } }
}

@Composable
private fun LinhaGasto(nome: String, cor: Color, gasto: Double, teto: Double?, acima: Double, parcelas: Double, ritmo: Double?,
                       negrito: Boolean = false, recuo: Boolean = false, sufixo: String = "", aoTocar: () -> Unit) {
    val pct = if (teto != null && teto > 0) gasto / teto else if (gasto > 0) 2.0 else 0.0
    val corBarra = when { teto == null -> cores.mudo; acima > 0 -> cores.ruim; ritmo != null && pct > ritmo + .1 -> cores.atencao; else -> cores.ok }
    Column(Modifier.fillMaxWidth().clickable(onClick = aoTocar).padding(start = if (recuo) 18.dp else 0.dp, top = 8.dp, bottom = 8.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Bolinha(cor)
            Text("  $nome $sufixo", color = cores.texto, fontSize = 14.sp, fontWeight = if (negrito) FontWeight.SemiBold else FontWeight.Normal,
                modifier = Modifier.weight(1f), maxLines = 1, overflow = TextOverflow.Ellipsis)
            Text(brl(gasto), color = cores.texto, fontWeight = FontWeight.SemiBold, fontSize = 14.sp)
        }
        Spacer(Modifier.height(5.dp))
        Barra(pct, corBarra, ritmo, 6.dp)
        Row(Modifier.padding(top = 3.dp)) {
            Text(if (teto != null) "de ${brl(teto)} · ${if (teto > 0) (gasto / teto * 100).roundToInt() else 0}%" else "sem teto", color = cores.mudo,
                fontSize = 11.sp, modifier = Modifier.weight(1f))
            if (teto != null) Text(if (acima > 0) "+${brl(acima)} acima" else "resta ${brl(max(teto - gasto, 0.0))}",
                color = if (acima > 0) cores.ruim else cores.ok, fontSize = 11.sp, fontWeight = FontWeight.SemiBold)
        }
        if (parcelas != 0.0) Text("+ ${brl(parcelas)} de parcelas antigas", color = cores.mudo, fontSize = 11.sp)
    }
}

@Composable
private fun Evolucao(q: String, nome: String, tipo: String, aoFechar: () -> Unit) {
    val c = carregar(q, tipo) { Api.lista("/api/evolucao?tipo=$tipo&$q").objs() }
    AlertDialog(onDismissRequest = aoFechar, containerColor = cores.painelForte, title = { Text("Evolução: $nome") },
        confirmButton = { TextButton(onClick = aoFechar) { Text("Fechar", color = cores.acento) } },
        text = {
            val s = c.dado
            if (s == null) Text("Carregando...", color = cores.mudo) else {
                val media = s.sumOf { it.d("gasto") + it.d("parcelas") } / max(1, s.size)
                Column {
                    Text("Média ${brl(media)} · acima do teto em ${s.count { it.dn("teto") != null && it.d("gasto") > it.d("teto") }} de ${s.size}", color = cores.mudo, fontSize = 12.sp)
                    Barras(s.map { (it.d("gasto") + it.d("parcelas")) to it.dn("teto") }, s.map { x ->
                        if (tipo == "semana") dataCurta(x.s("inicio")) else mesCurto(x.s("periodo") + "-01").take(3) })
                }
            }
        })
}

/** Barras simples (gasto contra teto), para a evolução de uma categoria. */
@Composable
private fun Barras(valores: List<Pair<Double, Double?>>, rotulos: List<String>) {
    val ruim = cores.ruim; val normal = cores.s2; val teto = cores.texto.copy(alpha = .55f); val linha = cores.linha
    val maximo = max(50.0, valores.maxOfOrNull { max(it.first, it.second ?: 0.0) } ?: 0.0) * 1.1     // folga para o teto não encostar na borda
    Column(Modifier.padding(top = 8.dp)) {
        Canvas(Modifier.fillMaxWidth().height(160.dp)) {
            val n = valores.size.coerceAtLeast(1); val gw = size.width / n; val bw = gw * .6f
            drawLine(linha, Offset(0f, size.height), Offset(size.width, size.height))
            valores.forEachIndexed { i, (v, t) ->
                val hgt = (v / maximo * size.height).toFloat()
                drawRoundRect(if (t != null && v > t) ruim else normal, Offset(i * gw + (gw - bw) / 2, size.height - hgt), Size(bw, hgt), CornerRadius(4f))
                if (t != null) { val y = (size.height - t / maximo * size.height).toFloat()
                    drawLine(teto, Offset(i * gw, y), Offset((i + 1) * gw, y), 3f, pathEffect = PathEffect.dashPathEffect(floatArrayOf(10f, 8f))) }
            }
        }
        Row { rotulos.forEach { Text(it, color = cores.mudo, fontSize = 9.sp, modifier = Modifier.weight(1f), textAlign = androidx.compose.ui.text.style.TextAlign.Center, maxLines = 1) } }
    }
}

@Composable
private fun Grafico(p: JSONObject) {
    val serie = p.lista("serie")
    val tipo = p.s("tipo")
    var sel by remember(p) { mutableStateOf(serie.lastIndex) }
    val s1 = cores.s1; val s2 = cores.s2; val s3 = cores.s3; val linha = cores.linha
    Cartao("Entradas e gastos", Modifier.alvo("grafico"), sub = when (tipo) { "semana" -> "últimas 12 semanas"; "ano" -> "jan a dez"; else -> "últimos 12 meses" }) {
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            listOf("Entradas" to s1, "Gastos" to s2, "Poupança" to s3).forEach { (n, c) ->
                Row(verticalAlignment = Alignment.CenterVertically) { Bolinha(c); Text(" $n", color = cores.texto2, fontSize = 12.sp) }
            }
        }
        if (serie.all { m -> listOf("renda", "gasto", "poupanca", "orc_renda", "orc_gasto", "orc_poupanca").all { m.d(it) == 0.0 } })
            return@Cartao Vazio("Nada lançado nem orçado ainda.")
        val maximo = max(100.0, serie.maxOfOrNull { listOf(it.d("renda"), it.d("gasto"), it.d("poupanca"), it.d("orc_renda"), it.d("orc_gasto")).max() } ?: 0.0)
        Canvas(Modifier.fillMaxWidth().height(170.dp).padding(top = 8.dp).pointerInput(serie) {
            detectTapGestures { o -> if (serie.isNotEmpty()) sel = (o.x / (size.width / serie.size)).toInt().coerceIn(0, serie.lastIndex) }
        }) {
            val n = serie.size.coerceAtLeast(1); val gw = size.width / n; val bw = gw * .26f
            drawLine(linha, Offset(0f, size.height), Offset(size.width, size.height))
            serie.forEachIndexed { i, m ->
                listOf(Triple("renda", "orc_renda", s1), Triple("gasto", "orc_gasto", s2), Triple("poupanca", "orc_poupanca", s3)).forEachIndexed { j, (k, ko, cor) ->
                    val x = i * gw + gw * .11f + j * bw
                    val ho = (m.d(ko) / maximo * size.height).toFloat()
                    if (ho > 0) drawRoundRect(cor.copy(alpha = .28f), Offset(x, size.height - ho), Size(bw * .9f, ho), CornerRadius(3f))
                    val hv = (max(0.0, m.d(k)) / maximo * size.height).toFloat()
                    drawRoundRect(cor, Offset(x, size.height - hv), Size(bw * .9f, hv), CornerRadius(3f))
                }
                if (i == sel) drawRect(Color.Gray.copy(alpha = .12f), Offset(i * gw, 0f), Size(gw, size.height))
            }
        }
        Row { serie.forEach { m -> Text(if (tipo == "semana") dataCurta(m.s("inicio")).take(5) else mesCurto(m.s("mes") + "-01").take(3),
            color = cores.mudo, fontSize = 9.sp, modifier = Modifier.weight(1f), textAlign = androidx.compose.ui.text.style.TextAlign.Center, maxLines = 1) } }
        serie.getOrNull(sel)?.let { m ->
            Spacer(Modifier.height(6.dp))
            Text(if (tipo == "semana") "Semana de ${dataBR(m.s("inicio"))}" else mesLongo(m.s("mes")), color = cores.texto, fontWeight = FontWeight.SemiBold, fontSize = 13.sp)
            LinhaKV("Entradas", "${brl(m.d("renda"))} de ${brl(m.d("orc_renda"))}", negrito = false)
            LinhaKV("Gastos", "${brl(m.d("gasto"))} de ${brl(m.d("orc_gasto"))}", negrito = false)
            LinhaKV("Poupança", "${brl(m.d("poupanca"))} de ${brl(m.d("orc_poupanca"))}", negrito = false)
            LinhaKV("Resultado", brl(m.d("resultado")), if (m.d("resultado") < 0) cores.ruim else cores.ok)
        }
    }
}

@Composable
private fun Composicao(p: JSONObject) {
    val g = p.optJSONObject("grupos") ?: JSONObject()
    val grupos = g.keys().asSequence().map { it to g.getDouble(it) }.sortedByDescending { it.second }.toList()
    val total = grupos.sumOf { it.second }.takeIf { it > 0 } ?: 1.0
    Cartao("Para onde foi", Modifier.alvo("composicao"), sub = "gasto por grupo") {
        if (grupos.isEmpty()) return@Cartao Vazio("Nenhum gasto no período.")
        Row(Modifier.fillMaxWidth().height(12.dp).clip(RoundedCornerShape(6.dp))) {
            grupos.forEach { (n, v) -> Box(Modifier.weight((v / total).toFloat().coerceAtLeast(0.001f)).fillMaxHeight().background(corGrupo(n))) }
        }
        Spacer(Modifier.height(8.dp))
        grupos.forEach { (n, v) ->
            Row(Modifier.padding(vertical = 3.dp), verticalAlignment = Alignment.CenterVertically) {
                Bolinha(corGrupo(n)); Text("  $n", color = cores.texto, fontSize = 14.sp, modifier = Modifier.weight(1f))
                Text(brl(v), color = cores.texto, fontSize = 14.sp, fontWeight = FontWeight.SemiBold)
                Text("  ${(v / total * 100).roundToInt()}%", color = cores.mudo, fontSize = 12.sp, modifier = Modifier.width(44.dp))
            }
        }
    }
}

@Composable
private fun Entradas(p: JSONObject) {
    val ents = p.lista("entradas").filter { it.d("valor") != 0.0 }
    Cartao("Entradas do período", Modifier.alvo("entradas")) {
        if (ents.isEmpty()) Vazio("Nenhuma entrada no período.")
        ents.forEach { e -> LinhaKV("${e.s("nome")} (${e.optInt("n")})", brl(e.d("valor")), negrito = false) }
        if (ents.isNotEmpty()) { Divisor(); LinhaKV("Total", brl(p.getJSONObject("totais").d("renda"))) }
    }
}

@Composable
private fun Metas(p: JSONObject, irPara: (String) -> Unit) {
    val ms = p.lista("metas").filter { it.optInt("ativa", 1) == 1 }
    Cartao("Poupança e metas", Modifier.alvo("metas")) {
        if (ms.isEmpty()) Text("Nenhuma meta ainda. Crie em Orçamento > Metas.", color = cores.acento, fontSize = 13.sp, modifier = Modifier.clickable { irPara("orcamento") })
        ms.forEach { m ->
            Column(Modifier.padding(vertical = 6.dp)) {
                Row { Text(m.s("nome"), color = cores.texto, fontWeight = FontWeight.SemiBold, fontSize = 14.sp, modifier = Modifier.weight(1f))
                    Text(if (m.d("falta_periodo") > 0) "falta ${brl(m.d("falta_periodo"))}" else "cumprido",
                        color = if (m.d("falta_periodo") > 0) cores.atencao else cores.ok, fontSize = 13.sp, fontWeight = FontWeight.SemiBold) }
                Text("Planejado ${brl(m.d("planejado_periodo"))} · guardado ${brl(m.d("guardado_periodo"))}" +
                    (m.dn("por_mes_ate_prazo")?.let { " · ${brl(it)}/mês para chegar" } ?: ""), color = cores.mudo, fontSize = 12.sp)
                m.dn("alvo")?.let { alvo ->
                    Spacer(Modifier.height(4.dp))
                    Barra(m.d("completude_alvo"), cores.acento, null, 6.dp)
                    Text("${brl(m.d("guardado_total"))} de ${brl(alvo)} (${(m.d("completude_alvo") * 100).roundToInt()}%)", color = cores.texto2, fontSize = 12.sp)
                } ?: Text("Acumulado ${brl(m.d("guardado_total"))}", color = cores.texto2, fontSize = 12.sp)
            }
        }
    }
}

@Composable
private fun Cobrancas(p: JSONObject) {
    val porMes = p.lista("compromissos").groupBy { it.s("mes") }.toList().take(6)
    Cartao("Próximas cobranças no cartão", Modifier.alvo("cobrancas")) {
        if (porMes.isEmpty()) Vazio("Nenhuma parcela futura.")
        porMes.forEach { (mes, cs) ->
            Row(Modifier.padding(top = 6.dp)) { Text(mesCurto("$mes-01"), color = cores.texto, fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f))
                Text(brl(cs.sumOf { it.d("valor") }), color = cores.texto, fontWeight = FontWeight.Bold) }
            cs.forEach { c -> LinhaKV(c.s("descricao").replace(Regex(" - Parcela.*| - \\d+/\\d+$"), "") + " " + c.s("parcela"), brl(c.d("valor")), negrito = false) }
        }
    }
}

@Composable
private fun Destinos(p: JSONObject) {
    val top = p.lista("top")
    Cartao("Maiores destinos", Modifier.alvo("destinos")) {
        if (top.isEmpty()) Vazio("Nenhum gasto no período.")
        top.forEach { t -> LinhaKV("${t.s("nome")} (${t.optInt("n")}x)", brl(t.d("total")), negrito = false) }
    }
}

@Composable
private fun ProjecaoResumo(p: JSONObject, irPara: (String) -> Unit) {
    val plano = p.getJSONObject("plano")
    val linhas = plano.lista("linhas").take(4)
    Cartao("Projeção até ${mesCurto(plano.s("horizonte") + "-01")}", Modifier.alvo("projecaoPainel")) {
        if (linhas.isEmpty()) Vazio("Defina o horizonte em Projeção, no alto.")
        linhas.forEach { l ->
            Column(Modifier.padding(vertical = 5.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(mesCurto(l.s("mes") + "-01"), color = cores.texto, fontWeight = FontWeight.SemiBold, modifier = Modifier.width(64.dp))
                    Text(sinal(l.d("resultado")), color = if (l.d("resultado") < 0) cores.ruim else cores.ok, fontWeight = FontWeight.Bold, fontSize = 14.sp,
                        modifier = Modifier.weight(1f))
                    if (l.d("falta") > 0) Text("falta ${brl(l.d("falta"))}  ", color = cores.atencao, fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
                    Text("livre ${brl(l.d("livre"))}", color = cores.texto2, fontSize = 12.sp)
                }
                Text("renda ${brl(l.d("renda") + l.d("reembolsos") + l.d("unicos"))} · custo ${brl(l.d("custo") + l.d("aportes"))} · cartão ${brl(l.d("cartao"))}",
                    color = cores.mudo, fontSize = 11.sp, modifier = Modifier.padding(start = 64.dp))
            }
        }
        Text("ver completa e editar", color = cores.acento, fontSize = 13.sp, modifier = Modifier.padding(top = 6.dp).clickable { irPara("projecao") })
    }
}
