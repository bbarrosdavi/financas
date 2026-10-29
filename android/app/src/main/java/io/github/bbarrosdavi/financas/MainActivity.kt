package io.github.bbarrosdavi.financas

import android.graphics.BitmapFactory
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.graphics.asImageBitmap
import androidx.core.view.WindowCompat
import androidx.lifecycle.lifecycleScope
import io.github.bbarrosdavi.financas.ui.Api
import io.github.bbarrosdavi.financas.ui.Aparencia
import io.github.bbarrosdavi.financas.ui.AppFinancas
import io.github.bbarrosdavi.financas.ui.Estado
import io.github.bbarrosdavi.financas.ui.FinancasTema
import io.github.bbarrosdavi.financas.ui.Vocab
import io.github.bbarrosdavi.financas.ui.cores
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.lang.ref.WeakReference

/**
 * As telas nativas (pacote ui, em Jetpack Compose) sobre a mesma API do site, servida pelo Python que roda no
 * aparelho (Backend). Nada aqui depende de rede.
 */
class MainActivity : ComponentActivity() {
    private lateinit var ajustes: Ajustes
    private var tema by mutableStateOf("sistema")
    private var aparencia by mutableStateOf(Aparencia())

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        Api.ctx = applicationContext
        ajustes = Ajustes(this)
        tema = ajustes.tema
        aparencia = Aparencia(tema = "lavanda", modo = tema)
        setContent {
            FinancasTema(aparencia) {
                val escuro = cores.escuro
                LaunchedEffect(escuro) {
                    WindowCompat.getInsetsController(window, window.decorView).apply {
                        isAppearanceLightStatusBars = !escuro
                        isAppearanceLightNavigationBars = !escuro
                    }
                }
                AppFinancas(ajustes, tema, aoTrocarTema = { tema = it; ajustes.tema = it; aparencia = aparencia.copy(modo = it) },
                    aoSair = { finish() })
            }
        }
        atual = WeakReference(this)
    }

    override fun onResume() {
        super.onResume()
        atual = WeakReference(this)
        recarregar()                         // o que chegou pelo push enquanto o app estava fechado
        Sincronizacao.agora(this)
    }

    override fun onStop() {
        super.onStop()
        Sincronizacao.agora(this)            // o que foi classificado aqui vai logo para o servidor
    }

    private fun recarregar() {
        lifecycleScope.launch {
            runCatching { Vocab.carregar() }; Estado.mudou()
            runCatching { lerAparencia() }.onSuccess { aparencia = it }
        }
    }

    /**
     * A aparência da conta no servidor (tema, claro ou escuro, desfoque, estilo e papel de parede), trazida pela
     * sincronização. Sem servidor, vale o modo escolhido aqui e o papel de parede deste aparelho.
     */
    private suspend fun lerAparencia(): Aparencia {
        val conta = Api.obj("/api/aparencia-conta")
        val v = conta.optJSONObject("valores") ?: JSONObject()
        val nomePapel = conta.optString("papel").ifEmpty { Api.obj("/api/papeis").optString("atual") }
        val papel = nomePapel.takeIf { it.isNotEmpty() }?.let { nome ->
            runCatching {
                withContext(Dispatchers.Default) {
                    // O papel padrão vem no APK; os outros, da pasta de papéis (os do servidor chegam pela sincronização).
                    if (nome == "papel-padrao.jpg" && runCatching { Api.bytes("/papel/$nome") }.isFailure)
                        BitmapFactory.decodeResource(resources, R.drawable.papel_padrao)?.asImageBitmap()
                    else Api.bytes("/papel/" + Api.q(nome).replace("+", "%20")).let { BitmapFactory.decodeByteArray(it, 0, it.size)?.asImageBitmap() }
                }
            }.getOrNull()
        }
        if (v.length() == 0) return Aparencia(tema = "lavanda", modo = tema, papel = papel)
        // Os padrões são os do site: escuro, Goth Neotribal, sem desfoque.
        val prefs = runCatching { JSONObject(v.optString("prefs", "{}")) }.getOrDefault(JSONObject())
        return Aparencia(tema = v.optString("ape-em-dia-theme", "lavanda"), modo = if (v.optString("tema") == "light") "claro" else "escuro",
            desfoque = v.optString("desfoque") == "com", estilo = prefs.optString("estilo", "vidro"), papel = papel, daConta = true)
    }

    companion object {
        @Volatile private var atual: WeakReference<MainActivity>? = null

        /** Chamado pelo push e pela sincronização: a tela aberta mostra o que mudou. */
        fun atualizarTela() {
            val a = atual?.get() ?: return
            a.runOnUiThread { if (!a.isFinishing) a.recarregar() }
        }
    }
}
