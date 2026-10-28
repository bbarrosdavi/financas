package io.github.bbarrosdavi.financas.ui

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Badge
import androidx.compose.material3.BadgedBox
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
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
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import io.github.bbarrosdavi.financas.Ajustes
import kotlinx.coroutines.launch

private class Aba(val chave: String, val nome: String, val icone: ImageVector)

private val ABAS = listOf(
    Aba("painel", "Painel", Icones.painel), Aba("pendentes", "Pendentes", Icones.pendentes),
    Aba("lancamentos", "Lançamentos", Icones.lancamentos), Aba("orcamento", "Orçamento", Icones.orcamento), Aba("mais", "Mais", Icones.mais),
)
private val DE_MAIS = mapOf("importar" to "Importar", "pessoas" to "Pessoas", "projecao" to "Projeção", "ajustes" to "Ajustes")

@Composable
fun AppFinancas(ajustes: Ajustes, tema: String, aoTrocarTema: (String) -> Unit, aoSair: () -> Unit) {
    var tela by rememberSaveable { mutableStateOf("painel") }
    val escopo = rememberCoroutineScope()
    val avisos = remember { SnackbarHostState() }
    var removendo by remember { mutableStateOf(false) }

    LaunchedEffect(Unit) {
        runCatching {
            Vocab.carregar()
            var demo = Api.obj("/api/demo")
            // Primeiro uso num Finanças vazio: a demonstração liga sozinha, para o tour ter o que mostrar.
            if (!ajustes.tourVisto && demo.optBoolean("vazio") && !demo.optBoolean("ativo"))
                demo = org.json.JSONObject(Api.put("/api/demo", jsonDe("ativo" to true)))
            Estado.demo = demo.optBoolean("ativo")
            Vocab.carregar(); Estado.mudou()
        }.onFailure { Estado.mensagem = it.message }
        Tour.aoTerminar = { ajustes.tourVisto = true }
        if (!ajustes.tourVisto) Tour.iniciar()
    }
    LaunchedEffect(Estado.mensagem) { Estado.mensagem?.let { avisos.showSnackbar(it); Estado.mensagem = null } }
    BackHandler(enabled = tela != "painel" && !Tour.ativo) { tela = if (tela in DE_MAIS) "mais" else "painel" }
    BackHandler(enabled = Tour.ativo) { Tour.fechar() }

    Box(Modifier.fillMaxSize()) {
        Scaffold(
            containerColor = cores.fundo,
            snackbarHost = { SnackbarHost(avisos) },
            topBar = {
                Column(Modifier.background(cores.fundo).statusBarsPadding()) {
                    Row(Modifier.fillMaxWidth().padding(start = 16.dp, end = 4.dp, top = 4.dp), verticalAlignment = Alignment.CenterVertically) {
                        if (tela in DE_MAIS) IconButton(onClick = { tela = "mais" }) { Icon(Icones.voltar, "Voltar", tint = cores.texto) }
                        Text(DE_MAIS[tela] ?: ABAS.first { it.chave == tela }.nome.let { if (tela == "painel") "Finanças" else it },
                            color = cores.texto, fontSize = 20.sp, fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f))
                        val escuro = cores.escuro
                        IconButton(onClick = { aoTrocarTema(if (escuro) "claro" else "escuro") }) {
                            Icon(if (cores.escuro) Icones.sol else Icones.lua, "Claro ou escuro", tint = cores.texto2, modifier = Modifier.size(22.dp))
                        }
                    }
                    if (Estado.demo) FaixaDemo { removendo = true }
                }
            },
            bottomBar = {
                NavigationBar(containerColor = cores.painel, modifier = Modifier.alvo("abas")) {
                    ABAS.forEach { a ->
                        val on = tela == a.chave || (a.chave == "mais" && tela in DE_MAIS)
                        NavigationBarItem(selected = on, onClick = { tela = a.chave },
                            icon = {
                                if (a.chave == "pendentes" && Estado.pendentes > 0)
                                    BadgedBox(badge = { Badge(containerColor = cores.ruim) { Text("${Estado.pendentes}") } }) { Icon(a.icone, a.nome) }
                                else Icon(a.icone, a.nome)
                            },
                            label = { Text(a.nome, fontSize = 11.sp, maxLines = 1) },
                            colors = NavigationBarItemDefaults.colors(selectedIconColor = cores.acento, selectedTextColor = cores.acento,
                                indicatorColor = cores.acentoSuave, unselectedIconColor = cores.texto2, unselectedTextColor = cores.texto2))
                    }
                }
            },
        ) { margens ->
            Box(Modifier.padding(margens).fillMaxSize()) {
                when (tela) {
                    "painel" -> TelaPainel { tela = it }
                    "pendentes" -> TelaPendentes()
                    "lancamentos" -> TelaLancamentos()
                    "orcamento" -> TelaOrcamento()
                    "mais" -> TelaMais { tela = it }
                    "importar" -> TelaImportar()
                    "pessoas" -> TelaPessoas()
                    "projecao" -> TelaProjecao()
                    "ajustes" -> TelaAjustes(ajustes, tema, aoTrocarTema)
                }
            }
        }
        TourCamada { tela = it }
    }
    if (removendo) Confirmar("Remover dados de demonstração",
        "O que você mexeu neles também sai, e o Finanças passa a mostrar os seus dados de verdade.", "Remover", { removendo = false }) {
        escopo.launch { removerDemo() }
    }
}

suspend fun removerDemo() {
    gravar("Dados de demonstração removidos.") { Api.put("/api/demo", jsonDe("ativo" to false)); Estado.demo = false }
}

@Composable
private fun FaixaDemo(aoRemover: () -> Unit) {
    Row(Modifier.padding(horizontal = 12.dp, vertical = 6.dp).fillMaxWidth().border(1.dp, cores.atencao, RoundedCornerShape(10.dp))
        .background(cores.painel, RoundedCornerShape(10.dp)).padding(horizontal = 12.dp, vertical = 8.dp), verticalAlignment = Alignment.CenterVertically) {
        Text(negrito("**Dados de demonstração.** Inventados, para você explorar."), color = cores.texto, fontSize = 13.sp, modifier = Modifier.weight(1f))
        Text("Remover", color = cores.acento, fontWeight = FontWeight.SemiBold, fontSize = 14.sp,
            modifier = Modifier.clickable(onClick = aoRemover).padding(start = 10.dp, top = 4.dp, bottom = 4.dp))
    }
}

@Composable
private fun TelaMais(irPara: (String) -> Unit) {
    val itens = listOf(
        Triple("importar", Icones.importar, "Extratos e faturas (.pdf, .csv, .xlsx) e notificações descartadas"),
        Triple("pessoas", Icones.pessoas, "Quem te deve e a quem você deve; contas que alguém pagou"),
        Triple("projecao", Icones.projecao, "Os próximos meses e os eventos que mudam a conta"),
        Triple("ajustes", Icones.ajustes, "Celular, servidor, pessoas, tema, demonstração e tour"),
    )
    Column(Modifier.padding(12.dp)) {
        itens.forEach { (k, icone, desc) ->
            Cartao(modifier = Modifier.padding(bottom = 10.dp).clickable { irPara(k) }) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(icone, null, tint = cores.acento, modifier = Modifier.size(26.dp))
                    Column(Modifier.weight(1f).padding(start = 14.dp)) {
                        Text(DE_MAIS.getValue(k), color = cores.texto, fontSize = 16.sp, fontWeight = FontWeight.SemiBold)
                        Text(desc, color = cores.mudo, fontSize = 13.sp)
                    }
                    Icon(Icones.seta, null, tint = cores.mudo)
                }
            }
        }
    }
}
