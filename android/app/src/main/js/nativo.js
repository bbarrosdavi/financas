'use strict';
// Dentro do app Android: a tela é o próprio site, empacotado no APK, e a API roda no aparelho (o Python do
// servidor pelo Chaquopy). Este arquivo entra antes do app.js e troca a rede pela ponte com o Kotlin
// (FinancasPonte): fetch('/api/...') continua igual para o app.js, sem servidor nenhum.
(() => {
  const ponte = window.FinancasPonte;
  if (!ponte) return;
  let seq = 0;
  const espera = new Map();
  window.__financasResposta = (id, json) => {
    const fim = espera.get(id);
    espera.delete(id);
    if (fim) fim(JSON.parse(json));
  };
  const chamar = (metodo, args = {}) => new Promise(fim => {
    const id = ++seq;
    espera.set(id, fim);
    ponte.chamar(id, metodo, JSON.stringify(args));
  });
  const paraB64 = buf => {
    const u = new Uint8Array(buf);
    let s = '';
    for (let i = 0; i < u.length; i += 0x8000) s += String.fromCharCode.apply(null, u.subarray(i, i + 0x8000));
    return btoa(s);
  };
  const deB64 = s => Uint8Array.from(atob(s), c => c.charCodeAt(0));

  const fetchDaRede = window.fetch.bind(window);
  window.fetch = async (entrada, opcoes) => {
    const req = new Request(entrada, opcoes);
    const u = new URL(req.url);
    if (u.origin !== location.origin || !/^\/(api|papel)\//.test(u.pathname)) return fetchDaRede(entrada, opcoes);
    const corpo = ['GET', 'HEAD'].includes(req.method) ? '' : paraB64(await req.arrayBuffer());
    const r = await chamar('pedir', {metodo: req.method, caminho: u.pathname + u.search, tipo: req.headers.get('content-type') || '', corpo});
    if (r.erro) throw new TypeError(r.erro);
    const vazio = [204, 205, 304].includes(r.status);
    return new Response(vazio ? null : deB64(r.corpo), {status: r.status, headers: r.cabecalhos});
  };

  // A casca já vem do APK: sem service worker.
  try { Object.defineProperty(navigator, 'serviceWorker', {value: {register: () => Promise.resolve()}, configurable: true}); } catch (_) {}

  // O que só existe no app (Ajustes > Celular): servidor, chave, apps monitorados e acesso a notificações.
  window.FINANCAS_APP = {
    ajustes: () => chamar('ajustes'),
    salvar: a => chamar('salvarAjustes', a),
    testar: (url, chave) => chamar('testarConexao', {url, chave}),
    sincronizar: () => chamar('sincronizar'),
    acessoNotificacoes: () => chamar('abrirAcessoNotificacoes'),
  };

  // Barra de status do Android na cor do tema (claro ou escuro) que o site escolheu.
  const tema = () => chamar('tema', {escuro: document.documentElement.dataset.theme === 'dark'});
  new MutationObserver(tema).observe(document.documentElement, {attributes: true, attributeFilter: ['data-theme']});
  addEventListener('DOMContentLoaded', tema);
})();
