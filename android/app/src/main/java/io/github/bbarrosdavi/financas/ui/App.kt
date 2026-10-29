package io.github.bbarrosdavi.financas.ui

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Badge
import androidx.compose.material3.BadgedBox
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
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
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import io.github.bbarrosdavi.financas.Ajustes
import kotlinx.coroutines.launch

private class Aba(val chave: String, val nome: String, val icone: ImageVector)

// Embaixo, as cinco de uso diário (o limite de 5 do Material 3); em cima, à vista, as outras três. Nada fica
// escondido num "Mais" (escondido, um destino é achado bem menos vezes: Nielsen Norman Group).
private val ABAS = listOf(
    Aba("painel", "Painel", Icones.painel), Aba("pendentes", "Pendentes", Icones.pendentes),
    Aba("lancamentos", "Lançamentos", Icones.lancamentos), Aba("pessoas", "Pessoas", Icones.pessoas),
    Aba("orcamento", "Orçamento", Icones.orcamento),
)
private val NO_ALTO = listOf(
    Aba("importar", "Importar", Icones.importar), Aba("projecao", "Projeção", Icones.projecao), Aba("ajustes", "Ajustes", Icones.ajustes),
)

@Composable
fun AppFinancas(ajustes: Ajustes, tema: String, aoTrocarTema: (String) -> Unit, aoSair: () -> Unit) {
    var tela by rememberSaveable { mutableStateOf("painel") }
    val escopo = rememberCoroutineScope()
    val avisos = remember { SnackbarHostState() }
    var removendo by remember { mutableStateOf(false) }
    val ap = LocalAparencia.current

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
    BackHandler(enabled = tela != "painel" && !Tour.ativo) { tela = "painel" }
    BackHandler(enabled = Tour.ativo) { Tour.fechar() }

    FundoDoApp {
        Scaffold(
            containerColor = Color.Transparent,
            snackbarHost = { SnackbarHost(avisos) },
            topBar = {
                Column(Modifier.statusBarsPadding()) {
                    Row(Modifier.fillMaxWidth().height(46.dp).padding(start = 14.dp, end = 2.dp), verticalAlignment = Alignment.CenterVertically) {
                        val nome = (ABAS + NO_ALTO).firstOrNull { it.chave == tela }?.nome ?: ""
                        Text(if (tela == "painel") "Finanças" else nome, color = cores.texto, fontSize = 17.sp, fontWeight = FontWeight.Bold,
                            modifier = Modifier.weight(1f))
                        NO_ALTO.forEach { a ->
                            val on = tela == a.chave
                            IconButton(onClick = { tela = if (on) "painel" else a.chave }, modifier = Modifier.size(40.dp)) {
                                Box(Modifier.size(32.dp).clip(RoundedCornerShape(8.dp)).background(if (on) cores.acentoSuave else Color.Transparent),
                                    contentAlignment = Alignment.Center) {
                                    Icon(a.icone, a.nome, tint = if (on) cores.acento else cores.texto2, modifier = Modifier.size(19.dp))
                                }
                            }
                        }
                        // Com a aparência da conta (vinda do servidor), claro ou escuro se escolhe lá, como o resto.
                        if (!ap.daConta) {
                            val escuro = cores.escuro
                            IconButton(onClick = { aoTrocarTema(if (escuro) "claro" else "escuro") }, modifier = Modifier.size(40.dp)) {
                                Icon(if (escuro) Icones.sol else Icones.lua, "Claro ou escuro", tint = cores.texto2, modifier = Modifier.size(19.dp))
                            }
                        }
                    }
                    if (Estado.demo) FaixaDemo { removendo = true }
                }
            },
            bottomBar = { BarraDeAbas(tela) { tela = it } },
        ) { margens ->
            Box(Modifier.padding(margens).fillMaxSize()) {
                when (tela) {
                    "painel" -> TelaPainel { tela = it }
                    "pendentes" -> TelaPendentes()
                    "lancamentos" -> TelaLancamentos()
                    "orcamento" -> TelaOrcamento()
                    "importar" -> TelaImportar()
                    "pessoas" -> TelaPessoas()
                    "projecao" -> TelaProjecao()
                    "ajustes" -> TelaAjustes(ajustes, tema, aoTrocarTema)
                }
            }
        }
        TourCamada { tela = it }
    }
    Estado.grafico?.let { (q, nome) -> Evolucao(q, nome, "mes") { Estado.grafico = null } }
    if (removendo) Confirmar("Remover dados de demonstração",
        "O que você mexeu neles também sai, e o Finanças passa a mostrar os seus dados de verdade.", "Remover", { removendo = false }) {
        escopo.launch { removerDemo() }
    }
}

/** A barra de baixo, compacta como a do site: ícone de 20 dp, nome em 10 sp, o número de pendentes no ícone. */
@Composable
private fun BarraDeAbas(tela: String, irPara: (String) -> Unit) {
    val linha = cores.linha
    Row(Modifier.fillMaxWidth().background(cores.painelForte).drawBehind { drawLine(linha, Offset(0f, 0f), Offset(size.width, 0f), 1f) }
        .navigationBarsPadding().height(54.dp).alvo("abas"), horizontalArrangement = Arrangement.SpaceEvenly) {
        ABAS.forEach { a ->
            val on = tela == a.chave
            val cor = if (on) cores.acento else cores.texto2
            Column(Modifier.weight(1f).fillMaxHeight().clickable { irPara(a.chave) }, horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.Center) {
                Box(Modifier.clip(RoundedCornerShape(12.dp)).background(if (on) cores.acentoSuave else Color.Transparent)
                    .padding(horizontal = 12.dp, vertical = 3.dp)) {
                    if (a.chave == "pendentes" && Estado.pendentes > 0)
                        BadgedBox(badge = { Badge(containerColor = cores.ruim) { Text("${Estado.pendentes}", fontSize = 9.sp) } }) {
                            Icon(a.icone, a.nome, tint = cor, modifier = Modifier.size(20.dp))
                        }
                    else Icon(a.icone, a.nome, tint = cor, modifier = Modifier.size(20.dp))
                }
                Text(a.nome, color = cor, fontSize = 10.sp, maxLines = 1, fontWeight = if (on) FontWeight.SemiBold else FontWeight.Normal,
                    modifier = Modifier.padding(top = 2.dp))
            }
        }
    }
}

suspend fun removerDemo() {
    gravar("Dados de demonstração removidos.") { Api.put("/api/demo", jsonDe("ativo" to false)); Estado.demo = false }
}

@Composable
private fun FaixaDemo(aoRemover: () -> Unit) {
    Row(Modifier.padding(horizontal = 10.dp, vertical = 4.dp).fillMaxWidth().border(1.dp, cores.atencao, RoundedCornerShape(10.dp))
        .background(cores.painel, RoundedCornerShape(10.dp)).padding(horizontal = 10.dp, vertical = 6.dp), verticalAlignment = Alignment.CenterVertically) {
        Text(negrito("**Dados de demonstração.** Inventados, para você explorar."), color = cores.texto, fontSize = 12.sp, modifier = Modifier.weight(1f))
        Text("Remover", color = cores.acento, fontWeight = FontWeight.SemiBold, fontSize = 13.sp,
            modifier = Modifier.clickable(onClick = aoRemover).padding(start = 10.dp, top = 4.dp, bottom = 4.dp))
    }
}
