package io.github.bbarrosdavi.financas

import android.content.Context
import com.chaquo.python.PyObject
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import java.io.File
import java.util.TimeZone

/**
 * O Finanças do servidor (a pasta app/ do repositório) rodando neste aparelho, pelo Chaquopy.
 * Ver src/main/python/financas_local.py. O banco fica em files/financas/financas.db.
 */
object Backend {
    @Volatile private var modulo: PyObject? = null

    fun modulo(ctx: Context): PyObject = modulo ?: synchronized(this) {
        modulo ?: run {
            if (!Python.isStarted()) Python.start(AndroidPlatform(ctx.applicationContext))
            val m = Python.getInstance().getModule("financas_local")
            m.callAttr("iniciar", File(ctx.filesDir, "financas").absolutePath, TimeZone.getDefault().id)
            modulo = m
            m
        }
    }

    /** Uma chamada da tela à API: devolve {status, cabecalhos, corpo (base64)}. */
    fun pedir(ctx: Context, metodo: String, caminho: String, tipo: String = "", corpoB64: String = ""): String =
        modulo(ctx).callAttr("pedir", metodo, caminho, tipo, corpoB64).toString()

    /** O push do banco vira lançamento local agora, como faria o webhook do servidor. */
    fun notificacao(ctx: Context, pacote: String, titulo: String, texto: String, quandoMs: Long): String =
        modulo(ctx).callAttr("notificacao", pacote, titulo, texto, quandoMs).toString()

    fun sincronizar(ctx: Context, url: String, chave: String): String =
        modulo(ctx).callAttr("sincronizar", url, chave).toString()
}
