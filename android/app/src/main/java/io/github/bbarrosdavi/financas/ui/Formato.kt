package io.github.bbarrosdavi.financas.ui

import java.text.DecimalFormat
import java.text.DecimalFormatSymbols
import java.time.LocalDate
import java.time.format.DateTimeFormatter
import java.time.temporal.IsoFields
import java.util.Locale
import kotlin.math.abs

private val ptBR = Locale.forLanguageTag("pt-BR")
private val dois = DecimalFormat("#,##0.00", DecimalFormatSymbols(ptBR))

/** Como no site: R$ 1.234,56, sempre com os centavos, e o sinal na frente quando negativo. */
fun brl(v: Double) = (if (v < 0) "-" else "") + "R$ " + dois.format(abs(v))
fun sinal(v: Double) = (if (v > 0) "+" else if (v < 0) "-" else "") + brl(abs(v))

val MESES = listOf("janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro")
fun mesCurto(aaaamm: String) = MESES[aaaamm.substring(5, 7).toInt() - 1].take(3) + "/" + aaaamm.substring(2, 4)
fun mesLongo(aaaamm: String) = MESES[aaaamm.substring(5, 7).toInt() - 1] + " de " + aaaamm.take(4)
fun dataBR(iso: String) = if (iso.length >= 10) "${iso.substring(8, 10)}/${iso.substring(5, 7)}/${iso.take(4)}" else iso
fun dataCurta(iso: String) = if (iso.length >= 10) "${iso.substring(8, 10)}/${iso.substring(5, 7)}" else iso
fun hojeISO(): String = LocalDate.now().toString()

/** Número digitado em pt-BR ("1.234,56" ou "12,5") ou com ponto ("12.5"). */
fun numero(texto: String): Double? {
    val t = texto.trim().replace("R$", "").replace(" ", "")
    if (t.isEmpty()) return null
    val normal = if (t.contains(',')) t.replace(".", "").replace(',', '.') else t
    return normal.toDoubleOrNull()
}

fun semanaISO(d: LocalDate) = "%d-W%02d".format(d.get(IsoFields.WEEK_BASED_YEAR), d.get(IsoFields.WEEK_OF_WEEK_BASED_YEAR))

/** O período do mesmo tipo que contém a data de referência (o "trocarTipo" do site). */
fun periodoDo(tipo: String, ref: LocalDate) = when (tipo) {
    "ano" -> ref.year.toString()
    "semana" -> semanaISO(ref)
    else -> ref.toString().take(7)
}

fun rotuloPeriodo(tipo: String, periodo: String, inicio: String, fim: String) = when (tipo) {
    "ano" -> periodo
    "semana" -> "semana de ${dataCurta(inicio)} a ${dataCurta(fim)}"
    else -> mesLongo(periodo)
}

val dataLonga: DateTimeFormatter = DateTimeFormatter.ofPattern("dd/MM/yyyy")
