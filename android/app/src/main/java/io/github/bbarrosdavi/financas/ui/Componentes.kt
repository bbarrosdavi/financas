package io.github.bbarrosdavi.financas.ui

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CheckboxDefaults
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/** O painel do site: fundo do tema, cantos de 14 dp, título em versalete pequeno e, se houver, um subtítulo. */
@Composable
fun Cartao(titulo: String? = null, modifier: Modifier = Modifier, sub: String? = null, acao: (@Composable RowScope.() -> Unit)? = null,
           conteudo: @Composable ColumnScope.() -> Unit) {
    Surface(modifier = modifier.fillMaxWidth(), shape = RoundedCornerShape(14.dp), color = cores.painel,
        shadowElevation = if (cores.escuro) 0.dp else 2.dp, border = BorderStroke(1.dp, cores.linha)) {
        Column(Modifier.padding(14.dp)) {
            if (titulo != null) {
                Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.padding(bottom = 8.dp)) {
                    Text(titulo.uppercase(), color = cores.texto2, fontSize = 12.sp, fontWeight = FontWeight.Bold, letterSpacing = 0.8.sp,
                        modifier = Modifier.weight(1f))
                    if (sub != null) Text(sub, color = cores.mudo, fontSize = 11.sp)
                    acao?.invoke(this)
                }
            }
            conteudo()
        }
    }
}

@Composable
fun Rotulo(texto: String, modifier: Modifier = Modifier) = Text(texto, color = cores.mudo, fontSize = 12.sp, modifier = modifier)

@Composable
fun Grande(texto: String, cor: Color = cores.texto) = Text(texto, color = cor, fontSize = 28.sp, fontWeight = FontWeight.Bold)

@Composable
fun LinhaKV(rotulo: String, valor: String, cor: Color = cores.texto, negrito: Boolean = true) {
    Row(Modifier.fillMaxWidth().padding(vertical = 2.dp), verticalAlignment = Alignment.CenterVertically) {
        Text(rotulo, color = cores.texto2, fontSize = 13.sp, modifier = Modifier.weight(1f))
        Text(valor, color = cor, fontSize = 13.sp, fontWeight = if (negrito) FontWeight.SemiBold else FontWeight.Normal)
    }
}

/** Barra de progresso do site: verde, âmbar ou vermelha, com a marca do ritmo (quanto do período já passou). */
@Composable
fun Barra(fracao: Double, cor: Color, ritmo: Double? = null, altura: Dp = 8.dp) {
    Box(Modifier.fillMaxWidth().height(altura).clip(RoundedCornerShape(4.dp)).background(cores.trilho)) {
        Box(Modifier.fillMaxWidth(fracao.coerceIn(0.0, 1.0).toFloat()).fillMaxHeight().clip(RoundedCornerShape(4.dp)).background(cor))
        if (ritmo != null && ritmo > 0 && ritmo < 1) {
            Row(Modifier.fillMaxWidth()) {
                Spacer(Modifier.fillMaxWidth(ritmo.toFloat()))
                Box(Modifier.width(2.dp).height(altura).background(cores.texto.copy(alpha = 0.55f)))
            }
        }
    }
}

@Composable
fun Bolinha(cor: Color, tamanho: Dp = 9.dp) = Box(Modifier.size(tamanho).clip(CircleShape).background(cor))

@Composable
fun Vazio(texto: String) = Text(texto, color = cores.mudo, fontSize = 13.sp, modifier = Modifier.padding(vertical = 6.dp))

@Composable
fun EstadoCarga(c: Carga<*>) {
    if (c.erro != null) Text(c.erro ?: "", color = cores.ruim, modifier = Modifier.padding(16.dp))
    else if (c.dado == null) Text("Carregando...", color = cores.mudo, modifier = Modifier.padding(16.dp))
}

/** Segmentos (Semana | Mês | Ano), como os botões agrupados do site. */
@Composable
fun Segmentos(opcoes: List<Pair<String, String>>, atual: String, modifier: Modifier = Modifier, aoEscolher: (String) -> Unit) {
    Row(modifier.clip(RoundedCornerShape(10.dp)).background(cores.trilho).padding(3.dp)) {
        opcoes.forEach { (k, nome) ->
            val on = k == atual
            Box(Modifier.weight(1f).clip(RoundedCornerShape(8.dp)).background(if (on) cores.painel else Color.Transparent)
                .clickable { aoEscolher(k) }.padding(vertical = 8.dp), contentAlignment = Alignment.Center) {
                Text(nome, color = if (on) cores.texto else cores.texto2, fontSize = if (opcoes.size > 3) 12.sp else 13.sp, maxLines = 1,
                    overflow = TextOverflow.Ellipsis, fontWeight = if (on) FontWeight.SemiBold else FontWeight.Normal)
            }
        }
    }
}

/** Chip do site: toque escolhe. `primario` é o azul (a sugestão). */
@Composable
fun Ficha(texto: String, primario: Boolean = false, ativo: Boolean = false, modifier: Modifier = Modifier, aoTocar: () -> Unit) {
    val fundo = when { primario -> cores.acento; ativo -> cores.acentoSuave; else -> cores.painel }
    val cor = when { primario -> Color.White; ativo -> cores.acento; else -> cores.texto }
    Box(modifier.clip(RoundedCornerShape(18.dp)).background(fundo).border(1.dp, if (primario) cores.acento else cores.linha, RoundedCornerShape(18.dp))
        .clickable(onClick = aoTocar).padding(horizontal = 12.dp, vertical = 7.dp)) {
        Text(texto, color = cor, fontSize = 13.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
    }
}

@Composable
fun Fichas(conteudo: @Composable RowScope.() -> Unit) =
    Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(6.dp), content = conteudo)

@Composable
fun BotaoPrimario(texto: String, modifier: Modifier = Modifier, habilitado: Boolean = true, aoTocar: () -> Unit) =
    Button(onClick = aoTocar, enabled = habilitado, modifier = modifier, shape = RoundedCornerShape(10.dp),
        colors = ButtonDefaults.buttonColors(containerColor = cores.acento, contentColor = Color.White)) { Text(texto) }

@Composable
fun BotaoSecundario(texto: String, modifier: Modifier = Modifier, aoTocar: () -> Unit) =
    OutlinedButton(onClick = aoTocar, modifier = modifier, shape = RoundedCornerShape(10.dp), border = BorderStroke(1.dp, cores.linha)) {
        Text(texto, color = cores.texto)
    }

@Composable
fun Campo(valor: String, aoMudar: (String) -> Unit, rotulo: String, modifier: Modifier = Modifier, numerico: Boolean = false,
          dica: String? = null, linhas: Int = 1) {
    OutlinedTextField(value = valor, onValueChange = aoMudar, label = { Text(rotulo) }, modifier = modifier.fillMaxWidth(),
        singleLine = linhas == 1, minLines = linhas, placeholder = dica?.let { { Text(it, color = cores.mudo) } },
        keyboardOptions = if (numerico) KeyboardOptions(keyboardType = KeyboardType.Decimal) else KeyboardOptions.Default,
        colors = OutlinedTextFieldDefaults.colors(focusedBorderColor = cores.acento, unfocusedBorderColor = cores.linha,
            focusedTextColor = cores.texto, unfocusedTextColor = cores.texto))
}

/** Um campo que mostra o escolhido e abre a escolha ao toque (lista suspensa, lista com busca, data). */
@Composable
fun CampoToque(rotulo: String, texto: String?, modifier: Modifier = Modifier, aoTocar: () -> Unit) {
    Column(modifier.fillMaxWidth().clip(RoundedCornerShape(6.dp)).border(1.dp, cores.linha, RoundedCornerShape(6.dp))
        .clickable(onClick = aoTocar).padding(horizontal = 14.dp, vertical = 8.dp)) {
        Text(rotulo, color = cores.mudo, fontSize = 11.sp)
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(texto ?: "escolha...", color = if (texto == null) cores.mudo else cores.texto, fontSize = 15.sp,
                modifier = Modifier.weight(1f), maxLines = 1, overflow = TextOverflow.Ellipsis)
            Text("▾", color = cores.mudo)
        }
    }
}

/** Lista suspensa: um campo que abre o menu de opções (valor -> rótulo). */
@Composable
fun Seletor(rotulo: String, opcoes: List<Pair<String, String>>, valor: String?, modifier: Modifier = Modifier, aoEscolher: (String) -> Unit) {
    var aberto by remember { mutableStateOf(false) }
    Box(modifier.fillMaxWidth()) {
        CampoToque(rotulo, opcoes.firstOrNull { it.first == valor }?.second) { aberto = true }
        DropdownMenu(expanded = aberto, onDismissRequest = { aberto = false }, modifier = Modifier.heightIn(max = 420.dp)) {
            opcoes.forEach { (k, nome) -> DropdownMenuItem(text = { Text(nome) }, onClick = { aberto = false; aoEscolher(k) }) }
        }
    }
}

/** Categoria de gasto ou de renda, escolhida numa lista com busca ("Grupo: Categoria", como no site). */
@Composable
fun SeletorCategoria(tipo: String, valor: String?, modifier: Modifier = Modifier, rotulo: String = "Categoria", aoEscolher: (String) -> Unit) {
    var aberto by remember { mutableStateOf(false) }
    CampoToque(rotulo, Vocab.categoria(valor)?.let { "${it.s("grupo")}: ${it.s("nome")}" }, modifier) { aberto = true }
    if (aberto) EscolherDaLista(rotulo, Vocab.categorias.filter { it.s("tipo") == tipo }.map { it.s("id") to "${it.s("grupo")}: ${it.s("nome")}" },
        { aberto = false }, aoEscolher)
}

@Composable
fun Marcar(texto: String, marcado: Boolean, aoMudar: (Boolean) -> Unit) {
    Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.clickable { aoMudar(!marcado) }) {
        Checkbox(checked = marcado, onCheckedChange = aoMudar, colors = CheckboxDefaults.colors(checkedColor = cores.acento))
        Text(texto, color = cores.texto, fontSize = 14.sp)
    }
}

@Composable
fun Divisor() = HorizontalDivider(color = cores.linha, thickness = 1.dp)

/** Texto com trechos **em negrito** (os textos de ajuda e do tour). */
fun negrito(texto: String): AnnotatedString = buildAnnotatedString {
    texto.split("**").forEachIndexed { i, pedaco -> if (i % 2 == 1) withStyle(SpanStyle(fontWeight = FontWeight.Bold)) { append(pedaco) } else append(pedaco) }
}

@Composable
fun Confirmar(titulo: String, texto: String, sim: String = "Confirmar", aoFechar: () -> Unit, aoConfirmar: () -> Unit) {
    AlertDialog(onDismissRequest = aoFechar, title = { Text(titulo) }, text = { Text(texto) },
        confirmButton = { TextButton(onClick = { aoFechar(); aoConfirmar() }) { Text(sim, color = cores.acento) } },
        dismissButton = { TextButton(onClick = aoFechar) { Text("Cancelar", color = cores.texto2) } }, containerColor = cores.painel)
}

/** Escolher um item de uma lista longa, com busca (categorias, pessoas). */
@Composable
fun EscolherDaLista(titulo: String, itens: List<Pair<String, String>>, aoFechar: () -> Unit, aoEscolher: (String) -> Unit) {
    var busca by remember { mutableStateOf("") }
    AlertDialog(onDismissRequest = aoFechar, title = { Text(titulo) }, containerColor = cores.painel, confirmButton = {},
        dismissButton = { TextButton(onClick = aoFechar) { Text("Fechar", color = cores.texto2) } },
        text = {
            Column {
                Campo(busca, { busca = it }, "Buscar")
                LazyColumn(Modifier.heightIn(max = 380.dp).padding(top = 6.dp)) {
                    items(itens.filter { it.second.contains(busca, ignoreCase = true) }) { (k, nome) ->
                        Text(nome, color = cores.texto, modifier = Modifier.fillMaxWidth().clickable { aoFechar(); aoEscolher(k) }.padding(vertical = 10.dp))
                    }
                }
            }
        })
}

@Composable
fun Titulo(texto: String, detalhe: String? = null) {
    Row(Modifier.fillMaxWidth().padding(top = 4.dp, bottom = 2.dp), verticalAlignment = Alignment.Bottom) {
        Text(texto, color = cores.texto, fontSize = 22.sp, fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f, fill = false))
        if (detalhe != null) Text("  $detalhe", color = cores.mudo, fontSize = 13.sp, modifier = Modifier.widthIn(max = 220.dp), maxLines = 1,
            overflow = TextOverflow.Ellipsis)
    }
}
