package io.github.bbarrosdavi.financas

import android.annotation.SuppressLint
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.util.Base64
import android.webkit.ValueCallback
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebView
import android.widget.FrameLayout
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.addCallback
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.core.view.ViewCompat
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.webkit.WebViewAssetLoader
import androidx.webkit.WebViewClientCompat
import org.json.JSONObject
import java.io.ByteArrayInputStream
import java.lang.ref.WeakReference
import kotlin.concurrent.thread

/**
 * A tela do app é o próprio site (web/ do repositório, nos assets do APK), servido de dentro do aparelho:
 * os arquivos pelos assets e a API pelo Python local. Nada aqui depende de rede.
 */
class MainActivity : ComponentActivity() {
    private lateinit var moldura: FrameLayout
    private lateinit var web: WebView
    private var escolhaPendente: ValueCallback<Array<Uri>>? = null
    private var planilhaPendente: ByteArray? = null

    private val escolherArquivos = registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { r ->
        val dados = r.data
        val uris = when {
            r.resultCode != RESULT_OK || dados == null -> null
            dados.clipData != null -> Array(dados.clipData!!.itemCount) { dados.clipData!!.getItemAt(it).uri }
            dados.data != null -> arrayOf(dados.data!!)
            else -> null
        }
        escolhaPendente?.onReceiveValue(uris)
        escolhaPendente = null
    }

    private val salvarPlanilha = registerForActivityResult(
        ActivityResultContracts.CreateDocument("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    ) { uri ->
        val bytes = planilhaPendente ?: return@registerForActivityResult
        planilhaPendente = null
        if (uri != null) contentResolver.openOutputStream(uri)?.use { it.write(bytes) }
    }

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (BuildConfig.DEBUG) WebView.setWebContentsDebuggingEnabled(true)     // só no build de teste (chrome://inspect)
        enableEdgeToEdge()
        moldura = FrameLayout(this)
        web = WebView(this)
        moldura.addView(web)
        setContentView(moldura)
        ViewCompat.setOnApplyWindowInsetsListener(moldura) { v, insets ->
            val b = insets.getInsets(WindowInsetsCompat.Type.systemBars() or WindowInsetsCompat.Type.ime())
            v.setPadding(b.left, b.top, b.right, b.bottom)
            WindowInsetsCompat.CONSUMED
        }
        aplicarTema(false)

        web.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true          // preferências, tema e disposição dos painéis, como no navegador
            allowFileAccess = false
        }
        val assets = WebViewAssetLoader.Builder().addPathHandler("/", WebViewAssetLoader.AssetsPathHandler(this)).build()
        web.webViewClient = object : WebViewClientCompat() {
            override fun shouldInterceptRequest(view: WebView, request: WebResourceRequest): WebResourceResponse? {
                val u = request.url
                // Papel de parede (CSS) e outros GET da API que não passam pelo fetch.
                if (u.host == HOST && request.method == "GET" && (u.path.orEmpty().startsWith("/api/") || u.path.orEmpty().startsWith("/papel/")))
                    return resposta(Backend.pedir(applicationContext, "GET", u.encodedPath + (u.encodedQuery?.let { "?$it" } ?: "")))
                return assets.shouldInterceptRequest(u)
            }

            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                val u = request.url
                if (u.host == HOST && u.path == "/api/exportar.xlsx") { baixarPlanilha(); return true }
                if (u.host != HOST) { startActivity(Intent(Intent.ACTION_VIEW, u)); return true }
                return false
            }
        }
        web.webChromeClient = object : WebChromeClient() {
            override fun onShowFileChooser(view: WebView, callback: ValueCallback<Array<Uri>>, params: FileChooserParams): Boolean {
                escolhaPendente?.onReceiveValue(null)
                escolhaPendente = callback
                val intent = params.createIntent().addCategory(Intent.CATEGORY_OPENABLE)
                if (params.mode == FileChooserParams.MODE_OPEN_MULTIPLE) intent.putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true)
                escolherArquivos.launch(Intent.createChooser(intent, null))
                return true
            }
        }
        web.addJavascriptInterface(Ponte(this, web), "FinancasPonte")
        onBackPressedDispatcher.addCallback(this) { if (web.canGoBack()) web.goBack() else finish() }
        if (savedInstanceState == null) web.loadUrl("https://$HOST/web/index.html") else web.restoreState(savedInstanceState)
        atual = WeakReference(this)
    }

    override fun onSaveInstanceState(outState: Bundle) {
        super.onSaveInstanceState(outState)
        web.saveState(outState)
    }

    override fun onResume() {
        super.onResume()
        atual = WeakReference(this)
        recarregarRota()                     // o que chegou pelo push enquanto o app estava fechado
        Sincronizacao.agora(this)
    }

    override fun onStop() {
        super.onStop()
        Sincronizacao.agora(this)            // o que foi classificado aqui vai logo para o servidor
    }

    fun aplicarTema(escuro: Boolean) {
        moldura.setBackgroundColor(getColor(if (escuro) R.color.fundo_escuro else R.color.fundo_claro))
        WindowCompat.getInsetsController(window, window.decorView).apply {
            isAppearanceLightStatusBars = !escuro
            isAppearanceLightNavigationBars = !escuro
        }
    }

    private fun recarregarRota() {
        web.evaluateJavascript("typeof rota === 'function' && !document.getElementById('app').hidden && rota()", null)
    }

    private fun baixarPlanilha() {
        thread {
            val r = JSONObject(Backend.pedir(applicationContext, "GET", "/api/exportar.xlsx"))
            runOnUiThread {
                if (r.getInt("status") != 200) { Toast.makeText(this, "Não deu para gerar a planilha.", Toast.LENGTH_LONG).show(); return@runOnUiThread }
                planilhaPendente = Base64.decode(r.getString("corpo"), Base64.DEFAULT)
                val nome = Regex("filename=\"([^\"]+)\"").find(r.getJSONObject("cabecalhos").optString("content-disposition"))?.groupValues?.get(1)
                salvarPlanilha.launch(nome ?: "financas.xlsx")
            }
        }
    }

    private fun resposta(json: String): WebResourceResponse {
        val r = JSONObject(json)
        val cab = r.getJSONObject("cabecalhos")
        val tipo = cab.optString("content-type", "application/octet-stream")
        val cabecalhos = cab.keys().asSequence().associateWith { cab.getString(it) }
        val status = r.getInt("status")
        return WebResourceResponse(tipo.substringBefore(';').trim(), null, status, if (status < 400) "OK" else "Erro", cabecalhos,
            ByteArrayInputStream(Base64.decode(r.getString("corpo"), Base64.DEFAULT)))
    }

    companion object {
        const val HOST = "appassets.androidplatform.net"
        @Volatile private var atual: WeakReference<MainActivity>? = null

        /** Chamado pelo push e pela sincronização: a tela aberta mostra o que mudou. */
        fun atualizarTela() {
            val a = atual?.get() ?: return
            a.runOnUiThread { if (!a.isFinishing) a.recarregarRota() }
        }
    }
}
