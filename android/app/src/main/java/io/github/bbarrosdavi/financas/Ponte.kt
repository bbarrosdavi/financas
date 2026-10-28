package io.github.bbarrosdavi.financas

import android.content.Intent
import android.provider.Settings
import android.webkit.JavascriptInterface
import android.webkit.WebView
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.Executors

/**
 * A ponte com a tela (src/main/js/nativo.js). Cada chamada roda fora da thread da interface e responde por
 * window.__financasResposta(id, json).
 */
class Ponte(private val atividade: MainActivity, private val web: WebView) {
    private val trabalho = Executors.newFixedThreadPool(3)

    @JavascriptInterface
    fun chamar(id: Int, metodo: String, args: String) {
        trabalho.execute {
            val resposta = try {
                executar(metodo, JSONObject(args))
            } catch (e: Exception) {
                JSONObject().put("erro", e.message ?: e.toString()).toString()
            }
            web.post { web.evaluateJavascript("window.__financasResposta($id, ${JSONObject.quote(resposta)})", null) }
        }
    }

    private fun executar(metodo: String, a: JSONObject): String {
        val ctx = atividade.applicationContext
        val ajustes = Ajustes(ctx)
        return when (metodo) {
            "pedir" -> Backend.pedir(ctx, a.getString("metodo"), a.getString("caminho"), a.optString("tipo"), a.optString("corpo"))
            "ajustes" -> ajustes.json().toString()
            "salvarAjustes" -> {
                ajustes.url = a.optString("url")
                ajustes.chave = a.optString("chave")
                val apps = a.optJSONArray("apps")
                if (apps != null) ajustes.apps = (0 until apps.length()).map { apps.getString(it).trim() }.filter { it.isNotEmpty() }.toSet()
                Sincronizacao.agora(ctx)
                ajustes.json().toString()
            }
            "testarConexao" -> testar(a.optString("url").trim().trimEnd('/'), a.optString("chave").trim()).toString()
            "sincronizar" -> Sincronizacao.rodar(ctx).toString()
            "abrirAcessoNotificacoes" -> {
                atividade.startActivity(Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
                "{}"
            }
            "tema" -> {
                atividade.runOnUiThread { atividade.aplicarTema(a.optBoolean("escuro")) }
                "{}"
            }
            else -> JSONObject().put("erro", "chamada desconhecida: $metodo").toString()
        }
    }

    /** /health diz se o servidor está ao alcance; uma troca vazia (cursor no fim) diz se a chave vale, sem mudar nada. */
    private fun testar(url: String, chave: String): JSONObject {
        val r = JSONObject()
        if (!url.startsWith("http://") && !url.startsWith("https://"))
            return r.put("ok", false).put("mensagem", "O endereço começa com http://, por exemplo http://192.168.0.10:8095")
        try {
            val saude = (URL("$url/health").openConnection() as HttpURLConnection).apply { connectTimeout = 5000; readTimeout = 5000 }
            if (saude.responseCode != 200) return r.put("ok", false).put("mensagem", "O endereço respondeu ${saude.responseCode}: não parece o Finanças.")
            val troca = (URL("$url/api/v1/sync").openConnection() as HttpURLConnection).apply {
                connectTimeout = 5000; readTimeout = 10000; requestMethod = "POST"; doOutput = true
                setRequestProperty("Content-Type", "application/json")
                setRequestProperty("Authorization", "Bearer $chave")
            }
            troca.outputStream.use { it.write("""{"protocolo":1,"cursor":4000000000000000000,"mudancas":[]}""".toByteArray()) }
            return when (troca.responseCode) {
                200 -> r.put("ok", true).put("mensagem", "Conectado, e a chave foi aceita.")
                401 -> r.put("ok", false).put("mensagem", "O servidor respondeu, mas recusou a chave.")
                404 -> r.put("ok", true).put("mensagem", "Conectado. Servidor de versão antiga: só os pushes vão, pelo webhook.")
                else -> r.put("ok", false).put("mensagem", "O servidor respondeu ${troca.responseCode} à sincronização.")
            }
        } catch (e: Exception) {
            return r.put("ok", false).put("mensagem", "Sem resposta de $url (${e.javaClass.simpleName}). Mesma rede ou VPN ligada?")
        }
    }
}
