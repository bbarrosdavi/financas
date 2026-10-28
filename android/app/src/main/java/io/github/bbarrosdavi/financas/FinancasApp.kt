package io.github.bbarrosdavi.financas

import android.app.Application
import kotlin.concurrent.thread

class FinancasApp : Application() {
    override fun onCreate() {
        super.onCreate()
        // O Python leva um ou dois segundos para subir: começa já, longe da tela.
        thread(name = "financas-inicio") { Backend.modulo(this) }
        Sincronizacao.periodica(this)
    }
}
