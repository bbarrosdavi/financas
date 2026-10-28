package io.github.bbarrosdavi.financas

import android.content.ComponentName
import android.content.Context
import android.provider.Settings

/** Ajustes deste aparelho (SharedPreferences): servidor, chave, apps monitorados, tema, tour e a última sincronização. */
class Ajustes(private val ctx: Context) {
    private val p = ctx.getSharedPreferences("ajustes", Context.MODE_PRIVATE)

    var url: String
        get() = p.getString("url", "") ?: ""
        set(v) = p.edit().putString("url", v.trim().trimEnd('/')).apply()

    var chave: String
        get() = p.getString("chave", "") ?: ""
        set(v) = p.edit().putString("chave", v.trim().removePrefix("Bearer ").trim()).apply()

    var apps: Set<String>
        get() = p.getStringSet("apps", null) ?: APPS_PADRAO.keys
        set(v) = p.edit().putStringSet("apps", v).apply()

    /** "sistema", "claro" ou "escuro". */
    var tema: String
        get() = p.getString("tema", "sistema") ?: "sistema"
        set(v) = p.edit().putString("tema", v).apply()

    var tourVisto: Boolean
        get() = p.getBoolean("tour_visto", false)
        set(v) = p.edit().putBoolean("tour_visto", v).apply()

    var ultimaSincronia: String
        get() = p.getString("ultima", "") ?: ""
        set(v) = p.edit().putString("ultima", v).apply()

    fun acessoNotificacoes(): Boolean {
        val ativos = Settings.Secure.getString(ctx.contentResolver, "enabled_notification_listeners") ?: return false
        val eu = ComponentName(ctx, NotificacoesService::class.java)
        return ativos.split(':').any { ComponentName.unflattenFromString(it) == eu }
    }

    companion object {
        val APPS_PADRAO = linkedMapOf(
            "com.nu.production" to "Nubank",
            "com.picpay" to "PicPay",
            "com.mercadopago.wallet" to "Mercado Pago",
            "com.bradesco" to "Bradesco",
        )
    }
}
