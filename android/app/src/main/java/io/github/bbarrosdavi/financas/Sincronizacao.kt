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

    class Trabalho(ctx: Context, params: WorkerParameters) : Worker(ctx, params) {
        override fun doWork(): Result {
            rodar(applicationContext)
            return Result.success()
        }
    }
}
