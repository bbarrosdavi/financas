package io.github.bbarrosdavi.financas

import android.content.Context
import androidx.work.Constraints
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.Worker
import androidx.work.WorkerParameters
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.TimeUnit

/**
 * Sincronização em segundo plano (WorkManager): a cada 15 minutos com rede, ao abrir e ao sair do app e depois
 * de cada push. Sem servidor ao alcance, só anota o erro: o app continua igual, e a próxima tentativa leva tudo.
 */
object Sincronizacao {
    private val comRede = Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build()

    fun periodica(ctx: Context) {
        WorkManager.getInstance(ctx).enqueueUniquePeriodicWork(
            "sincronizar", ExistingPeriodicWorkPolicy.KEEP,
            PeriodicWorkRequestBuilder<Trabalho>(15, TimeUnit.MINUTES).setConstraints(comRede).build())
    }

    fun agora(ctx: Context) {
        WorkManager.getInstance(ctx).enqueueUniqueWork(
            "sincronizar-agora", ExistingWorkPolicy.REPLACE,
            OneTimeWorkRequestBuilder<Trabalho>().setConstraints(comRede).build())
    }

    /** Uma troca com o servidor; anota o resultado para a tela de Ajustes. */
    fun rodar(ctx: Context): JSONObject {
        val a = Ajustes(ctx)
        if (a.url.isBlank() || a.chave.isBlank()) return JSONObject().put("ok", false).put("erro", "Servidor ou chave não configurados.")
        val r = JSONObject(Backend.sincronizar(ctx, a.url, a.chave)).put("quando", System.currentTimeMillis())
        a.ultimaSincronia = r.toString()
        if (r.optBoolean("ok") && r.optInt("recebidas") > 0) MainActivity.atualizarTela()
        return r
    }

    /** /health diz se o servidor está ao alcance; uma troca vazia (cursor no fim) diz se a chave vale, sem mudar nada. */
    fun testar(endereco: String, chaveDigitada: String): Pair<Boolean, String> {
        val url = endereco.trim().trimEnd('/')
        val chave = chaveDigitada.trim().removePrefix("Bearer ").trim()
        if (!url.startsWith("http://") && !url.startsWith("https://"))
            return false to "O endereço começa com http://, por exemplo http://192.168.0.10:8095"
        return try {
            val saude = (URL("$url/health").openConnection() as HttpURLConnection).apply { connectTimeout = 5000; readTimeout = 5000 }
            if (saude.responseCode != 200) return false to "O endereço respondeu ${saude.responseCode}: não parece o Avareza."
            val troca = (URL("$url/api/v1/sync").openConnection() as HttpURLConnection).apply {
                connectTimeout = 5000; readTimeout = 10000; requestMethod = "POST"; doOutput = true
                setRequestProperty("Content-Type", "application/json")
                setRequestProperty("Authorization", "Bearer $chave")
            }
            troca.outputStream.use { it.write("""{"protocolo":1,"cursor":4000000000000000000,"mudancas":[]}""".toByteArray()) }
            when (troca.responseCode) {
                200 -> true to "Conectado, e a chave foi aceita."
                401 -> false to "O servidor respondeu, mas recusou a chave."
                404 -> true to "Conectado. Servidor de versão antiga: só os pushes vão, pelo webhook."
                else -> false to "O servidor respondeu ${troca.responseCode} à sincronização."
            }
        } catch (e: Exception) {
            false to "Sem resposta de $url (${e.javaClass.simpleName}). Mesma rede ou VPN ligada?"
        }
    }

    class Trabalho(ctx: Context, params: WorkerParameters) : Worker(ctx, params) {
        override fun doWork(): Result {
            rodar(applicationContext)
            return Result.success()
        }
    }
}
