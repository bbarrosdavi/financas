package io.github.bbarrosdavi.financas.ui

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp

/** As cores do site (web/style.css), no claro e no escuro. */
@Immutable
data class Cores(
    val fundo: Color, val painel: Color, val linha: Color, val texto: Color, val texto2: Color, val mudo: Color,
    val trilho: Color, val acento: Color, val acentoSuave: Color, val s1: Color, val s2: Color, val s3: Color,
    val ok: Color, val atencao: Color, val ruim: Color, val escuro: Boolean,
)

val CoresClaras = Cores(
    fundo = Color(0xFFE9EBEF), painel = Color(0xFFFFFFFF), linha = Color(0x1414141E), texto = Color(0xFF15151A),
    texto2 = Color(0xFF46454D), mudo = Color(0xFF7B7A82), trilho = Color(0x1214141E), acento = Color(0xFF2A78D6),
    acentoSuave = Color(0x1F2A78D6), s1 = Color(0xFF2A78D6), s2 = Color(0xFFEB6834), s3 = Color(0xFF0F9D9A),
    ok = Color(0xFF13805A), atencao = Color(0xFFA86F00), ruim = Color(0xFFC93A39), escuro = false,
)

val CoresEscuras = Cores(
    fundo = Color(0xFF101014), painel = Color(0xFF1C1C22), linha = Color(0x14FFFFFF), texto = Color(0xFFF0EFEC),
    texto2 = Color(0xFFC3C2B7), mudo = Color(0xFF8D8C84), trilho = Color(0x14FFFFFF), acento = Color(0xFF3987E5),
    acentoSuave = Color(0x2E3987E5), s1 = Color(0xFF3987E5), s2 = Color(0xFFD95926), s3 = Color(0xFF2BB7B3),
    ok = Color(0xFF1BAF7A), atencao = Color(0xFFC98500), ruim = Color(0xFFE66767), escuro = true,
)

val LocalCores = staticCompositionLocalOf { CoresClaras }
val cores: Cores @Composable get() = LocalCores.current

// Cor fixa por grupo, como no site (a cor segue o grupo, nunca a posição). Grupo fora da lista fica cinza.
private val COR_GRUPO = mapOf(
    "Moradia" to Color(0xFF2A78D6), "Alimentação" to Color(0xFFEB6834), "Saúde" to Color(0xFF1BAF7A),
    "Transporte" to Color(0xFFEDA100), "Lazer" to Color(0xFFE87BA4), "Compras" to Color(0xFF6250D6), "Assinaturas" to Color(0xFF008300),
)

fun corHex(hex: String?): Color? = runCatching { hex?.takeIf { it.startsWith("#") && it.length == 7 }?.let { Color(android.graphics.Color.parseColor(it)) } }.getOrNull()
fun corGrupo(grupo: String?): Color = corHex(Vocab.coresGrupos[grupo]) ?: COR_GRUPO[grupo] ?: Color(0xFF9A99A1)
fun corCategoria(id: String?): Color = Vocab.categoria(id)?.let { corHex(it.s("cor")) ?: corGrupo(it.s("grupo")) } ?: Color(0xFF9A99A1)

@Composable
fun FinancasTema(tema: String, conteudo: @Composable () -> Unit) {
    val escuro = when (tema) { "escuro" -> true; "claro" -> false; else -> isSystemInDarkTheme() }
    val c = if (escuro) CoresEscuras else CoresClaras
    val esquema = if (escuro) darkColorScheme(primary = c.acento, background = c.fundo, surface = c.painel, onSurface = c.texto,
        onBackground = c.texto, surfaceVariant = c.painel, outline = c.linha)
    else lightColorScheme(primary = c.acento, background = c.fundo, surface = c.painel, onSurface = c.texto,
        onBackground = c.texto, surfaceVariant = c.painel, outline = c.linha)
    val base = Typography()
    val tnum = TextStyle(fontFeatureSettings = "tnum")
    val tipos = Typography(
        bodyLarge = base.bodyLarge.merge(tnum).copy(fontSize = 15.sp), bodyMedium = base.bodyMedium.merge(tnum).copy(fontSize = 14.sp),
        bodySmall = base.bodySmall.merge(tnum).copy(fontSize = 12.sp), titleMedium = base.titleMedium.copy(fontWeight = FontWeight.SemiBold),
        labelLarge = base.labelLarge.copy(fontWeight = FontWeight.SemiBold),
    )
    CompositionLocalProvider(LocalCores provides c) {
        MaterialTheme(colorScheme = esquema, typography = tipos, content = conteudo)
    }
}
