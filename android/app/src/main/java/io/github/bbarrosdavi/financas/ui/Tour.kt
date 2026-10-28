package io.github.bbarrosdavi.financas.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.navigationBars
import androidx.compose.foundation.layout.statusBars
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.relocation.BringIntoViewRequester
import androidx.compose.foundation.relocation.bringIntoViewRequester
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.composed
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Rect
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.BlendMode
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.CompositingStrategy
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.boundsInRoot
import androidx.compose.ui.layout.onGloballyPositioned
import androidx.compose.ui.layout.onSizeChanged
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.delay
import kotlin.math.max
import kotlin.math.min
import kotlin.math.roundToInt

class PassoTour(val tela: String, val alvo: String?, val titulo: String, val texto: () -> String)

/** Tour do primeiro uso: destaca cada parte das telas e diz o que é, como ler e o que colocar ali. */
object Tour {
    var ativo by mutableStateOf(false)
    var passo by mutableIntStateOf(0)
    val alvos = mutableStateMapOf<String, Rect>()
    val trazer = mutableMapOf<String, BringIntoViewRequester>()
    var aoTerminar: () -> Unit = {}

    fun iniciar() { passo = 0; ativo = true }
    fun fechar() { ativo = false; aoTerminar() }

    val passos = listOf(
        PassoTour("painel", null, "Bem-vindo ao Finanças") {
            "Em poucos minutos este tour passa por cada tela: o que mostra, como ler os números e o que você coloca em cada lugar." +
                (if (Estado.demo) "\n\n**Os dados que aparecem agora são de demonstração**: pessoas, lugares e valores inventados, para cada painel ter o que mostrar. " +
                    "Os seus dados de verdade ficam à parte. Depois de explorar, toque em **Remover** na faixa do topo (ou em Ajustes)." else "") +
                "\n\nDá para sair a qualquer hora e rever depois em **Ajustes**."
        },
        PassoTour("painel", "abas", "As abas") {
            "**Painel**: o resumo. **Pendentes**: o que falta classificar (o número diz quantos). **Lançamentos**: tudo que entrou e saiu. " +
                "**Orçamento**: quanto você planeja gastar. Em **Mais** ficam Importar, Pessoas, Projeção e Ajustes."
        },
        PassoTour("painel", "periodo", "Qual período ver") {
            "Semana, mês ou ano; as setas andam no tempo e **Hoje** volta ao atual. Salário que cai do dia 25 em diante conta no mês seguinte."
        },
        PassoTour("painel", "resultado", "Resultado") {
            "Entradas menos gastos do período: verde sobrou, vermelho faltou. Transferência entre contas suas e acerto com pessoas não contam. " +
                "**Juros e taxas** é a parte dos gastos que foi juro, IOF ou tarifa."
        },
        PassoTour("painel", "podeGastar", "Ainda pode gastar") {
            "Quanto ainda cabe no orçamento das categorias variáveis (mercado, delivery, transporte, lazer). O traço na barra é o ritmo: até onde ela deveria ir hoje. " +
                "Verde no ritmo, amarelo acima, vermelho estourou.\n\n**O que colocar:** o teto de cada categoria, no **Orçamento**."
        },
        PassoTour("painel", "kpis", "Conta, cartão, pessoas e pendentes") {
            "**Conta**: o saldo que o app do banco mostra (toque para informar); a diferença para o calculado é o que falta lançar. " +
                "**Cartão**: a fatura em aberto e o limite livre. **Pessoas**: quem te deve e a quem você deve. **Pendentes**: quantos esperam você."
        },
        PassoTour("painel", "categorias", "Categorias") {
            "Cada grupo contra o teto: gasto, teto, porcentagem e quanto resta (verde) ou passou (vermelho). Toque no grupo para abrir as categorias; " +
                "toque numa categoria para ver a evolução dos últimos meses. Parcela antiga (da 2ª em diante) aparece à parte."
        },
        PassoTour("painel", "grafico", "Entradas e gastos") { "Entradas, gastos e poupança de cada mês, com o orçado em tom claro atrás. Toque numa coluna para ver os valores." },
        PassoTour("painel", "composicao", "Para onde foi") { "A fatia de cada grupo no gasto do período." },
        PassoTour("painel", "entradas", "Entradas do período") { "O que entrou, por categoria de renda. Vem dos lançamentos classificados como renda." },
        PassoTour("painel", "metas", "Poupança e metas") {
            "Planejado, guardado e o que falta em cada meta, e o total contra o objetivo.\n\n**O que colocar:** crie as metas no **Orçamento**; guardar é lançar como poupança ligada à meta."
        },
        PassoTour("painel", "cobrancas", "Próximas cobranças no cartão") { "As parcelas que ainda vão cair, por mês da fatura. Aparecem sozinhas quando uma compra parcelada entra." },
        PassoTour("painel", "destinos", "Maiores destinos") { "Onde mais saiu dinheiro no período, por lugar ou pessoa." },
        PassoTour("painel", "projecaoPainel", "Projeção") { "Os próximos meses: resultado, quanto falta cobrir e o saldo livre. A conta completa fica em **Mais > Projeção**." },
        PassoTour("pendentes", "pendentes", "Pendentes") {
            "O que o sistema não classifica sozinho: lugar novo, Pix para uma pessoa, recarga do PicPay no crédito.\n\n" +
                "**O que fazer:** toque na sugestão (azul) ou numa categoria. **Dividir** separa em partes, como a sua e a de um colega. " +
                "Com **sugerir da próxima vez**, o mesmo lugar já chega com a sugestão."
        },
        PassoTour("lancamentos", "lancResumo", "Lançamentos") { "Entradas, gastos e resultado do que está filtrado, e quanto falta lançar na conta." },
        PassoTour("lancamentos", "lancFiltros", "Filtros") { "Mês, categoria, tipo e busca pelo nome. O resumo acompanha o filtro." },
        PassoTour("lancamentos", "lancNovo", "Lançar à mão") {
            "Para o que não passa pelo banco: dinheiro vivo, uma conta que alguém pagou, um acerto.\n\n**O que colocar:** o tipo, a categoria ou a pessoa, o valor, o que foi, a data e a conta."
        },
        PassoTour("lancamentos", "lancLista", "Tudo que entrou e saiu") {
            "Toque num lançamento para mudar a categoria, dividir em partes ou apagar (só o lançado à mão ou pelo celular; o do extrato é a fonte)."
        },
        PassoTour("orcamento", "orcAbas", "Orçamento") {
            "**Mês**: cada categoria com orçado, realizado e diferença, para o mês escolhido; toque no orçado para mudar. **Ano**: a visão do ano inteiro. " +
                "**Fixas**: despesas que se repetem (aluguel, internet). **Categorias**: teto e se é fixa. **Metas**: objetivos de poupança.\n\n" +
                "**Comece por aqui:** dê um teto para mercado, delivery, transporte e lazer."
        },
        PassoTour("importar", "importarArquivos", "Importar extrato e fatura") {
            "Escolha os arquivos do banco: Nubank em .pdf ou .csv, Bradesco em .pdf, .csv ou .xlsx. O que já existe não duplica, e a compra que veio pelo celular é casada com a linha do arquivo. " +
                "No celular, .pdf não é lido: use o .csv ou o .xlsx, ou importe o .pdf no computador."
        },
        PassoTour("importar", "importarDescartadas", "Notificações descartadas") { "O que o filtro entendeu que não era compra. Se alguma era, **Resgatar** transforma em lançamento." },
        PassoTour("pessoas", "pessoasSaldos", "Quem deve a quem") { "Positivo: a pessoa te deve. Negativo: você deve a ela. Muda quando uma parte é um **acerto**." },
        PassoTour("pessoas", "pessoasPagou", "Alguém pagou por você") { "Quando outra pessoa paga uma conta sua: o gasto entra na categoria e vira dívida com ela, sem mexer no saldo da conta." },
        PassoTour("projecao", "projResumo", "Projeção") { "Mês a mês até o horizonte: renda, custo de vida (do Orçamento), o cartão já contratado e o resultado." },
        PassoTour("projecao", "projEventos", "Eventos") { "**O que colocar:** o que muda e quando (um aumento, uma renda que acaba, uma viagem, o 13º). A projeção recalcula na hora." },
        PassoTour("ajustes", "ajCelular", "Celular") {
            "As notificações dos apps de banco marcados viram lançamentos aqui na hora, mesmo sem servidor.\n\n**O que fazer:** toque em **Acesso a notificações** e ligue o Finanças. " +
                "Se tiver o Finanças no computador, coloque o endereço e a chave que aparecem em Ajustes no computador e toque em **Testar conexão**."
        },
        PassoTour("ajustes", "ajPessoas", "Pessoas") { "**O que colocar:** quem divide contas com você, com o nome como aparece no extrato. Assim o Pix dessa pessoa vem com sugestão." },
        PassoTour("painel", null, "Pronto para começar") {
            (if (Estado.demo) "Explore à vontade com os dados de demonstração. Para começar de verdade, toque em **Remover** na faixa do topo e então:\n\n" else "Um bom começo:\n\n") +
                "1. No **Orçamento**, dê um teto para as categorias.\n2. Em **Ajustes**, cadastre quem divide contas com você e libere o acesso a notificações.\n" +
                "3. Em **Mais > Importar**, traga o extrato e a fatura do mês.\n4. Classifique o que aparecer em **Pendentes**."
        },
    )
}

/** Marca um elemento como alvo do tour (posição na tela e como rolar até ele). */
@OptIn(ExperimentalFoundationApi::class)
fun Modifier.alvo(chave: String): Modifier = composed {
    val r = remember { BringIntoViewRequester() }
    DisposableEffect(chave) {
        Tour.trazer[chave] = r
        onDispose { if (Tour.trazer[chave] === r) { Tour.trazer.remove(chave); Tour.alvos.remove(chave) } }
    }
    this.bringIntoViewRequester(r).onGloballyPositioned { Tour.alvos[chave] = it.boundsInRoot() }
}

@Composable
fun TourCamada(irPara: (String) -> Unit) {
    if (!Tour.ativo) return
    val passo = Tour.passos[Tour.passo]
    val n = Tour.passos.size
    var pronto by remember { mutableStateOf(false) }
    LaunchedEffect(Tour.passo) {
        pronto = false
        irPara(passo.tela)
        delay(400)                                 // a tela desenha
        passo.alvo?.let { runCatching { Tour.trazer[it]?.bringIntoView() } }
        delay(250)
        pronto = true
    }
    val densidade = LocalDensity.current
    BoxWithConstraints(Modifier.fillMaxSize()) {
        val w = constraints.maxWidth.toFloat()
        val h = constraints.maxHeight.toFloat()
        val folga = with(densidade) { 12.dp.toPx() }
        val margem = with(densidade) { 6.dp.toPx() }
        var alturaBalao by remember { mutableIntStateOf(0) }
        // O balão fica entre a barra de status e a de navegação; o destaque pode ir até as bordas.
        val acima = WindowInsets.statusBars.getTop(densidade).toFloat() + folga
        val abaixo = h - WindowInsets.navigationBars.getBottom(densidade) - folga
        val alvo = if (pronto) passo.alvo?.let { Tour.alvos[it] } else null
        // Onde o balão cabe sem cobrir o alvo; sem espaço, fica na borda e o destaque vai só até ele.
        var foco: Rect? = null
        var yBalao = (h - alturaBalao) / 2
        if (alvo != null) {
            var topo = max(alvo.top, 0f)
            var baixo = min(alvo.bottom, h)
            when {
                abaixo - alvo.bottom >= alturaBalao + folga -> yBalao = alvo.bottom + folga
                alvo.top - acima >= alturaBalao + folga -> yBalao = alvo.top - alturaBalao - folga
                (alvo.top + alvo.bottom) / 2 < h / 2 -> { yBalao = abaixo - alturaBalao; baixo = min(baixo, yBalao - folga) }
                else -> { yBalao = acima; topo = max(topo, yBalao + alturaBalao + folga) }
            }
            if (baixo - topo > 2 * margem) foco = Rect(max(alvo.left, 0f) - margem, topo - margem, min(alvo.right, w) + margem, baixo + margem)
        }
        val corAnel = cores.acento
        Canvas(Modifier.fillMaxSize().graphicsLayer(compositingStrategy = CompositingStrategy.Offscreen).pointerInput(Unit) { detectTapGestures { } }) {
            drawRect(Color.Black.copy(alpha = 0.55f))
            foco?.let {
                val raio = CornerRadius(14.dp.toPx())
                drawRoundRect(Color.Transparent, Offset(it.left, it.top), Size(it.width, it.height), raio, blendMode = BlendMode.Clear)
                drawRoundRect(corAnel, Offset(it.left, it.top), Size(it.width, it.height), raio, style = Stroke(2.dp.toPx()))
            }
        }
        Surface(shape = RoundedCornerShape(12.dp), color = cores.painel, shadowElevation = 8.dp,
            modifier = Modifier.padding(horizontal = 10.dp).fillMaxWidth().heightIn(max = 420.dp)
                .offset { IntOffset(0, yBalao.coerceIn(min(acima, max(0f, abaixo - alturaBalao)), max(acima, abaixo - alturaBalao)).roundToInt()) }
                .onSizeChanged { alturaBalao = it.height }) {
            Column(Modifier.padding(16.dp)) {
                Row {
                    Text(passo.titulo, color = cores.texto, fontWeight = FontWeight.SemiBold, fontSize = 16.sp, modifier = Modifier.weight(1f))
                    Text("${Tour.passo + 1} de $n", color = cores.mudo, fontSize = 12.sp)
                }
                Column(Modifier.weight(1f, fill = false).verticalScroll(rememberScrollState()).padding(vertical = 8.dp)) {
                    Text(negrito(passo.texto()), color = cores.texto, fontSize = 14.sp, lineHeight = 20.sp)
                }
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    BotaoSecundario("Sair") { Tour.fechar() }
                    Spacer(Modifier.weight(1f))
                    if (Tour.passo > 0) BotaoSecundario("Voltar") { Tour.passo-- }
                    BotaoPrimario(if (Tour.passo == n - 1) "Começar" else "Próximo") {
                        if (Tour.passo == n - 1) { Tour.fechar(); irPara("painel") } else Tour.passo++
                    }
                }
            }
        }
    }
}

