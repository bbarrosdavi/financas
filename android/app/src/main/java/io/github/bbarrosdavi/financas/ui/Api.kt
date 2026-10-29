package io.github.bbarrosdavi.financas.ui

import android.content.Context
import android.util.Base64
import io.github.bbarrosdavi.financas.Backend
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.net.URLEncoder
import java.util.UUID

class ErroApi(val status: Int, mensagem: String) : Exception(mensagem)

/**
 * A mesma API do site (/api/...), servida pelo Python que roda neste aparelho (Backend): as telas nativas pedem
 * e gravam do mesmo jeito que o site, sem rede.
 */
object Api {
    lateinit var ctx: Context

    private fun chamar(metodo: String, caminho: String, corpo: ByteArray? = null, tipo: String = "application/json"): ByteArray {
        val b64 = corpo?.let { Base64.encodeToString(it, Base64.NO_WRAP) } ?: ""
        val r = JSONObject(Backend.pedir(ctx, metodo, caminho, if (corpo != null) tipo else "", b64))
        val bytes = Base64.decode(r.getString("corpo"), Base64.DEFAULT)
        val status = r.getInt("status")
        if (status >= 400) {
            val detalhe = runCatching { JSONObject(String(bytes)).optString("detail") }.getOrNull()
            throw ErroApi(status, if (detalhe.isNullOrBlank()) "Erro $status" else detalhe)
        }
        return bytes
    }

    suspend fun obj(caminho: String) = withContext(Dispatchers.IO) { JSONObject(String(chamar("GET", caminho))) }
    suspend fun lista(caminho: String) = withContext(Dispatchers.IO) { JSONArray(String(chamar("GET", caminho))) }
    suspend fun bytes(caminho: String) = withContext(Dispatchers.IO) { chamar("GET", caminho) }
    suspend fun put(caminho: String, corpo: JSONObject) =
        withContext(Dispatchers.IO) { String(chamar("PUT", caminho, corpo.toString().toByteArray())) }
    suspend fun post(caminho: String, corpo: JSONObject) =
        withContext(Dispatchers.IO) { String(chamar("POST", caminho, corpo.toString().toByteArray())) }
    suspend fun delete(caminho: String) = withContext(Dispatchers.IO) { String(chamar("DELETE", caminho)) }

    /** Arquivos do banco (.pdf, .csv, .xlsx) para /api/importar, num multipart como o do navegador. */
    suspend fun importar(arquivos: List<Pair<String, ByteArray>>) = withContext(Dispatchers.IO) {
        val fronteira = "----financas" + UUID.randomUUID().toString().replace("-", "")
        val corpo = java.io.ByteArrayOutputStream()
        for ((nome, conteudo) in arquivos) {
            corpo.write("--$fronteira\r\nContent-Disposition: form-data; name=\"arquivos\"; filename=\"${nome.replace("\"", "")}\"\r\n".toByteArray())
            corpo.write("Content-Type: application/octet-stream\r\n\r\n".toByteArray())
            corpo.write(conteudo)
            corpo.write("\r\n".toByteArray())
        }
        corpo.write("--$fronteira--\r\n".toByteArray())
        JSONArray(String(chamar("POST", "/api/importar", corpo.toByteArray(), "multipart/form-data; boundary=$fronteira")))
    }

    fun q(v: String) = URLEncoder.encode(v, "UTF-8")
}

// Leitura confortável de JSON
fun JSONArray.objs(): List<JSONObject> = (0 until length()).map { getJSONObject(it) }
fun JSONObject.d(k: String) = if (isNull(k)) 0.0 else optDouble(k, 0.0)
fun JSONObject.dn(k: String): Double? = if (!has(k) || isNull(k)) null else optDouble(k)
fun JSONObject.s(k: String) = if (isNull(k)) "" else optString(k, "")
fun JSONObject.sn(k: String): String? = if (!has(k) || isNull(k)) null else optString(k)
fun JSONObject.lista(k: String): List<JSONObject> = optJSONArray(k)?.objs() ?: emptyList()
fun jsonDe(vararg pares: Pair<String, Any?>) = JSONObject().apply { pares.forEach { (k, v) -> put(k, v ?: JSONObject.NULL) } }
