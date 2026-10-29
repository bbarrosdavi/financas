package io.github.bbarrosdavi.financas.ui

import android.os.Build
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.blur
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.Density
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/** As cores do site, para o tema e o modo (claro ou escuro) em uso. */
@Immutable
data class Cores(
    val fundo: Color, val painel: Color, val painelForte: Color, val linha: Color, val texto: Color, val texto2: Color,
    val mudo: Color, val trilho: Color, val acento: Color, val acentoSuave: Color, val s1: Color, val s2: Color, val s3: Color,
    val ok: Color, val atencao: Color, val ruim: Color, val veu: Color, val escuro: Boolean,
)

// As paletas do site (frontend/src/lib/paletas.ts do Apê em Dia): fundo, papel dos painéis, texto, mudo, texto
// secundário, acento e, quando o tema tem, a borda dos painéis.
private class Modo(val bg: Long, val papel: Long, val tinta: Long, val mudo: Long, val sutil: Long, val acento: Long, val borda: Color? = null)
private class Paleta(val claro: Modo, val escuro: Modo)

private val PALETAS = mapOf(
    "vidro" to Paleta(Modo(0xFFE9EBEF, 0xFFFFFFFF, 0xFF15151A, 0xFF7B7A82, 0xFF46454D, 0xFF2A78D6),
        Modo(0xFF101014, 0xFF18181E, 0xFFF0EFEC, 0xFF8D8C84, 0xFFC3C2B7, 0xFF3987E5)),
    "salvia" to Paleta(Modo(0xFFF8F9F5, 0xFFFFFFFF, 0xFF303A32, 0xFF8B9086, 0xFF66755B, 0xFF526A42),
        Modo(0xFF151A14, 0xFF1E241C, 0xFFE8EDE1, 0xFFA3AD98, 0xFFC4CFB8, 0xFFB3C894)),
    "cafe" to Paleta(Modo(0xFFF7F1EA, 0xFFFFFCF7, 0xFF3B2A1E, 0xFF8A7462, 0xFF6E5442, 0xFF8A5A36),
        Modo(0xFF1B1410, 0xFF2B241E, 0xFFF1E6D7, 0xFFBAA58F, 0xFFD3B99E, 0xFFD3A97F)),
    "areia" to Paleta(Modo(0xFFFBF7EC, 0xFFFFFDF6, 0xFF4D4431, 0xFF87795C, 0xFF77633F, 0xFF88652E),
        Modo(0xFF1C1912, 0xFF282319, 0xFFF2EAD6, 0xFFB3A585, 0xFFD6C7A3, 0xFFD9B77A)),
    "oceano" to Paleta(Modo(0xFFF0F6F9, 0xFFFFFFFF, 0xFF283F4B, 0xFF687F8B, 0xFF4D7487, 0xFF346F87),
        Modo(0xFF111A1F, 0xFF18242B, 0xFFE3EEF3, 0xFF93AAB5, 0xFFB7CCD6, 0xFF7FBCD4)),
    "lavanda" to Paleta(Modo(0xFFF7F3FA, 0xFFFFFFFF, 0xFF46374F, 0xFF85718E, 0xFF806393, 0xFF7B5B96),
        Modo(0xFF18141C, 0xFF241D2A, 0xFFEFE6F5, 0xFFAD9CB8, 0xFFCDBAD9, 0xFFC3A6DB)),
    "noite" to Paleta(Modo(0xFFEEF1F5, 0xFFFFFFFF, 0xFF1F2733, 0xFF6B7685, 0xFF4A5566, 0xFF4F6B2F),
        Modo(0xFF171C24, 0xFF222A35, 0xFFE6EAF0, 0xFFA4B0C1, 0xFFC4CFDD, 0xFFB3C894)),
    "neotribal" to Paleta(Modo(0xFFF6F0F8, 0xFFFFFFFF, 0xFF2A1030, 0xFF7E6A86, 0xFF6B2F78, 0xFFA21CAF, Color(0x40C026D3)),
        Modo(0xFF070709, 0xFF0C0C11, 0xFFF5F5F7, 0xFF9494A8, 0xFFD8B4FE, 0xFFC026D3, Color(0x59C026D3))),
)

/** As cores de um tema. No estilo Vidro o painel é translúcido (82% no claro, 80% no escuro, como no site). */
fun coresDe(tema: String, escuro: Boolean, estilo: String = "vidro"): Cores {
    val m = (PALETAS[tema] ?: PALETAS.getValue("vidro")).let { if (escuro) it.escuro else it.claro }
    val papel = Color(m.papel)
    val acento = Color(m.acento)
    return Cores(
        fundo = Color(m.bg), painel = papel.copy(alpha = if (estilo == "vidro") (if (escuro) 0.80f else 0.82f) else 1f),
        painelForte = papel.copy(alpha = if (escuro) 0.95f else 0.94f),
        linha = m.borda ?: if (escuro) Color(0x14FFFFFF) else Color(0x1414141E),
        texto = Color(m.tinta), texto2 = Color(m.sutil), mudo = Color(m.mudo),
        trilho = if (escuro) Color(0x14FFFFFF) else Color(0x1214141E),
        acento = acento, acentoSuave = acento.copy(alpha = if (escuro) 0.18f else 0.12f), s1 = acento,
        s2 = if (escuro) Color(0xFFD95926) else Color(0xFFEB6834), s3 = if (escuro) Color(0xFF2BB7B3) else Color(0xFF0F9D9A),
        ok = if (escuro) Color(0xFF1BAF7A) else Color(0xFF13805A), atencao = if (escuro) Color(0xFFC98500) else Color(0xFFA86F00),
        ruim = if (escuro) Color(0xFFE66767) else Color(0xFFC93A39),
        // o véu sobre o papel de parede, como no site
        veu = if (escuro) Color(0x5908080C) else Color(0x4DECEDF1), escuro = escuro,
    )
}

/**
 * A aparência em uso: a da conta no servidor (trazida pela sincronização) ou, sem ela, a escolhida neste
 * aparelho. `modo` é "claro", "escuro" ou "sistema".
 */
@Immutable
data class Aparencia(
    val tema: String = "vidro", val modo: String = "sistema", val desfoque: Boolean = false, val estilo: String = "vidro",
    val papel: ImageBitmap? = null, val daConta: Boolean = false,
)

val LocalCores = staticCompositionLocalOf { coresDe("vidro", false) }
val LocalAparencia = staticCompositionLocalOf { Aparencia() }
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
fun FinancasTema(ap: Aparencia, conteudo: @Composable () -> Unit) {
    val escuro = when (ap.modo) { "escuro" -> true; "claro" -> false; else -> isSystemInDarkTheme() }
    val c = coresDe(ap.tema, escuro, ap.estilo)
    val esquema = if (escuro) darkColorScheme(primary = c.acento, background = c.fundo, surface = c.painelForte, onSurface = c.texto,
        onBackground = c.texto, surfaceVariant = c.painelForte, outline = c.linha)
    else lightColorScheme(primary = c.acento, background = c.fundo, surface = c.painelForte, onSurface = c.texto,
        onBackground = c.texto, surfaceVariant = c.painelForte, outline = c.linha)
    // A densidade do site: corpo em 13, detalhe em 11 a 12, títulos curtos.
    val base = Typography()
    val tnum = TextStyle(fontFeatureSettings = "tnum")
    val tipos = Typography(
        bodyLarge = base.bodyLarge.merge(tnum).copy(fontSize = 14.sp, lineHeight = 19.sp),
        bodyMedium = base.bodyMedium.merge(tnum).copy(fontSize = 13.sp, lineHeight = 18.sp),
        bodySmall = base.bodySmall.merge(tnum).copy(fontSize = 11.sp, lineHeight = 15.sp),
        titleLarge = base.titleLarge.copy(fontSize = 17.sp, lineHeight = 22.sp, fontWeight = FontWeight.Bold),
        titleMedium = base.titleMedium.copy(fontSize = 15.sp, lineHeight = 20.sp, fontWeight = FontWeight.SemiBold),
        labelLarge = base.labelLarge.copy(fontSize = 13.sp, fontWeight = FontWeight.SemiBold),
        labelMedium = base.labelMedium.copy(fontSize = 12.sp), labelSmall = base.labelSmall.copy(fontSize = 10.sp),
    )
    // O texto não cresce com a fonte do sistema (o site também não): o app fica tão denso quanto o site.
    val d = LocalDensity.current
    CompositionLocalProvider(LocalCores provides c, LocalAparencia provides ap,
        LocalDensity provides Density(d.density, fontScale = minOf(d.fontScale, 1f))) {
        MaterialTheme(colorScheme = esquema, typography = tipos, content = conteudo)
    }
}

/** O fundo do site: a cor do tema e, se houver, o papel de parede com o véu do modo (e desfoque, se a conta usa). */
@Composable
fun FundoDoApp(conteudo: @Composable () -> Unit) {
    val ap = LocalAparencia.current
    Box(Modifier.fillMaxSize().background(cores.fundo)) {
        ap.papel?.let { img ->
            val borrar = ap.desfoque && Build.VERSION.SDK_INT >= Build.VERSION_CODES.S
            Image(img, null, Modifier.fillMaxSize().then(if (borrar) Modifier.blur(18.dp) else Modifier), contentScale = ContentScale.Crop)
            Box(Modifier.fillMaxSize().background(cores.veu))
        }
        conteudo()
    }
}
