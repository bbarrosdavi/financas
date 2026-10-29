package io.github.bbarrosdavi.financas.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
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
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.launch
import org.json.JSONObject
import java.time.LocalDate

private val ABAS_ORC = listOf("mes" to "Mês", "ano" to "Ano", "fixas" to "Fixas", "categorias" to "Categorias", "metas" to "Metas")

/** Uma linha da grade do orçamento (categoria ou meta), com orçado e realizado de cada mês. */
private class LinhaOrc(val j: JSONObject) {
    val chave = j.s("chave"); val tipo = j.s("tipo"); val grupo = j.s("grupo"); val nome = j.s("nome")
    fun orcado(m: String): Double? = j.optJSONObject("orcado")?.let { if (it.isNull(m)) null else it.optDouble(m) }
    fun realizado(m: String): Double = j.optJSONObject("realizado")?.optDouble(m, 0.0) ?: 0.0
    fun definido(m: String) = j.optJSONArray("definido")?.let { a -> (0 until a.length()).any { a.getString(it) == m } } ?: false
    val porItens = j.optBoolean("por_itens")
    val fixa = j.optInt("fixa") == 1
    val itens = j.lista("itens")
    fun somaItens(m: String) = j.optJSONObject("soma_itens")?.optDouble(m, 0.0) ?: 0.0
    val cor: Color @Composable get() = if (tipo == "poupanca") cores.s3 else corCategoria(chave)
}

@Composable
fun TelaOrcamento() {
    var aba by rememberSaveable { mutableStateOf("mes") }
    var ano by rememberSaveable { mutableStateOf(LocalDate.now().year) }
    var mes by rememberSaveable { mutableStateOf(LocalDate.now().toString().take(7)) }
    val c = carregar(ano) { Api.obj("/api/orcamento?ano=$ano") to Api.lista("/api/metas").objs() }
    Column(Modifier.verticalScroll(rememberScrollState()).padding(horizontal = 10.dp, vertical = 8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Cartao(modifier = Modifier.alvo("orcAbas")) {
            Segmentos(ABAS_ORC, aba) { aba = it }
            if (aba == "mes" || aba == "ano" || aba == "fixas") Row(Modifier.padding(top = 6.dp), verticalAlignment = Alignment.CenterVertically) {
                IconButton(onClick = { if (aba == "ano") { ano--; mes = "$ano-${mes.substring(5)}" } else mes = LocalDate.parse("$mes-01").minusMonths(1).toString().take(7).also { ano = it.take(4).toInt() } }) {
                    Icon(Icones.setaEsq, "Período anterior", tint = cores.texto) }
                Text(if (aba == "ano") "$ano" else mesLongo(mes), color = cores.texto, fontWeight = FontWeight.SemiBold, fontSize = 16.sp,
                    modifier = Modifier.weight(1f), textAlign = TextAlign.Center)
                IconButton(onClick = { if (aba == "ano") { ano++; mes = "$ano-${mes.substring(5)}" } else mes = LocalDate.parse("$mes-01").plusMonths(1).toString().take(7).also { ano = it.take(4).toInt() } }) {
                    Icon(Icones.seta, "Período seguinte", tint = cores.texto) }
            }
        }
        val (g, metas) = c.dado ?: return@Column EstadoCarga(c)
        val linhas = g.lista("linhas").map(::LinhaOrc)
        val parcelas = g.optJSONObject("parcelas") ?: JSONObject()
        val meses = g.optJSONArray("meses")?.let { a -> (0 until a.length()).map { a.getString(it) } } ?: emptyList()
        when (aba) {
            "mes" -> if (mes in meses) AbaMes(linhas, mes, parcelas.optDouble(mes, 0.0)) else EstadoCarga(Carga<Unit>())
            "ano" -> AbaAno(linhas, meses, parcelas)
            "fixas" -> AbaFixas(linhas.filter { it.tipo == "gasto" }, mes)
            "categorias" -> AbaCategorias()
            "metas" -> AbaMetas(metas)
        }
    }
}

/** Positivo é sempre a favor: gastou menos que o orçado, recebeu ou guardou mais. */
private fun diferenca(l: LinhaOrc, orc: Double, real: Double) = if (l.tipo == "gasto") orc - real else real - orc

@Composable
private fun AbaMes(linhas: List<LinhaOrc>, mes: String, parcelas: Double) {
    val atual = LocalDate.now().toString().take(7)
    val futuro = mes > atual
    val renda = linhas.filter { it.tipo == "renda" }
    val gasto = linhas.filter { it.tipo == "gasto" }
    val poup = linhas.filter { it.tipo == "poupanca" && (it.j.optInt("ativa") == 1 || it.orcado(mes) != null || it.realizado(mes) != 0.0) }
    fun soma(ls: List<LinhaOrc>, f: (LinhaOrc) -> Double) = ls.sumOf(f)
    val alocarOrc = soma(renda) { it.orcado(mes) ?: 0.0 } - soma(gasto) { it.orcado(mes) ?: 0.0 } - soma(poup) { it.orcado(mes) ?: 0.0 }
    val alocarReal = soma(renda) { it.realizado(mes) } - soma(gasto) { it.realizado(mes) } - soma(poup) { it.realizado(mes) } - parcelas
    var editando by remember { mutableStateOf<LinhaOrc?>(null) }

    Cartao("A alocar", sub = "entradas menos gastos e poupança") {
        LinhaKV("Orçado", sinal(alocarOrc), if (alocarOrc < -.5) cores.ruim else cores.ok)
        if (!futuro) LinhaKV("Realizado", sinal(alocarReal), if (alocarReal < -.5) cores.ruim else cores.ok)
        Text("Toque numa linha para mudar o orçado do mês. Cinza é o padrão (teto da categoria, soma das fixas ou aporte da meta).",
            color = cores.mudo, fontSize = 12.sp, modifier = Modifier.padding(top = 4.dp))
    }
    @Composable
    fun secao(titulo: String, ls: List<LinhaOrc>, porGrupo: Boolean, extra: Double = 0.0) {
        Cartao(titulo) {
            Cabecalho(futuro)
            if (porGrupo) ls.groupBy { it.grupo }.forEach { (gr, gls) ->
                LinhaValores(gr, corGrupo(gr), gls.sumOf { it.orcado(mes) ?: 0.0 }, if (futuro) null else gls.sumOf { it.realizado(mes) }, "gasto", negrito = true)
                gls.forEach { l -> LinhaValores(l.nome, l.cor, l.orcado(mes), if (futuro) null else l.realizado(mes), l.tipo, recuo = true,
                    padrao = !l.definido(mes)) { editando = l } }
            } else ls.forEach { l -> LinhaValores(l.nome, l.cor, l.orcado(mes), if (futuro) null else l.realizado(mes), l.tipo,
                padrao = !l.definido(mes)) { editando = l } }
            if (ls.isEmpty()) Vazio(if (titulo == "Poupança") "Nenhuma meta ativa." else "Nada aqui.")
            if (extra != 0.0 && !futuro) LinhaValores("Parcelas de compras antigas", cores.mudo, null, extra, "gasto")
            Divisor()
            LinhaValores("Total", cores.texto, ls.sumOf { it.orcado(mes) ?: 0.0 }, if (futuro) null else ls.sumOf { it.realizado(mes) } + extra,
                ls.firstOrNull()?.tipo ?: "gasto", negrito = true)
        }
    }
    secao("Entradas", renda, false)
    secao("Gastos", gasto, true, parcelas)
    secao("Poupança", poup, false)
    editando?.let { l -> EditarOrcado(l, mes) { editando = null } }
}

@Composable
private fun Cabecalho(semRealizado: Boolean) {
    Row(Modifier.fillMaxWidth().padding(bottom = 4.dp)) {
        Spacer(Modifier.weight(1f))
        listOf("Orçado", "Real", "Dif.").forEachIndexed { i, t ->
            if (i == 0 || !semRealizado) Text(t, color = cores.mudo, fontSize = 11.sp, modifier = Modifier.width(68.dp), textAlign = TextAlign.End)
        }
    }
}

@Composable
private fun LinhaValores(nome: String, cor: Color, orcado: Double?, realizado: Double?, tipo: String, negrito: Boolean = false, recuo: Boolean = false,
                         padrao: Boolean = false, aoTocar: (() -> Unit)? = null) {
    val dif = if (realizado != null) (if (tipo == "gasto") (orcado ?: 0.0) - realizado else realizado - (orcado ?: 0.0)) else null
    Row(Modifier.fillMaxWidth().then(if (aoTocar != null) Modifier.clickable(onClick = aoTocar) else Modifier)
        .padding(start = if (recuo) 14.dp else 0.dp, top = 7.dp, bottom = 7.dp), verticalAlignment = Alignment.CenterVertically) {
        Bolinha(cor)
        Text("  $nome", color = cores.texto, fontSize = 14.sp, fontWeight = if (negrito) FontWeight.SemiBold else FontWeight.Normal,
            modifier = Modifier.weight(1f), maxLines = 1, overflow = TextOverflow.Ellipsis)
        Text(orcado?.let { brl(it).removePrefix("R$ ") } ?: "–", color = if (padrao) cores.mudo else cores.texto, fontSize = 13.sp,
            fontWeight = if (negrito || !padrao) FontWeight.SemiBold else FontWeight.Normal, modifier = Modifier.width(68.dp), textAlign = TextAlign.End)
        if (realizado != null) {
            Text(brl(realizado).removePrefix("R$ "), color = cores.texto, fontSize = 13.sp, modifier = Modifier.width(68.dp), textAlign = TextAlign.End)
            Text((if (dif!! > .5) "+" else "") + brl(dif).replace("R$ ", ""), fontSize = 13.sp, fontWeight = FontWeight.SemiBold,
                color = if (dif < -.5) cores.ruim else if (dif > .5) cores.ok else cores.mudo, modifier = Modifier.width(68.dp), textAlign = TextAlign.End)
        }
    }
}

@Composable
private fun EditarOrcado(l: LinhaOrc, mes: String, aoFechar: () -> Unit) {
    val escopo = rememberCoroutineScope()
    var texto by remember { mutableStateOf(l.orcado(mes)?.takeIf { l.definido(mes) }?.let(::valorTexto) ?: "") }
    var repetir by rememberSaveable { mutableStateOf(false) }
    val padrao = when { l.tipo == "poupanca" -> "aporte mensal da meta"; l.tipo == "renda" -> if (l.chave == "salario") "renda base" else "sem padrão"
        l.porItens -> "soma das despesas fixas"; else -> "teto da categoria" }
    // Fecha só depois de gravar: fechar o diálogo cancela o escopo dele.
    fun salvar(v: Double?) {
        escopo.launch { gravar { Api.put("/api/orcamento", jsonDe("chave" to l.chave, "mes" to mes, "valor" to v, "ate_dezembro" to repetir)) }; aoFechar() }
    }
    AlertDialog(onDismissRequest = aoFechar, containerColor = cores.painelForte, title = { Text("${l.nome}: ${mesLongo(mes)}") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text("Vazio volta ao padrão ($padrao${l.orcado(mes)?.takeIf { !l.definido(mes) }?.let { ": " + brl(it) } ?: ""}).", color = cores.texto2, fontSize = 13.sp)
                Campo(texto, { texto = it }, "Orçado", numerico = true)
                Marcar("repetir até dezembro", repetir) { repetir = it }
            }
        },
        confirmButton = { TextButton(onClick = {
            if (texto.isBlank()) salvar(null) else numero(texto)?.let(::salvar)
        }) { Text("Salvar", color = cores.acento) } },
        dismissButton = { TextButton(onClick = aoFechar) { Text("Cancelar", color = cores.texto2) } })
}

@Composable
private fun AbaAno(linhas: List<LinhaOrc>, meses: List<String>, parcelas: JSONObject) {
    val atual = LocalDate.now().toString().take(7)
    val passados = meses.filter { it <= atual }
    fun orc(l: LinhaOrc) = meses.sumOf { l.orcado(it) ?: 0.0 }
    fun orcAteHoje(l: LinhaOrc) = passados.sumOf { l.orcado(it) ?: 0.0 }
    fun real(l: LinhaOrc) = passados.sumOf { l.realizado(it) }
    val parc = passados.sumOf { parcelas.optDouble(it, 0.0) }
    val renda = linhas.filter { it.tipo == "renda" }; val gasto = linhas.filter { it.tipo == "gasto" }
    val poup = linhas.filter { it.tipo == "poupanca" && (it.j.optInt("ativa") == 1 || orc(it) != 0.0 || real(it) != 0.0) }
    Cartao("O ano", sub = if (passados.size in 1 until meses.size) "realizado até ${mesCurto(passados.last() + "-01")}" else null) {
        LinhaKV("Entradas orçadas", brl(renda.sumOf(::orc)))
        LinhaKV("Gastos orçados", brl(gasto.sumOf(::orc)))
        LinhaKV("Poupança orçada", brl(poup.sumOf(::orc)))
        val alocar = renda.sumOf(::orc) - gasto.sumOf(::orc) - poup.sumOf(::orc)
        LinhaKV("A alocar no ano", sinal(alocar), if (alocar < -.5) cores.ruim else cores.ok)
        Text("Real e diferença comparam só os meses que já passaram com o orçado deles.", color = cores.mudo, fontSize = 12.sp, modifier = Modifier.padding(top = 4.dp))
    }
    listOf("Entradas" to renda, "Gastos" to gasto, "Poupança" to poup).forEach { (titulo, ls) ->
        Cartao(titulo) {
            Cabecalho(false)
            if (titulo == "Gastos") ls.groupBy { it.grupo }.forEach { (gr, gls) ->
                LinhaValores(gr, corGrupo(gr), gls.sumOf(::orcAteHoje), gls.sumOf(::real), "gasto", negrito = true)
                gls.forEach { l -> LinhaValores(l.nome, l.cor, orcAteHoje(l), real(l), l.tipo, recuo = true) }
            } else ls.forEach { l -> LinhaValores(l.nome, l.cor, orcAteHoje(l), real(l), l.tipo) }
            if (titulo == "Gastos" && parc != 0.0) LinhaValores("Parcelas de compras antigas", cores.mudo, null, parc, "gasto")
            Divisor()
            LinhaValores("Total", cores.texto, ls.sumOf(::orcAteHoje), ls.sumOf(::real) + if (titulo == "Gastos") parc else 0.0, ls.firstOrNull()?.tipo ?: "gasto", negrito = true)
        }
    }
}

@Composable
private fun AbaFixas(gasto: List<LinhaOrc>, mes: String) {
    val escopo = rememberCoroutineScope()
    var item by remember { mutableStateOf<JSONObject?>(null) }
    var novo by remember { mutableStateOf(false) }
    // As categorias fixas (aluguel, contas da casa...) aparecem sempre, mesmo antes de ter item.
    val comItens = gasto.filter { it.itens.isNotEmpty() || it.fixa }
    Cartao("Despesas fixas", sub = "o que se repete todo mês") {
        Text("Aluguel, internet, academia: cada item soma na categoria. Ligando \"usar a soma como orçamento\", o orçado da categoria passa a ser a soma.",
            color = cores.texto2, fontSize = 13.sp)
        Spacer(Modifier.height(8.dp))
        BotaoPrimario("Novo item") { novo = true }
    }
    if (comItens.isEmpty()) Cartao { Vazio("Nenhum item ainda.") }
    comItens.forEach { l ->
        val s = l.somaItens(mes); val o = l.orcado(mes); val pelaSoma = l.porItens && !l.definido(mes)
        Cartao {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Bolinha(l.cor); Text("  ${l.nome}", color = cores.texto, fontWeight = FontWeight.SemiBold, fontSize = 15.sp, modifier = Modifier.weight(1f))
                Text(l.grupo, color = cores.mudo, fontSize = 12.sp)
            }
            Text(when { pelaSoma -> "${mesCurto("$mes-01")}: ${brl(s)} é o orçamento"; o == null -> "${mesCurto("$mes-01")}: itens ${brl(s)} · sem orçamento"
                else -> "${mesCurto("$mes-01")}: itens ${brl(s)} de ${brl(o)} orçados · sobra ${brl(o - s)}" }, color = cores.texto2, fontSize = 12.sp)
            Marcar("usar a soma como orçamento", l.porItens) { v ->
                escopo.launch { gravar { Api.put("/api/categorias/${l.chave}", jsonDe("orcar_por_itens" to v)) } }
            }
            l.itens.forEach { i ->
                Row(Modifier.fillMaxWidth().clickable { item = i }.padding(vertical = 7.dp), verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text(i.s("nome"), color = cores.texto, fontSize = 14.sp)
                        Text("${i.sn("inicio")?.let { "de ${mesCurto("$it-01")}" } ?: "sempre"}${i.sn("fim")?.let { " até ${mesCurto("$it-01")}" } ?: ""}", color = cores.mudo, fontSize = 11.sp)
                    }
                    Text(brl(i.d("valor")), color = cores.texto, fontWeight = FontWeight.SemiBold, fontSize = 14.sp)
                }
            }
        }
    }
    item?.let { i -> EditarItem(i, gasto) { item = null } }
    if (novo) EditarItem(null, gasto) { novo = false }
}

@Composable
private fun EditarItem(i: JSONObject?, gasto: List<LinhaOrc>, aoFechar: () -> Unit) {
    val escopo = rememberCoroutineScope()
    var categoria by remember { mutableStateOf(i?.s("categoria") ?: gasto.firstOrNull()?.chave) }
    var nome by remember { mutableStateOf(i?.s("nome") ?: "") }
    var valor by remember { mutableStateOf(i?.d("valor")?.let(::valorTexto) ?: "") }
    var inicio by remember { mutableStateOf(i?.sn("inicio") ?: "") }
    var fim by remember { mutableStateOf(i?.sn("fim") ?: "") }
    var erro by remember { mutableStateOf<String?>(null) }
    AlertDialog(onDismissRequest = aoFechar, containerColor = cores.painelForte, title = { Text(if (i == null) "Nova despesa fixa" else "Despesa fixa") },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                SeletorCategoria("gasto", categoria) { categoria = it }
                Campo(nome, { nome = it }, "Item", dica = "Aluguel, internet, academia...")
                Campo(valor, { valor = it }, "Valor mensal", numerico = true)
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Campo(inicio, { inicio = it }, "De (AAAA-MM)", Modifier.weight(1f), dica = "sempre")
                    Campo(fim, { fim = it }, "Até", Modifier.weight(1f), dica = "sem fim")
                }
                erro?.let { Text(it, color = cores.ruim, fontSize = 13.sp) }
                if (i != null) TextButton(onClick = {
                    escopo.launch { if (gravar("Item apagado.") { Api.delete("/api/itens-fixos/${i.optInt("id")}") }) aoFechar() }
                }) { Text("Apagar item", color = cores.ruim) }
            }
        },
        confirmButton = { TextButton(onClick = {
            val v = numero(valor)
            if (v == null || nome.isBlank() || categoria == null) { erro = "Preencha a categoria, o item e o valor."; return@TextButton }
            val corpo = jsonDe("categoria" to categoria, "nome" to nome.trim(), "valor" to v, "inicio" to inicio.trim().ifEmpty { null }, "fim" to fim.trim().ifEmpty { null })
            escopo.launch {
                try {
                    if (i == null) Api.post("/api/itens-fixos", corpo) else Api.put("/api/itens-fixos/${i.optInt("id")}", corpo)
                    Vocab.carregar(); Estado.mudou(); aoFechar()
                } catch (e: Exception) { erro = e.message }
            }
        }) { Text("Salvar", color = cores.acento) } },
        dismissButton = { TextButton(onClick = aoFechar) { Text("Cancelar", color = cores.texto2) } })
}

@Composable
private fun AbaCategorias() {
    var editando by remember { mutableStateOf<JSONObject?>(null) }
    var nova by remember { mutableStateOf(false) }
    Cartao("Categorias", sub = "teto vazio = sem teto") {
        Text("Fixa não entra no \"ainda pode gastar\". Toque numa categoria para mudar nome, grupo, teto, cor ou apagar.", color = cores.texto2, fontSize = 13.sp)
        Spacer(Modifier.height(8.dp))
        BotaoPrimario("Nova categoria") { nova = true }
    }
    listOf("gasto" to "Gastos", "renda" to "Renda").forEach { (tipo, titulo) ->
        Cartao(titulo) {
            Vocab.categorias.filter { it.s("tipo") == tipo }.groupBy { it.s("grupo") }.forEach { (g, cs) ->
                Rotulo(g, Modifier.padding(top = 8.dp, bottom = 2.dp))
                cs.forEach { cat ->
                    Row(Modifier.fillMaxWidth().clickable { editando = cat }.padding(vertical = 7.dp), verticalAlignment = Alignment.CenterVertically) {
                        Bolinha(corCategoria(cat.s("id")))
                        Text("  ${cat.s("nome")}", color = cores.texto, fontSize = 14.sp, modifier = Modifier.weight(1f), maxLines = 1, overflow = TextOverflow.Ellipsis)
                        if (cat.optInt("fixa") == 1) Text("  fixa  ", color = cores.mudo, fontSize = 11.sp)
                        if (tipo == "gasto") Text(cat.dn("teto")?.let { brl(it) } ?: "sem teto", color = if (cat.dn("teto") == null) cores.mudo else cores.texto,
                            fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
                        Text("  ${cat.optInt("uso")}", color = cores.mudo, fontSize = 11.sp, modifier = Modifier.width(36.dp), textAlign = TextAlign.End)
                    }
                }
            }
        }
    }
    editando?.let { EditarCategoria(it) { editando = null } }
    if (nova) EditarCategoria(null) { nova = false }
}

private val PALETA = listOf("#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#6250d6", "#008300", "#0f9d9a", "#c93a39", "#8a5a44", "#5b6b7a", "#9a99a1")

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun EditarCategoria(cat: JSONObject?, aoFechar: () -> Unit) {
    val escopo = rememberCoroutineScope()
    var nome by remember { mutableStateOf(cat?.s("nome") ?: "") }
    var grupo by remember { mutableStateOf(cat?.s("grupo") ?: "") }
    var tipo by remember { mutableStateOf(cat?.s("tipo") ?: "gasto") }
    var teto by remember { mutableStateOf(cat?.dn("teto")?.let(::valorTexto) ?: "") }
    var fixa by remember { mutableStateOf(cat?.optInt("fixa") == 1) }
    var cor by remember { mutableStateOf(cat?.sn("cor")) }
    var destino by remember { mutableStateOf<String?>(null) }
    var apagando by remember { mutableStateOf(false) }
    var erro by remember { mutableStateOf<String?>(null) }
    val grupos = Vocab.categorias.map { it.s("grupo") }.distinct()
    AlertDialog(onDismissRequest = aoFechar, containerColor = cores.painelForte, title = { Text(if (cat == null) "Nova categoria" else if (apagando) "Apagar \"${cat.s("nome")}\"" else cat.s("nome")) },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                if (apagando && cat != null) {
                    if (cat.optInt("uso") > 0) {
                        Text("Esta categoria tem ${cat.optInt("uso")} lançamento(s). Para onde eles vão?", color = cores.texto)
                        Seletor("Mover para", Vocab.categorias.filter { it.s("tipo") == cat.s("tipo") && it.s("id") != cat.s("id") }
                            .map { it.s("id") to "${it.s("grupo")}: ${it.s("nome")}" }, destino) { destino = it }
                    } else Text("Ela não tem lançamentos.", color = cores.texto)
                } else {
                    Campo(nome, { nome = it }, "Nome")
                    Campo(grupo, { grupo = it }, "Grupo")
                    FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        grupos.filter { it != grupo }.take(10).forEach { gr -> Ficha(gr) { grupo = gr } }
                    }
                    if (cat == null) Segmentos(listOf("gasto" to "Gasto", "renda" to "Renda"), tipo) { tipo = it }
                    if (tipo == "gasto") {
                        Campo(teto, { teto = it }, "Teto mensal", numerico = true, dica = "vazio = sem teto")
                        Marcar("fixa (não entra no \"ainda pode gastar\")", fixa) { fixa = it }
                    }
                    if (cat != null) {
                        Rotulo("Cor")
                        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                            PALETA.forEach { h ->
                                val c = corHex(h) ?: Color.Gray
                                Box(Modifier.size(28.dp).clip(CircleShape).background(c)
                                    .border(if (cor == h) 3.dp else 0.dp, cores.texto, CircleShape).clickable { cor = h })
                            }
                            Ficha("do grupo", ativo = cor == null) { cor = null }
                        }
                    }
                }
                erro?.let { Text(it, color = cores.ruim, fontSize = 13.sp) }
                if (cat != null && !apagando) TextButton(onClick = { apagando = true }) { Text("Apagar categoria", color = cores.ruim) }
            }
        },
        confirmButton = { TextButton(onClick = {
            escopo.launch {
                try {
                    if (apagando && cat != null) {
                        if (cat.optInt("uso") > 0 && destino == null) { erro = "Escolha para onde vão os lançamentos."; return@launch }
                        Api.delete("/api/categorias/${cat.s("id")}" + if (cat.optInt("uso") > 0) "?mover_para=${Api.q(destino!!)}" else "")
                    } else if (cat == null) {
                        Api.post("/api/categorias", jsonDe("nome" to nome.trim(), "grupo" to grupo.trim(), "tipo" to tipo, "teto" to numero(teto), "fixa" to fixa))
                    } else {
                        val corpo = jsonDe("nome" to nome.trim(), "grupo" to grupo.trim())
                        if (tipo == "gasto") { val t = numero(teto); if (t == null) corpo.put("limpar_teto", true) else corpo.put("teto", t); corpo.put("fixa", fixa) }
                        if (cor == null) corpo.put("limpar_cor", true) else corpo.put("cor", cor)
                        Api.put("/api/categorias/${cat.s("id")}", corpo)
                    }
                    Vocab.carregar(); Estado.mudou(); aoFechar()
                } catch (e: Exception) { erro = e.message }
            }
        }) { Text(if (apagando) "Apagar" else "Salvar", color = if (apagando) cores.ruim else cores.acento) } },
        dismissButton = { TextButton(onClick = { if (apagando) apagando = false else aoFechar() }) { Text(if (apagando) "Voltar" else "Cancelar", color = cores.texto2) } })
}

@Composable
private fun AbaMetas(metas: List<JSONObject>) {
    var editando by remember { mutableStateOf<JSONObject?>(null) }
    var nova by remember { mutableStateOf(false) }
    Cartao("Metas de poupança", sub = "objetivo, prazo e aporte") {
        Text("Guarde numa conta separada (Caixinha ou CDB de liquidez diária). Aporte entra como poupança; para usar o dinheiro, o resgate desconta da meta e a compra entra como gasto.",
            color = cores.texto2, fontSize = 13.sp)
        Spacer(Modifier.height(8.dp))
        BotaoPrimario("Nova meta") { nova = true }
    }
    if (metas.isEmpty()) Cartao { Vazio("Nenhuma meta ainda.") }
    metas.forEach { m ->
        Cartao(modifier = Modifier.clickable { editando = m }) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(m.s("nome"), color = if (m.optInt("ativa") == 1) cores.texto else cores.mudo, fontWeight = FontWeight.SemiBold, fontSize = 15.sp, modifier = Modifier.weight(1f))
                if (m.optInt("ativa") != 1) Text("inativa", color = cores.mudo, fontSize = 12.sp)
            }
            Text(listOfNotNull(m.dn("alvo")?.let { "objetivo ${brl(it)}" }, m.sn("data_alvo")?.takeIf { it.isNotEmpty() }?.let { "até ${mesCurto("$it-01")}" },
                "aporte ${brl(m.d("aporte_mensal"))}/mês", m.s("onde").takeIf { it.isNotEmpty() }).joinToString(" · "), color = cores.texto2, fontSize = 12.sp)
            Text("Guardado ${brl(m.d("guardado_total"))}", color = cores.ok, fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
        }
    }
    editando?.let { EditarMeta(it) { editando = null } }
    if (nova) EditarMeta(null) { nova = false }
}

@Composable
private fun EditarMeta(m: JSONObject?, aoFechar: () -> Unit) {
    val escopo = rememberCoroutineScope()
    var nome by remember { mutableStateOf(m?.s("nome") ?: "") }
    var alvo by remember { mutableStateOf(m?.dn("alvo")?.let(::valorTexto) ?: "") }
    var prazo by remember { mutableStateOf(m?.sn("data_alvo") ?: "") }
    var aporte by remember { mutableStateOf(m?.d("aporte_mensal")?.let(::valorTexto) ?: "0") }
    var onde by remember { mutableStateOf(m?.s("onde") ?: "") }
    var ativa by remember { mutableStateOf(m == null || m.optInt("ativa") == 1) }
    var erro by remember { mutableStateOf<String?>(null) }
    AlertDialog(onDismissRequest = aoFechar, containerColor = cores.painelForte, title = { Text(if (m == null) "Nova meta" else m.s("nome")) },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Campo(nome, { nome = it }, "Nome", dica = "Reserva de emergência")
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Campo(alvo, { alvo = it }, "Objetivo (R$)", Modifier.weight(1f), numerico = true)
                    Campo(prazo, { prazo = it }, "Prazo (AAAA-MM)", Modifier.weight(1f))
                }
                Campo(aporte, { aporte = it }, "Aporte mensal planejado", numerico = true)
                Campo(onde, { onde = it }, "Onde fica", dica = "Caixinha Nubank")
                if (m != null) Marcar("ativa", ativa) { ativa = it }
                erro?.let { Text(it, color = cores.ruim, fontSize = 13.sp) }
                if (m != null && m.d("guardado_total") == 0.0) TextButton(onClick = {
                    escopo.launch { if (gravar("Meta apagada.") { Api.delete("/api/metas/${m.optInt("id")}") }) aoFechar() }
                }) { Text("Apagar meta", color = cores.ruim) }
            }
        },
        confirmButton = { TextButton(onClick = {
            val corpo = jsonDe("nome" to nome.trim(), "descricao" to (m?.s("descricao") ?: ""), "alvo" to numero(alvo), "data_alvo" to prazo.trim().ifEmpty { null },
                "aporte_mensal" to (numero(aporte) ?: 0.0), "onde" to onde.trim(), "ativa" to ativa)
            escopo.launch {
                try {
                    if (m == null) Api.post("/api/metas", corpo) else Api.put("/api/metas/${m.optInt("id")}", corpo)
                    Vocab.carregar(); Estado.mudou(); aoFechar()
                } catch (e: Exception) { erro = e.message }
            }
        }) { Text("Salvar", color = cores.acento) } },
        dismissButton = { TextButton(onClick = aoFechar) { Text("Cancelar", color = cores.texto2) } })
}
