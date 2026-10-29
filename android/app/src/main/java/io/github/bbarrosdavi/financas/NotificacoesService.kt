package io.github.bbarrosdavi.financas

import android.app.Notification
import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification
import android.util.Log
import java.util.concurrent.Executors

/**
 * Notificação de um app de banco escolhido em Ajustes vira lançamento no banco do aparelho na hora, na ordem em
 * que chegou, pelo mesmo leitor do servidor (app/push_parser.py). Não espera servidor nenhum: a sincronização
 * leva depois.
 */
class NotificacoesService : NotificationListenerService() {
    private val fila = Executors.newSingleThreadExecutor()

    override fun onNotificationPosted(sbn: StatusBarNotification) {
        if (sbn.packageName !in Ajustes(this).apps) return
        val n = sbn.notification ?: return
        if (n.flags and Notification.FLAG_GROUP_SUMMARY != 0) return
        val extras = n.extras
        val titulo = extras.getCharSequence(Notification.EXTRA_TITLE)?.toString().orEmpty()
        val texto = (extras.getCharSequence(Notification.EXTRA_BIG_TEXT) ?: extras.getCharSequence(Notification.EXTRA_TEXT))
            ?.toString().orEmpty()
        if (titulo.isBlank() && texto.isBlank()) return
        val pacote = sbn.packageName
        val quando = sbn.postTime
        fila.execute {
            try {
                val r = Backend.notificacao(applicationContext, pacote, titulo, texto, quando)
                Log.i(TAG, "push de $pacote: $r")
                MainActivity.atualizarTela()
                Sincronizacao.agora(applicationContext)
            } catch (e: Exception) {
                Log.e(TAG, "push de $pacote não aplicado", e)
            }
        }
    }

    companion object { const val TAG = "Financas" }
}
