package io.github.bbarrosdavi.financas.ui

import android.content.Intent
import android.provider.Settings
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import io.github.bbarrosdavi.financas.Ajustes
import io.github.bbarrosdavi.financas.Sincronizacao
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.text.DateFormat
import java.util.Date
import java.util.Locale
import kotlin.math.abs
import kotlin.math.roundToInt

@Composable
fun TelaAjustes(ajustes: Ajustes, tema: String, aoTrocarTema: (String) -> Unit) {
    val escopo = rememberCoroutineScope()
    var removendo by remember { mutableStateOf(false) }
    Column(Modifier.verticalScroll(rememberScrollState()).padding(horizontal = 10.dp, vertical = 8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        if (Estado.demo) Cartao("Dados de demonstração") {
            Text("O Finanças está mostrando dados inventados. Remover apaga a demonstração e o que você mexeu nela; os seus dados de verdade ficam como estão.",
                color = cores.texto2, fontSize = 13.sp)
            Spacer(Modifier.height(8.dp))
            BotaoPrimario("Remover dados de demonstração") { removendo = true }
        }
        Cartao("Aparência") {
            if (LocalAparencia.current.daConta)
                Text("A mesma da sua conta no site: tema de cores, claro ou escuro, transparência e papel de parede. Mude no site " +
                    "(Ajustes da casa) e o celular acompanha na próxima sincronização.", color = cores.texto2, fontSize = 12.sp)
            else Segmentos(listOf("sistema" to "Do sistema", "claro" to "Claro", "escuro" to "Escuro"), tema) { aoTrocarTema(it) }
            Spacer(Modifier.height(8.dp))
            BotaoSecundario("Rever o tour") { Tour.iniciar() }
        }
        Celular(ajustes)
        MesDaEntrada()
        Planilha()
    }
    if (removendo) Confirmar("Remover dados de demonstração",
        "O que você mexeu neles também sai, e o Finanças passa a mostrar os seus dados de verdade.", "Remover", { removendo = false }) {
        escopo.launch { removerDemo() }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun Celular(ajustes: Ajustes) {
    val ctx = LocalContext.current
    val escopo = rememberCoroutineScope()
    var url by remember { mutableStateOf(ajustes.url) }
    var chave by remember { mutableStateOf(ajustes.chave) }
    var apps by remember { mutableStateOf(ajustes.apps) }
    var outros by remember { mutableStateOf(ajustes.apps.filter { it !in Ajustes.APPS_PADRAO }.joinToString(", ")) }
    var msg by remember { mutableStateOf<Pair<String, Boolean>?>(null) }
    var ocupado by remember { mutableStateOf(false) }
    var acesso by remember { mutableStateOf(ajustes.acessoNotificacoes()) }
    var ultima by remember { mutableStateOf(ajustes.ultimaSincronia) }
    // Ao voltar da tela de acesso a notificações, a situação muda.
    LaunchedEffect(Estado.versao) { acesso = ajustes.acessoNotificacoes(); ultima = ajustes.ultimaSincronia }

    fun salvar() {
        ajustes.url = url; ajustes.chave = chave
        ajustes.apps = apps.filter { it in Ajustes.APPS_PADRAO }.toSet() + outros.split(',').map { it.trim() }.filter { it.isNotEmpty() }
        Sincronizacao.agora(ctx)
    }
    Cartao("Celular", Modifier.alvo("ajCelular"), sub = "este aparelho") {
        Text("As notificações dos apps marcados viram lançamentos aqui na hora, sem precisar do servidor. Com o servidor ao alcance (mesma rede ou VPN), " +
            "o app manda o que mudou aqui e recebe o que mudou lá.", color = cores.texto2, fontSize = 13.sp)
        Spacer(Modifier.height(8.dp))
        Text(if (acesso) "Acesso a notificações: liberado" else "Acesso a notificações: falta liberar",
            color = if (acesso) cores.ok else cores.atencao, fontWeight = FontWeight.SemiBold, fontSize = 14.sp)
        BotaoSecundario("Acesso a notificações") {
            ctx.startActivity(Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        }
        Rotulo("Apps monitorados", Modifier.padding(top = 8.dp))
        FlowRow {
            Ajustes.APPS_PADRAO.forEach { (pacote, nome) -> Marcar(nome, pacote in apps) { apps = if (it) apps + pacote else apps - pacote } }
        }
        Campo(outros, { outros = it }, "Outros apps (pacotes, separados por vírgula)")
        Rotulo("Servidor (opcional)", Modifier.padding(top = 10.dp))
        Campo(url, { url = it }, "Endereço do servidor", dica = "http://192.168.0.10:8095")
        Campo(chave, { chave = it }, "Chave (API_KEY)")
        Spacer(Modifier.height(8.dp))
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            BotaoPrimario("Salvar") { salvar(); msg = "Salvo." to true }
            BotaoSecundario("Testar conexão") {
                msg = "Testando..." to true
                escopo.launch { val (ok, texto) = withContext(Dispatchers.IO) { Sincronizacao.testar(url, chave) }; msg = texto to ok }
            }
            BotaoSecundario(if (ocupado) "Sincronizando..." else "Sincronizar agora") {
                if (ocupado) return@BotaoSecundario
                ocupado = true; msg = "Sincronizando..." to true
                salvar()
                escopo.launch {
                    val r = withContext(Dispatchers.IO) { Sincronizacao.rodar(ctx.applicationContext) }
                    ultima = ajustes.ultimaSincronia
                    msg = (if (r.optBoolean("ok")) "Sincronizado: ${r.optInt("enviadas")} enviada(s), ${r.optInt("recebidas")} recebida(s)." else r.optString("erro")) to r.optBoolean("ok")
                    runCatching { Vocab.carregar() }; Estado.mudou(); ocupado = false
                }
            }
        }
        msg?.let { (t, ok) -> Text(t, color = if (ok) cores.ok else cores.ruim, fontSize = 13.sp, modifier = Modifier.padding(top = 6.dp)) }
        val u = ultima.takeIf { it.isNotBlank() }?.let { runCatching { JSONObject(it) }.getOrNull() }
        Text("Última sincronização: " + if (u == null) "ainda não sincronizou" else
            DateFormat.getDateTimeInstance(DateFormat.SHORT, DateFormat.SHORT, Locale.forLanguageTag("pt-BR")).format(Date(u.optLong("quando"))) + ": " +
                if (u.optBoolean("ok")) "ok, ${u.optInt("enviadas")} enviada(s) e ${u.optInt("recebidas")} recebida(s)" else u.optString("erro"),
            color = cores.mudo, fontSize = 12.sp, modifier = Modifier.padding(top = 4.dp))
    }
}

/** O cadastro de pessoas (fica na aba Pessoas): nome no extrato e o que sugerir quando o dinheiro entra ou sai. */
@Composable
fun CadastroPessoas() {
    var editando by remember { mutableStateOf<JSONObject?>(null) }
    var nova by remember { mutableStateOf(false) }
    Cartao("Cadastro", Modifier.alvo("pessoasCadastro"), sub = "nome no extrato e o que sugerir") {
        if (Vocab.pessoas.isEmpty()) Vazio("Ninguém cadastrado.")
        Vocab.pessoas.forEach { p ->
            Row(Modifier.fillMaxWidth().clickable { editando = p }.padding(vertical = 7.dp), verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text(p.s("nome"), color = cores.texto, fontSize = 15.sp, fontWeight = FontWeight.SemiBold)
                    Text(listOf(p.s("tipo"), p.s("apelido_extrato").ifEmpty { "sem nome no extrato" }).joinToString(" · "), color = cores.mudo, fontSize = 12.sp)
                }
                Text("entra: ${rotuloSugestao(p.s("sugere_entrada"))}\nsai: ${rotuloSugestao(p.s("sugere_saida"))}", color = cores.texto2, fontSize = 11.sp)
            }
        }
        Spacer(Modifier.height(6.dp))
        BotaoPrimario("Adicionar pessoa") { nova = true }
    }
    editando?.let { EditarPessoa(it) { editando = null } }
    if (nova) EditarPessoa(null) { nova = false }
}

private fun rotuloSugestao(s: String) = if (s == "acerto" || s.isEmpty()) "acerto" else Vocab.categoria(s.substringAfter(':'))?.s("nome") ?: s

@Composable
private fun EditarPessoa(p: JSONObject?, aoFechar: () -> Unit) {
    val escopo = rememberCoroutineScope()
    var nome by remember { mutableStateOf(p?.s("nome") ?: "") }
    var apelido by remember { mutableStateOf(p?.s("apelido_extrato") ?: "") }
    var tipo by remember { mutableStateOf(p?.s("tipo") ?: "colega") }
    var entrada by remember { mutableStateOf(p?.s("sugere_entrada")?.ifEmpty { "acerto" } ?: "acerto") }
    var saida by remember { mutableStateOf(p?.s("sugere_saida")?.ifEmpty { "acerto" } ?: "acerto") }
    var erro by remember { mutableStateOf<String?>(null) }
    val sugeridas = listOf("acerto" to "acerto") + Vocab.categorias.map { "${it.s("tipo")}:${it.s("id")}" to "${it.s("tipo")}: ${it.s("nome")}" }
    AlertDialog(onDismissRequest = aoFechar, containerColor = cores.painelForte, title = { Text(if (p == null) "Nova pessoa" else p.s("nome")) },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Campo(nome, { nome = it }, "Nome")
                Campo(apelido, { apelido = it }, "Nome no extrato", dica = "FULANO DE TAL")
                Seletor("Tipo", listOf("colega", "familia", "credor", "outro").map { it to it }, tipo) { tipo = it }
                if (p != null) {
                    Seletor("Quando entra dinheiro dela", sugeridas, entrada) { entrada = it }
                    Seletor("Quando sai dinheiro para ela", sugeridas, saida) { saida = it }
                }
                erro?.let { Text(it, color = cores.ruim, fontSize = 13.sp) }
            }
        },
        confirmButton = { TextButton(onClick = {
            val corpo = jsonDe("nome" to nome.trim(), "apelido_extrato" to apelido.trim(), "tipo" to tipo, "sugere_entrada" to entrada, "sugere_saida" to saida)
            escopo.launch {
                try {
                    if (p == null) Api.post("/api/pessoas", corpo) else Api.put("/api/pessoas/${p.s("id")}", corpo)
                    Vocab.carregar(); Estado.mudou(); aoFechar()
                } catch (e: Exception) { erro = e.message }
            }
        }) { Text("Salvar", color = cores.acento) } },
        dismissButton = { TextButton(onClick = aoFechar) { Text("Cancelar", color = cores.texto2) } })
}

/** Renda que cai a partir do dia X conta como entrada do mês seguinte (Painel, Lançamentos, Orçamento, Projeção). */
@Composable
private fun MesDaEntrada() {
    val escopo = rememberCoroutineScope()
    val c = carregar { Api.obj("/api/parametros") }
    val prm = c.dado ?: return
    var ligado by remember(prm) { mutableStateOf(prm.optString("renda_mes_seguinte", "1") != "0") }
    var dia by remember(prm) { mutableStateOf(prm.optString("dia_renda_mes_seguinte", "25").ifEmpty { "25" }) }
    var msg by remember { mutableStateOf<String?>(null) }
    Cartao("Mês da entrada", sub = "Painel, Lançamentos, Orçamento e Projeção") {
        Marcar("Renda que cai a partir do dia abaixo conta como entrada do mês seguinte", ligado) { ligado = it }
        Row(verticalAlignment = Alignment.Bottom, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Campo(dia, { dia = it.filter(Char::isDigit).take(2) }, "Dia", Modifier.weight(1f), numerico = true)
            BotaoPrimario("Salvar") {
                val d = dia.toIntOrNull()
                if (d == null || d !in 1..31) { msg = "O dia vai de 1 a 31."; return@BotaoPrimario }
                escopo.launch {
                    if (gravar {
                            Api.put("/api/parametros/renda_mes_seguinte", jsonDe("valor" to if (ligado) "1" else "0"))
                            Api.put("/api/parametros/dia_renda_mes_seguinte", jsonDe("valor" to d.toString()))
                        }) { msg = "Salvo."; Estado.mudou() }
                }
            }
        }
        msg?.let { Text(it, color = cores.texto2, fontSize = 12.sp, modifier = Modifier.padding(top = 4.dp)) }
    }
}

@Composable
private fun Planilha() {
    val ctx = LocalContext.current
    val escopo = rememberCoroutineScope()
    var bytes by remember { mutableStateOf<ByteArray?>(null) }
    val salvar = rememberLauncherForActivityResult(ActivityResultContracts.CreateDocument("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")) { uri ->
        val b = bytes ?: return@rememberLauncherForActivityResult
        bytes = null
        if (uri != null) escopo.launch {
            runCatching { withContext(Dispatchers.IO) { ctx.contentResolver.openOutputStream(uri)?.use { it.write(b) } } }
                .onSuccess { Estado.mensagem = "Planilha salva." }.onFailure { Estado.mensagem = "Não deu para salvar: ${it.message}" }
        }
    }
    Cartao("Planilha") {
        Text("Todas as tabelas (lançamentos, orçamento, metas, pessoas) num arquivo .xlsx, para abrir no LibreOffice, no Planilhas Google ou onde preferir.",
            color = cores.texto2, fontSize = 13.sp)
        Spacer(Modifier.height(8.dp))
        BotaoSecundario("Baixar tabelas (.xlsx)") {
            escopo.launch {
                try { bytes = Api.bytes("/api/exportar.xlsx"); salvar.launch("financas-${hojeISO()}.xlsx") }
                catch (e: Exception) { Estado.mensagem = "Não deu para gerar a planilha: ${e.message}" }
            }
        }
    }
}

