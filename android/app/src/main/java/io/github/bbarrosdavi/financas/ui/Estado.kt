package io.github.bbarrosdavi.financas.ui

import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import org.json.JSONObject

/** O que várias telas compartilham: a versão dos dados (sobe a cada mudança e as telas recarregam), o vocabulário
 *  (categorias, pessoas, metas, contas) e se os dados de demonstração estão ligados. */
object Estado {
    var versao by mutableIntStateOf(0)
    var pendentes by mutableIntStateOf(0)
    var demo by mutableStateOf(false)
    var mensagem by mutableStateOf<String?>(null)
    fun mudou() { versao++ }
}

object Vocab {
    var categorias by mutableStateOf(listOf<JSONObject>())
    var pessoas by mutableStateOf(listOf<JSONObject>())
    var metas by mutableStateOf(listOf<JSONObject>())
    var contas by mutableStateOf(listOf<JSONObject>())
    var coresGrupos by mutableStateOf(mapOf<String, String>())

    fun categoria(id: String?) = categorias.firstOrNull { it.s("id") == id }
    fun pessoa(id: String?) = pessoas.firstOrNull { it.s("id") == id }
    fun meta(id: Int?) = metas.firstOrNull { it.optInt("id") == id }
    fun nomeConta(id: String) = when (id) {
        "nubank_conta" -> "Conta"; "nubank_cartao" -> "Cartão"; "picpay" -> "PicPay"; "bradesco_conta" -> "Bradesco"
        "bradesco_cartao" -> "Cartão Bradesco"; else -> contas.firstOrNull { it.s("id") == id }?.s("nome") ?: id
    }

    suspend fun carregar() {
        val v = Api.obj("/api/vocabulario")
        categorias = v.lista("categorias"); pessoas = v.lista("pessoas"); metas = v.lista("metas"); contas = v.lista("contas")
        val cg = v.optJSONObject("cores_grupos") ?: JSONObject()
        coresGrupos = cg.keys().asSequence().associateWith { cg.getString(it) }
        Estado.pendentes = Api.lista("/api/lancamentos?pendentes=true").length()
    }
}

val NATUREZA = linkedMapOf("gasto" to "Gasto", "renda" to "Renda", "transferencia" to "Transferência", "acerto" to "Acerto", "poupanca" to "Poupança")

/** Carrega dados para uma tela e recarrega quando os dados mudam (Estado.versao) ou quando as chaves mudam. */
class Carga<T> {
    var dado by mutableStateOf<T?>(null)
    var erro by mutableStateOf<String?>(null)
}

@Composable
fun <T> carregar(vararg chaves: Any?, bloco: suspend () -> T): Carga<T> {
    val c = remember { Carga<T>() }
    LaunchedEffect(Estado.versao, *chaves) {
        try { c.dado = bloco(); c.erro = null } catch (e: Exception) { c.erro = e.message ?: e.toString() }
    }
    return c
}

/** Grava e avisa todas as telas; o erro vira mensagem na barra de baixo. */
suspend fun gravar(sucesso: String? = null, acao: suspend () -> Unit): Boolean = try {
    acao(); Vocab.carregar(); Estado.mudou(); if (sucesso != null) Estado.mensagem = sucesso; true
} catch (e: Exception) { Estado.mensagem = e.message ?: e.toString(); false }
