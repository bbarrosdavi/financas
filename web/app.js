'use strict';
// Site de finanças: SPA sem build. Telas por hash (#painel?p=2026-10, #pendentes, ...).

const $ = (s, r = document) => r.querySelector(s);
const brl = v => (v < 0 ? '-' : '') + 'R$ ' + Math.abs(v || 0).toLocaleString('pt-BR', {minimumFractionDigits: 2, maximumFractionDigits: 2});
const brl0 = v => (v < 0 ? '-' : '') + 'R$ ' + Math.abs(v || 0).toLocaleString('pt-BR', {maximumFractionDigits: 0});
const brlv = v => (Math.abs(v) < 10 && v ? brl : brl0)(v);
const sinal = v => (v > 0 ? '+' : v < 0 ? '-' : '') + brlv(Math.abs(v)).replace('R$', 'R$');
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
const dataBR = d => d ? d.split('-').reverse().join('/') : '';
const dataCurta = d => d ? `${d.slice(8, 10)}/${d.slice(5, 7)}/${d.slice(2, 4)}` : '';
const MESES = ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho', 'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro'];
const MES3 = MESES.map(m => m.slice(0, 3));
const mesBR = m => MES3[+m.slice(5, 7) - 1] + '/' + m.slice(2, 4);
const hojeISO = () => new Date().toLocaleDateString('sv-SE');
const CONTA = {nubank_conta: 'Conta', nubank_cartao: 'Cartão', picpay: 'PicPay', bradesco_conta: 'Bradesco', bradesco_cartao: 'Cartão Bradesco'};
const NAT = {gasto: 'Gasto', renda: 'Renda', transferencia: 'Transferência', acerto: 'Acerto', poupanca: 'Poupança'};
const ORIGEM = {manual: 'lançado à mão', push: 'pelo celular'};      // extrato e fatura já se veem pela conta
// Cor fixa por grupo (a cor segue o grupo, nunca a posição). Grupos fora da lista ficam cinza.
const COR_GRUPO = {Moradia: '#2a78d6', 'Alimentação': '#eb6834', 'Saúde': '#1baf7a', Transporte: '#eda100', Lazer: '#e87ba4', Compras: '#6250d6', Assinaturas: '#008300'};
const corGrupo = g => (V.cores_grupos || {})[g] || COR_GRUPO[g] || '#9a99a1';
const corCat = id => { const c = cat(id); return c?.cor || corGrupo(c?.grupo); };

let V = {categorias: [], pessoas: [], contas: [], metas: []};
// Só dentro do app Android (android/app/src/main/js/nativo.js): os ajustes do aparelho em Ajustes > Celular.
const APP = window.FINANCAS_APP;
const cat = id => V.categorias.find(c => c.id === id);
const pessoa = id => V.pessoas.find(p => p.id === id);
const meta = id => V.metas.find(m => m.id === id);
const store = {get: (k, d) => { try { return localStorage.getItem(k) ?? d; } catch (_) { return d; } }, set: (k, v) => { try { localStorage.setItem(k, v); } catch (_) {} }};

async function api(path, opts = {}) {
  const r = await fetch(path, {credentials: 'same-origin', ...opts,
    headers: opts.body && !(opts.body instanceof FormData) ? {'Content-Type': 'application/json'} : {}});
  if (r.status === 401 && !path.endsWith('/login')) { mostrarLogin(); throw new Error('sessão'); }
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText);
  return r.json();
}
// Preferências de visualização: ficam neste aparelho (PC e celular podem ser diferentes).
const PREF_PADRAO = {largura: 'reduzida', densidade: 'compacta', fonte: 'media', colunas: '2', agrupar: true, ordenar: 'excesso',
  vazias: false, grupos: 'auto', estilo: 'vidro', cantos: 'redondos', barras: 'arredondadas', barras_larg: 'medias', grade: true, paineis: {grafico: true, composicao: true, entradas: true, metas: true, cobrancas: true, destinos: true, plano: true}};
let PREF = (() => { try { const p = JSON.parse(store.get('prefs', '{}')); return {...PREF_PADRAO, ...p, paineis: {...PREF_PADRAO.paineis, ...(p.paineis || {})}}; } catch (_) { return {...PREF_PADRAO}; } })();
function salvarPref(k, v) { PREF[k] = v; store.set('prefs', JSON.stringify(PREF)); aplicarVisual(); }
function aplicarVisual() {
  const b = document.body.classList;
  b.toggle('larga', PREF.largura === 'total');
  b.toggle('confortavel', PREF.densidade === 'confortavel');
  ['solido', 'contorno', 'plano'].forEach(e => b.toggle('estilo-' + e, PREF.estilo === e));
  b.toggle('cantos-retos', PREF.cantos === 'retos');
  document.documentElement.style.fontSize = {pequena: '13px', media: '14px', grande: '15.5px'}[PREF.fonte] || '14px';
}
const abertos = () => { try { return JSON.parse(store.get('grupos-abertos', '{}')); } catch (_) { return {}; } };

const put = (p, b) => api(p, {method: 'PUT', body: JSON.stringify(b)});
const post = (p, b) => api(p, {method: 'POST', body: b instanceof FormData ? b : JSON.stringify(b)});
const del = p => api(p, {method: 'DELETE'});

// ---------------------------------------------------------------- tema e papel de parede
const SOL = '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>';
const ICONE_BARRAS = '<svg viewBox="0 0 16 16" width="13" height="13" fill="currentColor"><rect x="1.5" y="8" width="3" height="6.5" rx="1"/><rect x="6.5" y="4.5" width="3" height="10" rx="1"/><rect x="11.5" y="1.5" width="3" height="13" rx="1"/></svg>';
const LUA = '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>';
function aplicarTema() {
  const t = store.get('tema', 'light');
  if (t === 'dark') document.documentElement.dataset.theme = 'dark'; else delete document.documentElement.dataset.theme;
  $('meta[name=theme-color]').content = t === 'dark' ? '#101014' : '#e9ebef';
  const b = $('#tema');
  if (b) { b.innerHTML = t === 'dark' ? SOL : LUA; b.title = t === 'dark' ? 'Mudar para claro' : 'Mudar para escuro'; }
}
$('#tema').addEventListener('click', () => {
  store.set('tema', store.get('tema', 'light') === 'dark' ? 'light' : 'dark');
  aplicarTema();
  if ((location.hash.slice(1) || '').startsWith('ajustes')) rota();
});
async function aplicarPapel() {
  const p = await api('/api/papeis');
  document.body.style.setProperty('--papel', p.atual ? `url("/papel/${encodeURIComponent(p.atual)}")` : 'none');
}

// ---------------------------------------------------------------- login e rotas
function mostrarLogin() { $('#app').hidden = true; $('#login').hidden = false; $('#senha').focus(); }
$('#f-login').addEventListener('submit', async e => {
  e.preventDefault();
  try { await post('/api/login', {senha: $('#senha').value}); $('#login').hidden = true; iniciar(); }
  catch (err) { $('#login-erro').textContent = err.message; }
});

const TELAS = {painel, pendentes, lancamentos, orcamento, importar, pessoas, plano, projecao: plano, ajustes};
const params = () => new URLSearchParams(location.hash.split('?')[1] || '');
async function rota() {
  const nome = (location.hash.slice(1) || 'painel').split('?')[0];
  document.querySelectorAll('#nav a').forEach(a => a.classList.toggle('on', a.getAttribute('href') === '#' + nome));
  const t = $('#tela');
  grades.forEach(g => g.destroy()); grades = [];
  if (!t.children.length) t.innerHTML = '<p class="muted">Carregando...</p>';
  try { await (TELAS[nome] || painel)(t); organizarPagina(t, nome === 'plano' ? 'projecao' : TELAS[nome] ? nome : 'painel'); }
  catch (e) { if (e.message !== 'sessão') t.innerHTML = `<div class="painel vidro erro">${esc(e.message)}</div>`; }
  contarPendentes();
}
async function contarPendentes() {
  const p = await api('/api/lancamentos?pendentes=true');
  const b = $('#n-pend'); b.textContent = p.length; b.hidden = !p.length;
}
async function iniciar() {
  V = await api('/api/vocabulario');
  $('#app').hidden = false;
  aplicarPapel().catch(() => {});
  rota();
  if (store.get('tour', '') !== 'visto') setTimeout(iniciarTour, 900);      // primeira entrada neste aparelho
}
window.addEventListener('hashchange', rota);

// ---------------------------------------------------------------- cartões rearranjáveis (Muuri: empacota sem buracos)
const ICONE_ALCA = '<svg viewBox="0 0 10 16" width="8" height="13" fill="currentColor"><circle cx="2.5" cy="3" r="1.4"/><circle cx="7.5" cy="3" r="1.4"/><circle cx="2.5" cy="8" r="1.4"/><circle cx="7.5" cy="8" r="1.4"/><circle cx="2.5" cy="13" r="1.4"/><circle cx="7.5" cy="13" r="1.4"/></svg>';
// Largura em sextos da página (2 = ⅓, 3 = ½, 4 = ⅔, 6 = inteira); altura em px ou automática.
const NOME_LARG = {2: '⅓', 3: '½', 4: '⅔', 5: '⅚', 6: 'inteira'}, CICLO_LARG = [2, 3, 4, 6], LARG_NOME = {terco: 2, metade: 3, inteira: 6};
const cartao = (id, titulo, sub, corpo) => `<section class="cartao" data-id="${id}"><div class="painel vidro">
  <h3><span class="alca" title="Arraste para mover">${ICONE_ALCA}</span><span class="titulo-cartao">${titulo}</span>${sub ? `<small>${sub}</small>` : ''}
    <button class="tam-btn" data-tam-btn title="Largura do painel"></button></h3><div class="corpo">${corpo}</div></div></section>`;
let grades = [];
function mosaico(raiz, pagina, padrao) {
  grades.forEach(g => g.destroy()); grades = [];
  const chave = 'mosaico:' + pagina;
  const salvo = (() => { try { return JSON.parse(store.get(chave, '{}')); } catch (_) { return {}; } })();
  salvo.larg ||= {}; salvo.alt ||= {};
  const cards = [...raiz.querySelectorAll(':scope > .cartao')];
  // Ordem salva; cartão que não estava nela (ex.: o título, que virou cartão depois) entra na posição natural.
  const ordem = (salvo.ordem || []).filter(id => cards.some(c => c.dataset.id === id));
  cards.forEach((c, i) => { if (!ordem.includes(c.dataset.id)) ordem.splice(Math.min(i, ordem.length), 0, c.dataset.id); });
  ordem.forEach(id => raiz.appendChild(cards.find(c => c.dataset.id === id)));
  const larg = c => +(salvo.larg[c.dataset.id] || LARG_NOME[padrao[c.dataset.id]] || 3);
  const aplicar = c => {
    const n = larg(c), h = salvo.alt[c.dataset.id];
    c.style.width = (n / 6 * 100) + '%'; c.dataset.larg = n;
    if (h) { c.dataset.alt = h; c.style.setProperty('--alt', h + 'px'); } else { delete c.dataset.alt; c.style.removeProperty('--alt'); }
    c.querySelector('[data-tam-btn]').textContent = NOME_LARG[n];
  };
  cards.forEach(aplicar);
  const salvar = () => store.set(chave, JSON.stringify({ordem: grid.getItems().map(i => i.getElement().dataset.id), larg: salvo.larg, alt: salvo.alt}));
  const grid = new Muuri(raiz, {items: '.cartao', dragEnabled: innerWidth > 920, dragHandle: '.alca', layout: {fillGaps: true},
    layoutOnResize: 120, dragSortHeuristics: {sortInterval: 50, minDragDistance: 10, minBounceBackAngle: 1}, dragRelease: {duration: 200}});
  grid.on('dragReleaseEnd', salvar);
  grades.push(grid);
  cards.forEach(c => c.querySelector('[data-tam-btn]').onclick = () => {
    const n = larg(c);
    salvo.larg[c.dataset.id] = CICLO_LARG[(CICLO_LARG.indexOf(n) + 1) % CICLO_LARG.length] || 6;
    aplicar(c); salvar(); grid.refreshItems().layout();
  });
  // Alça no canto: arrastar muda largura (em sextos) e altura; duplo clique volta à altura automática.
  cards.forEach(c => {
    const al = document.createElement('div');
    al.className = 'redim'; al.title = 'Arraste para mudar largura e altura; duplo clique volta à altura automática';
    c.firstElementChild.appendChild(al);
    al.onpointerdown = e => {
      if (innerWidth <= 920) return;
      e.preventDefault(); e.stopPropagation(); al.setPointerCapture(e.pointerId);
      const x0 = c.getBoundingClientRect().left, y0 = c.firstElementChild.getBoundingClientRect().top, W = raiz.getBoundingClientRect().width;
      let quadro = 0;
      c.classList.add('redimensionando');
      al.onpointermove = ev => {
        salvo.larg[c.dataset.id] = Math.min(6, Math.max(2, Math.round((ev.clientX - x0) / W * 6)));
        salvo.alt[c.dataset.id] = Math.max(110, Math.round(ev.clientY - y0));
        aplicar(c);
        if (!quadro) quadro = requestAnimationFrame(() => { quadro = 0; grid.refreshItems().layout(true); });
      };
      al.onpointerup = () => { al.onpointermove = al.onpointerup = null; c.classList.remove('redimensionando'); salvar(); grid.refreshItems().layout(); };
    };
    al.ondblclick = () => { delete salvo.alt[c.dataset.id]; aplicar(c); salvar(); grid.refreshItems().layout(); };
  });
  // Altura muda (grupo aberto, gráfico desenhado, fonte carregada): reempacota.
  const ro = new ResizeObserver(() => { grid.refreshItems().layout(); });
  cards.forEach(c => ro.observe(c.firstElementChild));
  grid.on('destroy', () => ro.disconnect());
  raiz.classList.add('pronto');
  return grid;
}
// Toda página vira mosaico: título, barra de período e seções soltas viram cartões que se movem e redimensionam.
const PADRAO_MOSAICO = {
  painel: {resumo: 'inteira', categorias: 'metade', plano: 'inteira'},
  projecao: {'proj-resumo': 'inteira', 'proj-grafico': 'metade', 'proj-premissas': 'metade', 'proj-tabela': 'inteira', 'proj-eventos': 'inteira'},
  orcamento: {'orc-grade': 'inteira', 'orc-fixas': 'inteira', 'orc-cats': 'inteira', 'orc-metas': 'inteira'},
};
const slug = s => s.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'secao';
const BOTAO_TAM = '<button class="tam-btn" data-tam-btn title="Largura do painel"></button>';
function cartaoTopo(id, el) {
  el.classList.remove('vidro');
  const c = document.createElement('section'); c.className = 'cartao'; c.dataset.id = id;
  const p = document.createElement('div'); p.className = 'painel vidro cartao-topo';
  p.innerHTML = `<span class="alca" title="Arraste para mover">${ICONE_ALCA}</span>`;
  p.appendChild(el); p.insertAdjacentHTML('beforeend', BOTAO_TAM);
  c.appendChild(p);
  return c;
}
function cartaoSecao(sec, idUnico) {
  const h3 = sec.querySelector(':scope > h3');
  const c = document.createElement('section'); c.className = 'cartao';
  const corpo = document.createElement('div'); corpo.className = 'corpo';
  [...sec.childNodes].filter(n => n !== h3).forEach(n => corpo.appendChild(n));
  if (h3) {
    const tit = document.createElement('span'); tit.className = 'titulo-cartao';
    while (h3.firstChild && !(h3.firstChild.nodeType === 1 && h3.firstChild.tagName === 'SMALL')) tit.appendChild(h3.firstChild);
    c.dataset.id = idUnico('s-' + slug(tit.textContent));
    h3.prepend(tit);
    h3.insertAdjacentHTML('afterbegin', `<span class="alca" title="Arraste para mover">${ICONE_ALCA}</span>`);
    h3.insertAdjacentHTML('beforeend', BOTAO_TAM);
  } else {
    c.dataset.id = idUnico('s-secao');
    sec.insertAdjacentHTML('afterbegin', `<div class="ctrl-cartao"><span class="alca" title="Arraste para mover">${ICONE_ALCA}</span>${BOTAO_TAM}</div>`);
  }
  sec.appendChild(corpo);
  c.appendChild(sec);
  return c;
}
function organizarPagina(t, pagina) {
  const padrao = {...(PADRAO_MOSAICO[pagina] || {})};
  let raiz = t.querySelector(':scope > .mosaico');
  const usados = new Set(raiz ? [...raiz.querySelectorAll(':scope > .cartao')].map(c => c.dataset.id) : []);
  const idUnico = base => { let id = base, i = 2; while (usados.has(id)) id = `${base}-${i++}`; usados.add(id); return id; };
  const antes = [], depois = [];
  let passou = false;
  for (const el of [...t.children]) {
    if (el === raiz) { passou = true; continue; }
    const lista = passou ? depois : antes;
    if (el.matches('.titulo, .periodo')) {
      const id = idUnico(el.matches('.titulo') ? 'titulo' : 'periodo');
      padrao[id] ||= 'inteira'; lista.push(cartaoTopo(id, el));
    } else if (el.matches('section.painel')) {
      const c = cartaoSecao(el, idUnico); padrao[c.dataset.id] ||= 'inteira'; lista.push(c);
    } else if (el.matches('.grade')) {
      el.querySelectorAll(':scope > section.painel').forEach(sec => { const c = cartaoSecao(sec, idUnico); padrao[c.dataset.id] ||= el.matches('.uma') ? 'inteira' : 'metade'; lista.push(c); });
      el.remove();
    }
  }
  if (!raiz && !antes.length) return;
  if (!raiz) { raiz = document.createElement('div'); raiz.className = 'mosaico'; raiz.id = 'mosaico'; t.appendChild(raiz); }
  raiz.prepend(...antes); raiz.append(...depois);
  mosaico(raiz, pagina, padrao);
  ligarAjuda(raiz, pagina);
}

// Ordem das abas do menu: arrastando no menu (computador) ou pelas setas em Ajustes.
const ABAS_PADRAO = [...document.querySelectorAll('#nav a')].map(a => a.getAttribute('href'));
const ordemAbas = () => { let o; try { o = JSON.parse(store.get('ordem-abas', '[]')); } catch (_) { o = []; }
  return [...o.filter(h => ABAS_PADRAO.includes(h)), ...ABAS_PADRAO.filter(h => !o.includes(h))]; };
function aplicarOrdemAbas(ordem = ordemAbas()) {
  const nav = $('#nav'), as = [...nav.querySelectorAll('a')];
  ordem.forEach(h => nav.appendChild(as.find(a => a.getAttribute('href') === h)));
  store.set('ordem-abas', JSON.stringify(ordem));
}
document.querySelectorAll('#nav a').forEach(a => {
  a.draggable = true;
  a.ondragstart = e => { e.dataTransfer.setData('text/plain', a.getAttribute('href')); a.classList.add('arrastando'); };
  a.ondragend = () => a.classList.remove('arrastando');
  a.ondragover = e => e.preventDefault();
  a.ondrop = e => {
    e.preventDefault();
    const src = [...$('#nav').children].find(x => x.getAttribute('href') === e.dataTransfer.getData('text/plain'));
    if (!src || src === a) return;
    const r = a.getBoundingClientRect();
    a.parentNode.insertBefore(src, e.clientX < r.left + r.width / 2 ? a : a.nextSibling);
    aplicarOrdemAbas([...$('#nav').children].map(x => x.getAttribute('href')));
  };
});
aplicarOrdemAbas();

function restaurarMosaicos() { Object.keys(localStorage).filter(k => k.startsWith('mosaico:')).forEach(k => { try { localStorage.removeItem(k); } catch (_) {} }); }

// ---------------------------------------------------------------- gráficos no tamanho do cartão
// O SVG é desenhado com o tamanho real do contêiner (texto sempre do mesmo tamanho) e redesenhado quando ele muda.
const roGraficos = new ResizeObserver(es => es.forEach(e => { const el = e.target; cancelAnimationFrame(el._quadro); el._quadro = requestAnimationFrame(() => el._desenhar?.()); }));
function desenharNoTamanho(el, f) { el._desenhar = () => { if (el.isConnected && el.clientWidth) { f(el.clientWidth, el.clientHeight); ligarDicas(el); } }; roGraficos.observe(el); el._desenhar(); }
const raioBarra = (w, h) => PREF.barras === 'retas' ? 0 : Math.max(0, Math.min(3, w / 2, h));
const barra = (x, y0, h, w, cor, extra = '') => { const r = raioBarra(w, h);
  return h > 0 ? `<path d="M${x},${y0} v${-(h - r)} q0,-${r} ${r},-${r} h${w - 2 * r} q${r},0 ${r},${r} v${h - r} z" fill="${cor}" ${extra}/>` : ''; };
const FRACAO_BARRA = {finas: .45, medias: .7, largas: .92};
function escalaY(max, min, alturaUtil) {
  const alvo = Math.max(2, Math.min(6, Math.floor(alturaUtil / 38)));
  const passo = [50, 100, 200, 250, 500, 1000, 2000, 2500, 5000, 10000, 20000, 50000].find(p => (max - min) / p <= alvo) || 100000;
  return {passo, topo: Math.ceil(max / passo) * passo || passo, base: Math.floor(min / passo) * passo};
}
const kRot = v => Math.abs(v) >= 1000 ? (v / 1000).toLocaleString('pt-BR', {maximumFractionDigits: 1}) + 'k' : String(v);

// ---------------------------------------------------------------- dica (tooltip)
const tip = $('#tip');
function dica(e, html) { tip.innerHTML = html; tip.style.display = 'block';
  tip.style.left = Math.min(e.clientX + 14, innerWidth - tip.offsetWidth - 8) + 'px'; tip.style.top = (e.clientY + 14) + 'px'; }
document.addEventListener('pointermove', e => { if (!e.target.closest('[data-tip]')) tip.style.display = 'none'; });
function ligarDicas(raiz) { raiz.querySelectorAll('[data-tip]').forEach(el => el.addEventListener('pointermove', e => dica(e, el.dataset.tip))); }

function tabela(el, cab, linhas, num = [], cls = () => '') {
  el.innerHTML = `<thead><tr>${cab.map((c, i) => `<th class="${num.includes(i) ? 'n' : ''}">${c}</th>`).join('')}</tr></thead><tbody>` +
    (linhas.length ? linhas.map((l, li) => `<tr class="${cls(l, li)}">${l.map((c, i) => `<td class="${num.includes(i) ? 'n' : ''}">${c}</td>`).join('')}</tr>`).join('')
      : `<tr><td colspan="${cab.length}" class="muted">Nada aqui.</td></tr>`) + '</tbody>';
}

// ---------------------------------------------------------------- período
function rotuloPeriodo(P) {
  if (P.tipo === 'ano') return P.periodo;
  if (P.tipo === 'mes') return `${MESES[+P.periodo.slice(5) - 1]} de ${P.periodo.slice(0, 4)}`;
  const i = P.inicio, f = P.fim;
  return `${+i.slice(8)} ${i.slice(5, 7) !== f.slice(5, 7) ? MES3[+i.slice(5, 7) - 1] + ' ' : ''}a ${+f.slice(8)} de ${MES3[+f.slice(5, 7) - 1]}`;
}
const rotuloCurto = (p, tipo) => tipo === 'ano' ? p : tipo === 'mes' ? mesBR(p + '-01') : 'semana ' + p.split('-W')[1];
function semanaISO(d) {
  const t = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
  const dia = t.getUTCDay() || 7; t.setUTCDate(t.getUTCDate() + 4 - dia);
  const ini = new Date(Date.UTC(t.getUTCFullYear(), 0, 1));
  return `${t.getUTCFullYear()}-W${String(Math.ceil(((t - ini) / 864e5 + 1) / 7)).padStart(2, '0')}`;
}
function trocarTipo(P, tipo) {
  const ref = P.hoje >= P.inicio && P.hoje <= P.fim ? P.hoje : P.inicio;
  if (tipo === 'ano') return ref.slice(0, 4);
  if (tipo === 'mes') return ref.slice(0, 7);
  return semanaISO(new Date(ref + 'T12:00'));
}

// ---------------------------------------------------------------- painel
async function painel(t) {
  const periodo = params().get('p') || '';
  const P = await api('/api/painel' + (periodo ? '?periodo=' + periodo : ''));
  const comparar = store.get('comparar', '0') === '1';
  const ant = rotuloCurto(P.anterior, P.tipo);
  const T = P.totais, TA = P.totais_anterior;
  const conta = P.contas.find(c => c.id === 'nubank_conta');
  const devo = P.pessoas.filter(p => p.saldo < 0).reduce((a, p) => a - p.saldo, 0);
  const meDevem = P.pessoas.filter(p => p.saldo > 0).reduce((a, p) => a + p.saldo, 0);
  const usoVar = P.teto_variavel ? P.gasto_variavel / P.teto_variavel : 0;
  const ideal = P.teto_variavel * P.ritmo;
  const ORDEM = {excesso: (a, b) => (b.acima - a.acima) || ((b.gasto / (b.teto || 1)) - (a.gasto / (a.teto || 1))),
    valor: (a, b) => (b.gasto + b.parcelas) - (a.gasto + a.parcelas), uso: (a, b) => (b.gasto / (b.teto || 1)) - (a.gasto / (a.teto || 1)),
    nome: (a, b) => a.nome.localeCompare(b.nome)};
  const cats = P.categorias.filter(c => c.gasto || c.parcelas || (comparar && c.anterior) || (PREF.vazias && c.teto))
    .sort(ORDEM[PREF.ordenar] || ORDEM.excesso);
  const acimaTot = cats.reduce((a, c) => a + c.acima, 0), acimaAnt = cats.reduce((a, c) => a + c.acima_anterior, 0);
  const nAcima = cats.filter(c => c.acima > 0).length;
  const dlt = (a, b, inverso) => { const d = a - b; if (Math.abs(d) < .5) return '<span class="muted delta">igual</span>';
    const ruim = inverso ? d < 0 : d > 0; return `<span class="delta ${ruim ? 'neg' : 'pos'}">${sinal(d)} vs ${ant}</span>`; };

  t.innerHTML = `
  <div class="periodo vidro">
    <div class="segmentos">${[['semana', 'Semana'], ['mes', 'Mês'], ['ano', 'Ano']].map(([k, n]) => `<button data-tipo="${k}" class="${P.tipo === k ? 'on' : ''}">${n}</button>`).join('')}</div>
    <button class="seta" data-ir="${P.anterior}" title="anterior">&lsaquo;</button>
    <span class="rotulo-periodo">${rotuloPeriodo(P)}</span>
    <button class="seta" data-ir="${P.proximo}" title="próximo">&rsaquo;</button>
    ${P.tipo === 'ano' ? `<select id="sel-ano">${P.anos.map(a => `<option ${a === P.periodo ? 'selected' : ''}>${a}</option>`).join('')}</select>` : ''}
    <button data-ir="${trocarTipo({...P, inicio: P.hoje, fim: P.hoje}, P.tipo)}">Hoje</button>
    <span class="espaco"></span>
    <label class="alternar"><input type="checkbox" id="comparar" ${comparar ? 'checked' : ''}> Comparar com ${ant}</label>
  </div>

  <div class="mosaico" id="mosaico">
  ${cartao('resumo', 'Resumo do período', '', `<div class="heroi">
    <div>
      <div class="rot">Resultado ${P.tipo === 'semana' ? 'da semana' : P.tipo === 'ano' ? 'do ano' : 'do mês'}</div>
      <div class="grande ${T.resultado < 0 ? 'neg' : 'pos'}">${sinal(T.resultado)}</div>
      ${comparar ? dlt(T.resultado, TA.resultado, true) : ''}
      <div class="linha-kv"><span>Entradas</span><b>${brl0(T.renda)}</b></div>
      <div class="linha-kv"><span>Gastos</span><b>${brl0(T.gasto)}</b></div>
      <div class="linha-kv"><span>Juros e taxas</span><b class="${T.juros ? 'neg' : ''}">${brlv(T.juros)}</b></div>
      ${P.metas.some(m => m.guardado_periodo) ? `<div class="linha-kv"><span>Guardado em metas</span><b class="pos">${brl0(P.metas.reduce((a, m) => a + m.guardado_periodo, 0))}</b></div>` : ''}
      ${comparar ? `<div class="linha-kv muted"><span>${ant}: entradas / gastos</span><span>${brl0(TA.renda)} / ${brl0(TA.gasto)}</span></div>` : ''}
    </div>
    <div>
      <div class="rot">Ainda pode gastar (categorias variáveis)</div>
      <div class="grande ${P.pode_gastar < 0 ? 'neg' : usoVar > P.ritmo + .1 ? 'warnc' : 'pos'}">${brl0(P.pode_gastar)}</div>
      <div class="barra-grande"><div class="fill" style="width:${Math.min(usoVar, 1) * 100}%;background:${usoVar > 1 ? 'var(--ruim)' : usoVar > P.ritmo + .1 ? 'var(--atencao)' : 'var(--ok)'}"></div>
        ${P.ritmo > 0 && P.ritmo < 1 ? `<div class="ritmo" style="left:${P.ritmo * 100}%"></div>` : ''}</div>
      <div class="linha-kv"><span>Gasto</span><b>${brl0(P.gasto_variavel)} de ${brl0(P.teto_variavel)}</b></div>
      ${P.ritmo > 0 && P.ritmo < 1 ? `<div class="linha-kv"><span>No ritmo certo, até hoje</span><b>${brl0(ideal)}</b></div>` : ''}
    </div>
    <div class="kpis">
      ${kpiConta(conta)}
      <div class="kpi"><div class="rot">Dívida do cartão</div><div class="v neg">${brl0(P.cartao.divida)}</div>
        <div class="d">limite livre <b class="${P.cartao.limite_livre < 300 ? 'neg' : ''}">${brl0(P.cartao.limite_livre)}</b> de ${brl0(P.cartao.limite)}</div></div>
      <div class="kpi"><div class="rot">Você deve / te devem</div><div class="v">${brl0(devo)} <span class="muted">/</span> ${brl0(meDevem)}</div>
        <div class="d"><a href="#pessoas">ver pessoas</a></div></div>
      <div class="kpi"><div class="rot">Pendentes</div><div class="v ${P.pendentes ? 'warnc' : 'pos'}">${P.pendentes}</div>
        <div class="d">${P.pendentes ? '<a href="#pendentes">classificar agora</a>' : 'tudo classificado'}</div></div>
    </div></div>`)}
  ${cartao('categorias', 'Categorias', `teto ${P.tipo === 'ano' ? 'acumulado no ano' : P.tipo === 'semana' ? 'do mês ÷ 4' : 'do mês'}`,
    `${nAcima || acimaAnt ? `<div class="resumo-acima"><div><div class="rot">Acima do teto</div><div class="grande">${brl0(acimaTot)}</div></div>
        <div>${nAcima} categoria(s) estourada(s)</div>
        <div>${ant}: <b>${brl0(acimaAnt)}</b> acima · ${acimaTot > acimaAnt ? `<b class="neg">piorou ${brl0(acimaTot - acimaAnt)}</b>` : acimaTot < acimaAnt ? `<b class="pos">melhorou ${brl0(acimaAnt - acimaTot)}</b>` : 'igual'}</div></div>` : ''}
      <div id="cats"></div>`)}
  ${PREF.paineis.grafico ? cartao('grafico', 'Entradas e gastos', P.tipo === 'semana' ? 'últimas 12 semanas' : P.tipo === 'ano' ? 'jan a dez' : 'últimos 12 meses',
    `${legendaSeries()}<div class="chart grafico" id="ch"></div>`) : ''}
  ${PREF.paineis.composicao ? cartao('composicao', 'Para onde foi', 'gasto por grupo', '<div id="comp"></div>') : ''}
  ${PREF.paineis.entradas ? cartao('entradas', 'Entradas do período', 'bloco Income da planilha', '<div class="scroll"><table id="t-ent"></table></div>') : ''}
  ${PREF.paineis.metas ? cartao('metas', 'Poupança e metas', 'bloco Savings da planilha', '<div id="t-metas"></div>') : ''}
  ${PREF.paineis.cobrancas ? cartao('cobrancas', 'Próximas cobranças no cartão', '', '<div id="t-comp"></div>') : ''}
  ${PREF.paineis.destinos ? cartao('destinos', 'Maiores destinos', '', '<div class="scroll"><table id="t-top"></table></div>') : ''}
  ${PREF.paineis.plano ? cartao('plano', `Projeção até ${mesBR(P.plano.horizonte + '-01')}`, '<a href="#projecao">ver completa e editar</a>', '<div class="scroll"><table id="t-plano"></table></div>') : ''}
  </div>`;

  // categorias: linha compacta (nome | barra | valor); detalhe só quando há o que dizer
  // colunas da tabela "Expenses" da planilha: gasto, teto, % do teto, resta (verde) ou excede (vermelho)
  const colunas = (gasto, teto, acima) => {
    const pct = teto ? Math.round(gasto / teto * 100) + '%' : '-';
    const resto = teto == null ? '<span class="muted">sem teto</span>'
      : acima > 0 ? `<b class="neg">+${brlv(acima)}</b>` : `<b class="pos">${brlv(Math.max(teto - gasto, 0))}</b>`;
    return `<span class="c-gasto"><b>${brlv(gasto)}</b></span><span class="c-teto">${teto != null ? brl0(teto) : '-'}</span>
      <span class="c-pct ${teto && gasto > teto ? 'neg' : ''}">${pct}</span><span class="c-resto">${resto}</span>`;
  };
  const linhaCat = c => {
    const pct = c.teto ? c.gasto / c.teto : (c.gasto ? 2 : 0);
    const cls = c.acima > 0 ? 'bad' : (c.fixa ? 'neutro' : pct > P.ritmo + .1 ? 'warn' : '');
    const dAcima = c.acima - c.acima_anterior;
    const varTot = c.gasto + c.parcelas - c.anterior;
    const infos = [];
    if (c.acima > 0 || c.acima_anterior > 0)
      infos.push(c.acima_anterior > 0 ? `<span>${ant}: <b>${brlv(c.acima_anterior)}</b> acima · <span class="vs ${dAcima > 0 ? 'neg' : dAcima < 0 ? 'pos' : ''}">${dAcima > 0 ? 'piorou ' + brlv(dAcima) : dAcima < 0 ? 'melhorou ' + brlv(-dAcima) : 'igual'}</span></span>`
        : `<span>${ant}: dentro do teto</span>`);
    if (comparar) infos.push(`<span>${ant}: ${brlv(c.anterior)} <span class="vs ${varTot > 0 ? 'neg' : varTot < 0 ? 'pos' : ''}">(${sinal(varTot)}${c.anterior ? `, ${varTot > 0 ? '+' : ''}${Math.round(varTot / c.anterior * 100)}%` : ''})</span></span>`);
    if (c.parcelas) infos.push(`<span>+ ${brlv(c.parcelas)} parcelas antigas</span>`);
    return `<div class="cat" data-evol-cat="${c.id}" data-tip="<b>${esc(c.nome)}</b><br>${brl(c.gasto)} de ${c.teto != null ? brl(c.teto) : 'sem teto'} · ${c.n} lançamento(s)<br>toque para ver a evolução">
      <div class="nome"><i style="background:${corCat(c.id)}"></i><span>${esc(c.nome)}</span></div>
      <div class="track"><div class="fill ${cls}" style="width:${Math.min(pct, 1) * 100}%"></div>${!c.fixa && P.ritmo > 0 && P.ritmo < 1 ? `<div class="ritmo" style="left:${P.ritmo * 100}%"></div>` : ''}</div>
      ${colunas(c.gasto, c.teto, c.acima)}
      ${infos.length ? `<div class="info">${infos.join('<span class="sep">·</span>')}</div>` : ''}</div>`;
  };
  const cabecalho = `<div class="cat-cab"><span>${PREF.agrupar ? 'Grupo / categoria' : 'Categoria'}</span><span></span><span>Gasto</span><span>Teto</span><span>%</span><span>Resta / excede</span></div>`;
  if (!PREF.agrupar) {
    $('#cats').innerHTML = cats.length ? cabecalho + cats.map(linhaCat).join('') : '<p class="muted">Nenhum gasto no período.</p>';
  } else {
    const porGrupo = {};
    cats.forEach(c => (porGrupo[c.grupo] ||= []).push(c));
    const ab = abertos();
    const blocos = Object.entries(porGrupo).map(([g, cs]) => {
      const soma = k => cs.reduce((a, c) => a + (c[k] || 0), 0);
      const comTeto = cs.some(c => c.teto != null);
      return {g, cs, gasto: soma('gasto'), teto: comTeto ? soma('teto') : null, acima: soma('acima'), parcelas: soma('parcelas'), anterior: soma('anterior')};
    }).sort((a, b) => PREF.ordenar === 'nome' ? a.g.localeCompare(b.g) : PREF.ordenar === 'valor' ? (b.gasto + b.parcelas) - (a.gasto + a.parcelas) : (b.acima - a.acima) || (b.gasto - a.gasto));
    $('#cats').innerHTML = cabecalho + blocos.map(b => {
      const aberto = b.g in ab ? ab[b.g] : PREF.grupos === 'abertos' || (PREF.grupos === 'auto' && b.acima > 0);
      const pct = b.teto ? b.gasto / b.teto : 0;
      return `<div class="grupo-cat ${aberto ? 'aberto' : ''}" data-grupo="${esc(b.g)}">
      <div class="grupo-cab"><span class="nome"><svg class="seta-g" viewBox="0 0 10 10" width="10" height="10"><path d="M3 2l4 3-4 3" fill="none" stroke="currentColor" stroke-width="1.6"/></svg><i style="background:${corGrupo(b.g)}"></i>${esc(b.g)} <small class="muted">${b.cs.length}</small><button class="botao-icone" data-evol-grupo="${esc(b.g)}" title="Evolução de ${esc(b.g)}" aria-label="Evolução de ${esc(b.g)}">${ICONE_BARRAS}</button></span>
        <div class="track mini"><div class="fill ${b.acima > 0 ? 'bad' : ''}" style="width:${Math.min(pct, 1) * 100}%"></div></div>
        ${colunas(b.gasto, b.teto, b.teto != null ? Math.max(0, b.gasto - b.teto) : 0)}
        <span class="g-extra">${b.parcelas ? `<small class="muted">+ ${brl0(b.parcelas)} de parcelas antigas</small>` : ''}${comparar ? `<small class="muted">${ant}: ${brl0(b.anterior)}</small>` : ''}</span></div>
      <div class="grupo-corpo">${b.cs.map(linhaCat).join('')}</div></div>`;
    }).join('') || '<p class="muted">Nenhum gasto no período.</p>';
    $('#cats').querySelectorAll('.grupo-cab').forEach(h => h.onclick = e => {
      if (e.target.closest('[data-evol-grupo]')) return;
      const el = h.parentElement, g = el.dataset.grupo, a = abertos();
      el.classList.toggle('aberto'); a[g] = el.classList.contains('aberto'); store.set('grupos-abertos', JSON.stringify(a));
    });
  }

  if ($('#ch')) {
    graficoBarras($('#ch'), P.serie, P.tipo);
    t.querySelectorAll('[data-serie]').forEach(i => i.onchange = () => {
      store.set('grafico-series', JSON.stringify({...verSeries(), [i.dataset.serie]: i.checked})); $('#ch')._desenhar();
    });
  }
  // composição por grupo
  const grupos = Object.entries(P.grupos).sort((a, b) => b[1] - a[1]);
  const totG = grupos.reduce((a, [, v]) => a + v, 0) || 1;
  if ($('#comp')) $('#comp').innerHTML = `<div class="composicao">${grupos.map(([g, v]) => `<span style="width:${v / totG * 100}%;background:${corGrupo(g)}" data-tip="<b>${esc(g)}</b><br>${brl(v)} (${Math.round(v / totG * 100)}%)"></span>`).join('')}</div>
    <table>${grupos.map(([g, v]) => `<tr><td><i style="display:inline-block;width:9px;height:9px;border-radius:50%;background:${corGrupo(g)};margin-right:7px"></i>${esc(g)}</td><td class="n">${brl0(v)}</td><td class="n muted">${Math.round(v / totG * 100)}%</td></tr>`).join('')}</table>`;
  // entradas
  const ents = P.entradas.filter(e => e.valor || (comparar && e.anterior));
  if ($('#t-ent')) tabela($('#t-ent'), comparar ? ['Entrada', 'Valor', ant, 'Diferença'] : ['Entrada', 'Valor', 'Lançamentos'],
    ents.map(e => comparar ? [esc(e.nome), brl(e.valor), brl(e.anterior), `<span class="${e.valor - e.anterior < 0 ? 'neg' : 'pos'}">${sinal(e.valor - e.anterior)}</span>`] : [esc(e.nome), brl(e.valor), e.n])
      .concat([comparar ? ['Total', brl(T.renda), brl(TA.renda), sinal(T.renda - TA.renda)] : ['Total', brl(T.renda), '']]),
    comparar ? [1, 2, 3] : [1, 2], l => l[0] === 'Total' ? 'tot' : '');
  // cobranças
  const comp = {};
  P.compromissos.forEach(c => { (comp[c.mes] ||= []).push(c); });
  if ($('#t-comp')) $('#t-comp').innerHTML = Object.entries(comp).slice(0, 6).map(([m, cs]) => `<div class="cobranca">
      <div class="cobranca-topo"><b>${mesBR(m + '-01')}</b><b>${brl(cs.reduce((a, c) => a + c.valor, 0))}</b></div>
      ${cs.map(c => `<div class="cobranca-item"><span>${esc(c.descricao.replace(/ - Parcela.*| - \d+\/\d+$/, '').replace(/^Pix no Crédito - /, 'Pix no crédito: '))} <span class="muted">${c.parcela}</span></span><span>${brl(c.valor)}</span></div>`).join('')}</div>`).join('') || '<p class="muted">Nenhuma parcela futura.</p>';
  if ($('#t-top')) tabela($('#t-top'), ['Onde', 'Vezes', 'Total'], P.top.map(r => [esc(r.nome), r.n, brl(r.total)]), [1, 2]);
  if ($('#t-plano')) tabela($('#t-plano'), ['Mês', 'Renda', 'Custo de vida', 'Cartão', 'Resultado', 'Falta cobrir', 'Ainda devo', 'Saldo livre'],
    P.plano.linhas.slice(0, 4).map(l => [mesBR(l.mes + '-01'), brl0(l.renda + l.reembolsos + l.unicos), brl0(l.custo + l.aportes), brl0(l.cartao),
      `<b class="${l.resultado < 0 ? 'neg' : 'pos'}">${sinal(l.resultado)}</b>`, l.falta ? `<b class="warnc">${brl0(l.falta)}</b>` : '0', brl0(l.deve_pessoas), brl0(l.livre)]), [1, 2, 3, 4, 5, 6, 7]);
  if ($('#t-metas')) tabelaMetas($('#t-metas'), P.metas.filter(m => m.ativa), P.tipo);
  ligarDicas(t);
  t.querySelectorAll('[data-evol-cat]').forEach(el => el.onclick = () => abrirEvolucao({categoria: el.dataset.evolCat}, cat(el.dataset.evolCat)?.nome, P.tipo));
  t.querySelectorAll('[data-evol-grupo]').forEach(el => el.onclick = () => abrirEvolucao({grupo: el.dataset.evolGrupo}, el.dataset.evolGrupo, P.tipo));

  // navegação
  t.querySelectorAll('[data-ir]').forEach(b => b.onclick = () => { location.hash = '#painel?p=' + b.dataset.ir; });
  t.querySelectorAll('[data-tipo]').forEach(b => b.onclick = () => { location.hash = '#painel?p=' + trocarTipo(P, b.dataset.tipo); });
  const sa = $('#sel-ano'); if (sa) sa.onchange = () => { location.hash = '#painel?p=' + sa.value; };
  $('#comparar').onchange = e => { store.set('comparar', e.target.checked ? '1' : '0'); rota(); };
}

// Evolução de uma categoria ou grupo: barras de gasto, linha do teto e média.
async function abrirEvolucao(alvo, nome, tipo) {
  const q = new URLSearchParams({tipo, ...alvo});
  const S = await api('/api/evolucao?' + q);
  const d = $('#editor');
  const media = S.reduce((a, x) => a + x.gasto + x.parcelas, 0) / (S.length || 1);
  const W = 620, H = 250, L = 44, B = 24, T = 22, n = S.length, gw = (W - L) / n, bw = Math.max(5, Math.min(22, gw * .55));
  const max = Math.max(50, ...S.map(x => Math.max(x.gasto + x.parcelas, x.teto || 0)));
  const passo = [50, 100, 200, 250, 500, 1000, 2000, 5000].find(p => max / p <= 5) || 10000, topo = Math.ceil(max / passo) * passo;
  const y = v => T + (H - T - B) * (1 - v / topo), cx = i => L + gw * i + gw / 2;
  const rot = x => tipo === 'semana' ? `${+x.inicio.slice(8)}/${+x.inicio.slice(5, 7)}` : mesBR(x.periodo + '-01').split('/')[0];
  let s = `<svg viewBox="0 0 ${W} ${H}">`;
  for (let v = 0; v <= topo; v += passo) s += (PREF.grade !== false || v === 0 ? `<line x1="${L}" x2="${W}" y1="${y(v)}" y2="${y(v)}" stroke="var(--linha)"/>` : '') + `<text x="${L - 6}" y="${y(v) + 4}" font-size="10" text-anchor="end" fill="var(--mudo)">${v >= 1000 ? v / 1000 + 'k' : v}</text>`;
  S.forEach((x, i) => {
    const acima = x.teto != null && x.gasto > x.teto;
    const h1 = y(0) - y(x.gasto), h2 = y(0) - y(x.gasto + x.parcelas) - h1;
    if (h1 > 0) s += `<rect x="${cx(i) - bw / 2}" y="${y(x.gasto)}" width="${bw}" height="${h1}" rx="${raioBarra(bw, h1)}" fill="${acima ? 'var(--ruim)' : 'var(--s2)'}"/>`;
    if (h2 > 0) s += `<rect x="${cx(i) - bw / 2}" y="${y(x.gasto + x.parcelas)}" width="${bw}" height="${h2 - 2}" rx="2" fill="var(--mudo)" opacity=".45"/>`;
    const tot = x.gasto + x.parcelas;
    if (tot > 0) s += `<text x="${cx(i)}" y="${y(tot) - 5}" font-size="10" font-weight="600" text-anchor="middle" fill="${acima ? 'var(--ruim)' : 'var(--texto-2)'}">${tot >= 1000 ? (tot / 1000).toLocaleString('pt-BR', {maximumFractionDigits: 1}) + 'k' : Math.round(tot)}</text>`;
    s += `<rect x="${cx(i) - gw / 2}" y="${T}" width="${gw}" height="${H - T - B}" fill="transparent" data-tip="<b>${rot(x)}</b><br>Gasto ${brl(x.gasto)}${x.parcelas ? '<br>Parcelas antigas ' + brl(x.parcelas) : ''}<br>Teto ${x.teto != null ? brl(x.teto) : 'sem teto'}${acima ? `<br><b class='neg'>+${brl(x.gasto - x.teto)} acima</b>` : ''}"/>`;
    s += `<text x="${cx(i)}" y="${H - 7}" font-size="10.5" text-anchor="middle" fill="var(--texto-2)">${rot(x)}</text>`;
  });
  const tetos = S.map((x, i) => x.teto != null ? `${i ? 'L' : 'M'}${cx(i) - gw / 2},${y(x.teto)} H${cx(i) + gw / 2}` : '').join(' ');
  if (tetos.trim()) s += `<path d="${tetos}" fill="none" stroke="var(--texto)" stroke-width="2" stroke-dasharray="5 4" opacity=".55"/>`;
  s += `<line x1="${L}" x2="${W}" y1="${y(media)}" y2="${y(media)}" stroke="var(--acento)" stroke-width="1.5"/>`;
  const acimaN = S.filter(x => x.teto != null && x.gasto > x.teto).length;
  d.innerHTML = `<h3 style="margin:0 0 4px">Evolução: ${esc(nome)}</h3>
    <p class="muted">${tipo === 'semana' ? 'Últimas 12 semanas' : tipo === 'ano' ? 'Meses do ano' : 'Últimos 12 meses'} · média ${brl(media)} · acima do teto em ${acimaN} de ${n}</p>
    <div class="legend"><span><i style="background:var(--s2)"></i>Gasto</span><span><i style="background:var(--ruim)"></i>Acima do teto</span><span><i style="background:var(--mudo);opacity:.45"></i>Parcelas antigas</span>
      <span><i style="background:none;border-top:2px dashed var(--texto);height:0;border-radius:0"></i>Teto</span><span><i style="background:var(--acento);height:2px"></i>Média</span></div>
    <div class="chart">${s}</svg></div>
    <div class="barra" style="margin-top:10px"><button id="ev-x">Fechar</button>
      ${alvo.categoria ? `<a href="#lancamentos?cat=${alvo.categoria}"><button>Ver lançamentos</button></a>` : ''}</div>`;
  ligarDicas(d);
  $('#ev-x').onclick = () => d.close();
  d.querySelector('a') && (d.querySelector('a').onclick = () => d.close());
  d.showModal();
}

// Tabela "Savings": planejado, guardado e completude no período; acumulado contra o objetivo.
function tabelaMetas(el, ms, tipo) {
  if (!ms.length) { el.innerHTML = '<p class="muted">Nenhuma meta ainda. Crie em <a href="#ajustes">Ajustes</a>: reserva de emergência, uma compra planejada...</p>'; return; }
  el.innerHTML = ms.map(m => {
    const pct = m.completude_periodo != null ? Math.round(m.completude_periodo * 100) + '%' : '-';
    const alvo = m.alvo ? Math.min(m.completude_alvo || 0, 1) : null;
    return `<div class="meta-item">
      <div class="meta-topo"><b>${esc(m.nome)}</b><span class="muted">${m.onde ? esc(m.onde) : ''}${m.data_alvo ? `${m.onde ? ' · ' : ''}até ${mesBR(m.data_alvo + '-01')}` : ''}${m.por_mes_ate_prazo ? ` · ${brl0(m.por_mes_ate_prazo)}/mês para chegar` : ''}</span></div>
      <div class="meta-nums"><span>Planejado <b>${brl0(m.planejado_periodo)}</b></span><span>Guardado <b>${brl0(m.guardado_periodo)}</b></span><span>${pct}</span>
        <span>${m.falta_periodo ? `Falta <b class="warnc">${brl0(m.falta_periodo)}</b>` : '<b class="pos">cumprido</b>'}</span></div>
      ${m.alvo ? `<div class="meta-alvo"><div class="track"><div class="fill neutro" style="width:${alvo * 100}%"></div></div>
        <span>${brl0(m.guardado_total)} de ${brl0(m.alvo)} (${Math.round((m.completude_alvo || 0) * 100)}%)</span></div>`
        : `<div class="meta-alvo"><span>Acumulado ${brl0(m.guardado_total)}</span></div>`}</div>`;
  }).join('');
}

function kpiConta(c) {
  if (c.saldo_real == null)
    return `<div class="kpi"><div class="rot">Conta</div><div class="v warnc">${brl(c.saldo)}</div><div class="d">pelo extrato até ${dataBR(c.cobertura)} · <a href="#" data-saldo>informar saldo do app</a></div></div>`;
  const dif = c.diferenca, ok = Math.abs(dif) < .005;
  return `<div class="kpi"><div class="rot">Conta (saldo do app)</div><div class="v ${c.saldo_real < 100 ? 'neg' : ''}">${brl(c.saldo_real)}</div>
    <div class="d">em ${dataBR(c.data_real)}${c.data_real < hojeISO() ? ' (desatualizado)' : ''} · ${ok ? 'bate com os lançamentos' : `<b class="warnc">${brl(dif)}</b> não lançados`} · <a href="#" data-saldo>atualizar</a></div></div>`;
}
document.addEventListener('click', async e => {
  const a = e.target.closest('[data-saldo]'); if (!a) return;
  e.preventDefault();
  const v = prompt('Saldo que o app do Nubank mostra agora (ex.: 162,18):');
  if (v == null || v.trim() === '') return;
  const valor = +v.replace(/\./g, '').replace(',', '.');
  if (Number.isNaN(valor)) return alert('Valor inválido.');
  await put('/api/contas/nubank_conta/saldo', {valor, data: hojeISO()});
  rota();
});

// Entradas, gastos e poupança com o orçado por trás (o "Tracked (vs. Budget)" da planilha).
const SERIES_GRAF = [['renda', 'Entradas', 'var(--s1)', 'orc_renda'], ['gasto', 'Gastos', 'var(--s2)', 'orc_gasto'], ['poupanca', 'Poupança', 'var(--s3)', 'orc_poupanca']];
const verSeries = () => { const p = {orcado: true, renda: true, gasto: true, poupanca: true}; try { return {...p, ...JSON.parse(store.get('grafico-series', '{}'))}; } catch (_) { return p; } };
function legendaSeries() {
  const v = verSeries();
  return `<div class="legend legenda-series">${[['orcado', 'Orçado', 'var(--mudo)'], ...SERIES_GRAF].map(([k, n, cor]) =>
    `<label class="alternar"><input type="checkbox" data-serie="${k}" ${v[k] ? 'checked' : ''}><i style="background:${cor};${k === 'orcado' ? 'opacity:.35' : ''}"></i>${n}</label>`).join('')}</div>`;
}
function graficoBarras(el, S, tipo) {
  desenharNoTamanho(el, (W, H) => {
    const ver = verSeries(), ativas = SERIES_GRAF.filter(([k]) => ver[k]);
    const L = 40, B = 22, T = 8, n = S.length || 1, gw = (W - L) / n, nb = Math.max(ativas.length, 1);
    const bw = Math.max(2, gw * (FRACAO_BARRA[PREF.barras_larg] || .7) / nb), gap = nb > 1 ? Math.min(2, bw * .2) : 0;
    const max = Math.max(100, ...S.flatMap(m => ativas.flatMap(([k, , , ko]) => [m[k] || 0, ver.orcado ? m[ko] || 0 : 0])));
    const {passo, topo} = escalaY(max, 0, H - T - B);
    const y = v => T + (H - T - B) * (1 - v / topo);
    const rot = m => tipo === 'semana' ? `${+m.inicio.slice(8)}/${+m.inicio.slice(5, 7)}` : mesBR(m.mes + '-01').split('/')[0];
    let s = `<svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="img" aria-label="Entradas, gastos e poupança">`;
    for (let v = 0; v <= topo; v += passo) s += (PREF.grade !== false || v === 0 ? `<line x1="${L}" x2="${W}" y1="${y(v)}" y2="${y(v)}" stroke="var(--linha)"/>` : '')
      + `<text x="${L - 6}" y="${y(v) + 4}" font-size="10" text-anchor="end" fill="var(--mudo)">${kRot(v)}</text>`;
    S.forEach((m, i) => {
      const cx = L + gw * i + gw / 2, x0 = cx - (nb * bw + (nb - 1) * gap) / 2;
      ativas.forEach(([k, , cor, ko], j) => {
        const x = x0 + j * (bw + gap);
        if (ver.orcado && m[ko] > 0) s += barra(x, y(0), y(0) - y(m[ko]), bw, cor, 'opacity=".28"');
        s += barra(x, y(0), y(0) - y(Math.max(m[k] || 0, 0)), bw, cor);
      });
      const linhas = ativas.map(([k, nome, , ko]) => `${nome} ${brl(m[k] || 0)}${ver.orcado ? ` <span class='muted'>de ${brl(m[ko] || 0)}</span>` : ''}`).join('<br>');
      s += `<rect x="${cx - gw / 2}" y="${T}" width="${gw}" height="${H - T - B}" fill="transparent" data-tip="<b>${tipo === 'semana' ? 'semana de ' + dataBR(m.inicio) : mesBR(m.mes + '-01')}</b><br>${linhas}<br>Resultado <b class='${m.resultado < 0 ? 'neg' : 'pos'}'>${brl(m.resultado)}</b>"/>`;
      if (n <= 12 || i % 2 === 0) s += `<text x="${cx}" y="${H - 7}" font-size="10.5" text-anchor="middle" fill="var(--texto-2)">${rot(m)}</text>`;
    });
    el.innerHTML = s + '</svg>';
  });
}

// ---------------------------------------------------------------- pendentes
function descreverPartes(ps) {
  return ps.map(p => (p.categoria ? cat(p.categoria)?.nome : p.pessoa ? 'acerto ' + (pessoa(p.pessoa)?.nome || '') : p.meta ? 'meta ' + (meta(p.meta)?.nome || '') : NAT[p.natureza]) + (ps.length > 1 ? ' ' + brl(p.valor) : '')).join(' + ');
}
const parteOk = p => !((p.natureza === 'gasto' || p.natureza === 'renda') && !p.categoria) && !(p.natureza === 'acerto' && !p.pessoa) && !(p.natureza === 'poupanca' && !p.meta);

async function pendentes(t) {
  const L = await api('/api/lancamentos?pendentes=true');
  t.innerHTML = `<div class="titulo"><h2>Pendentes</h2><span class="muted">${L.length ? `${L.length} esperando você` : 'tudo classificado'}</span></div>
    <section class="painel vidro">
    <p class="sub">Um toque classifica. Nada com pessoa é classificado sozinho: o sistema só sugere, e você confirma.</p>
    <label class="alternar"><input type="checkbox" id="lembrar" checked> sugerir a mesma classificação da próxima vez para o mesmo lugar</label>
    <div id="lista"></div></section>`;
  const lista = $('#lista');
  L.sort((a, b) => Math.abs(b.valor) - Math.abs(a.valor)).forEach(l => lista.appendChild(itemPendente(l)));
}

function itemPendente(l) {
  const div = document.createElement('div');
  div.className = 'pendente';
  const conhecidas = l.partes.filter(parteOk);
  const poupSemMeta = l.partes.find(p => p.natureza === 'poupanca' && !p.meta);
  const falta = Math.round((l.valor - conhecidas.reduce((a, p) => a + p.valor, 0)) * 100) / 100;
  const tipo = falta < 0 ? 'gasto' : 'renda';
  const cats = V.categorias.filter(c => c.tipo === tipo);
  const grupos = [...new Set(cats.map(c => c.grupo))];
  const pergunta = (p => p && (p.motivo || p.obs))(l.partes.find(p => !parteOk(p)));
  div.innerHTML = `<div class="topo"><div><div class="nome">${esc(l.contraparte || l.descricao)}</div>
      <div class="muted">${dataBR(l.data)} · ${CONTA[l.conta] || l.conta} · ${esc(l.descricao)}${l.parcela ? ' · parcela ' + l.parcela : ''}${ORIGEM[l.origem] ? ' · ' + ORIGEM[l.origem] : ''}${l.nota ? ' · ' + esc(l.nota) : ''}</div>
      ${conhecidas.length ? `<div class="muted">já separado: ${conhecidas.map(p => `<span class="chip">${esc(p.motivo || p.obs || NAT[p.natureza])} ${brl(p.valor)}</span>`).join('')}</div>` : ''}
      ${pergunta ? `<div class="muted">${esc(pergunta)}</div>` : ''}</div>
      <div class="valor ${l.valor < 0 ? 'neg' : 'pos'}">${brl(falta)}</div></div>
    <div class="sugs">${l.sugestao ? `<button class="prim" data-sug="1">Sugestão: ${esc(descreverPartes(l.sugestao))}</button>` : ''}
      ${poupSemMeta ? V.metas.filter(m => m.ativa).map(m => `<button class="prim" data-m="${m.id}">Meta: ${esc(m.nome)}</button>`).join('') || '<a href="#ajustes">crie uma meta em Ajustes</a>' : ''}
      ${[...cats].sort((a, b) => b.uso - a.uso).slice(0, 6).map(c => `<button data-c="${c.id}">${esc(c.nome)}</button>`).join('')}
      ${V.pessoas.filter(p => p.tipo !== 'credor').slice(0, 3).map(p => `<button data-p="${p.id}">Acerto: ${esc(p.nome)}</button>`).join('')}
      <button data-mais="1">outras...</button><button data-e="1">Dividir...</button>
      <span class="todas" hidden>${grupos.map(g => `<span class="grupo-rot">${esc(g)}</span>` + cats.filter(c => c.grupo === g).map(c => `<button data-c="${c.id}">${esc(c.nome)}</button>`).join('')).join('')}
      <span class="grupo-rot">Não é ${tipo} seu</span>${V.pessoas.map(p => `<button data-p="${p.id}">Acerto: ${esc(p.nome)}</button>`).join('')}
      <button data-t="1">Transferência entre contas suas</button>
      ${V.metas.filter(m => m.ativa).map(m => `<button data-m="${m.id}">${falta < 0 ? 'Guardar em' : 'Resgate de'}: ${esc(m.nome)}</button>`).join('')}</span></div>`;
  div.addEventListener('click', async e => {
    const b = e.target.closest('button'); if (!b) return;
    if (b.dataset.e) return abrirEditor(l, () => div.remove());
    if (b.dataset.mais) { const s = div.querySelector('.todas'); s.hidden = !s.hidden; b.textContent = s.hidden ? 'outras...' : 'menos'; return; }
    let partes, lembrar = false;
    if (b.dataset.sug) partes = l.sugestao;
    else if (b.dataset.m && poupSemMeta) partes = l.partes.map(p => p === poupSemMeta ? {...p, meta: +b.dataset.m} : p);
    else {
      const nova = b.dataset.c ? {natureza: tipo, categoria: b.dataset.c} : b.dataset.p ? {natureza: 'acerto', pessoa: b.dataset.p}
        : b.dataset.m ? {natureza: 'poupanca', meta: +b.dataset.m} : {natureza: 'transferencia'};
      partes = [...conhecidas, {valor: falta, obs: '', ...nova}];
      lembrar = $('#lembrar').checked && partes.length === 1;
    }
    b.disabled = true;
    try { await put(`/api/lancamentos/${l.id}/partes`, {partes, lembrar}); div.remove(); contarPendentes(); }
    catch (err) { alert(err.message); b.disabled = false; }
  });
  return div;
}

// ---------------------------------------------------------------- editor de partes
function abrirEditor(l, aoSalvar) {
  const d = $('#editor');
  let partes = l.partes.length ? l.partes.map(p => ({...p})) : l.sugestao ? l.sugestao.map(p => ({...p}))
    : [{valor: l.valor, natureza: l.valor < 0 ? 'gasto' : 'renda', categoria: null, pessoa: null, obs: ''}];
  let nota = l.nota || '';
  const opcoesCat = tipo => V.categorias.filter(c => c.tipo === tipo).map(c => `<option value="${c.id}">${esc(c.grupo)}: ${esc(c.nome)}</option>`).join('');
  function desenhar() {
    const soma = Math.round(partes.reduce((a, p) => a + (+p.valor || 0), 0) * 100) / 100;
    d.innerHTML = `<h3 style="margin:0 0 4px">${esc(l.contraparte || l.descricao)}</h3>
      <p class="muted">${dataBR(l.data)} · ${CONTA[l.conta]} · ${esc(l.descricao)} · <b>${brl(l.valor)}</b>${ORIGEM[l.origem] ? ' · ' + ORIGEM[l.origem] : ''}</p>
      <label class="c" style="margin-bottom:6px">Obs<input id="ed-nota" value="${esc(nota)}" placeholder="sua observação sobre este lançamento"></label>
      ${partes.map((p, i) => `<div class="parte" data-i="${i}">
        <input type="number" step="0.01" value="${p.valor}" data-k="valor">
        <select data-k="natureza">${Object.entries(NAT).map(([k, n]) => `<option value="${k}" ${p.natureza === k ? 'selected' : ''}>${n}</option>`).join('')}</select>
        ${p.natureza === 'acerto' ? `<select data-k="pessoa"><option value="">pessoa...</option>${V.pessoas.map(x => `<option value="${x.id}" ${p.pessoa === x.id ? 'selected' : ''}>${esc(x.nome)}</option>`).join('')}</select>`
          : p.natureza === 'poupanca' ? `<select data-k="meta"><option value="">meta...</option>${V.metas.map(x => `<option value="${x.id}" ${p.meta === x.id ? 'selected' : ''}>${esc(x.nome)}</option>`).join('')}</select>`
          : p.natureza === 'transferencia' ? '<span class="muted" style="align-self:center">entre contas suas</span>'
          : `<select data-k="categoria"><option value="">categoria...</option>${opcoesCat(p.natureza)}</select>`}
        <input value="${esc(p.obs || '')}" data-k="obs" placeholder="obs desta parte">
        <button data-rm="${i}" title="remover">x</button>
        ${p.motivo ? `<span class="motivo" title="por que o sistema classificou ou sugeriu assim">${esc(p.motivo)}</span>` : ''}</div>`).join('')}
      <div class="barra"><button id="ed-add">+ parte</button>
        <span class="${Math.abs(soma - l.valor) > .005 ? 'neg' : 'muted'}">soma ${brl(soma)} de ${brl(l.valor)}</span></div>
      <label class="alternar"><input type="checkbox" id="ed-lembrar"> sugerir isto da próxima vez para o mesmo lugar (só com uma parte)</label>
      <div class="barra" style="margin-top:12px"><button class="prim" id="ed-ok">Salvar</button><button id="ed-x">Cancelar</button>
        ${['manual', 'push'].includes(l.origem) ? '<button id="ed-del">Apagar lançamento</button>' : ''}</div><p class="erro" id="ed-erro"></p>`;
    d.querySelectorAll('.parte').forEach(row => {
      const i = +row.dataset.i;
      const sel = row.querySelector('[data-k=categoria]'); if (sel) sel.value = partes[i].categoria || '';
      row.querySelectorAll('[data-k]').forEach(inp => inp.addEventListener('change', () => {
        partes[i][inp.dataset.k] = ['valor', 'meta'].includes(inp.dataset.k) ? (inp.value === '' ? null : +inp.value) : (inp.value || null);
        if (inp.dataset.k === 'natureza') { partes[i].categoria = null; partes[i].pessoa = null; partes[i].meta = null; }
        if (['natureza', 'categoria', 'pessoa', 'meta'].includes(inp.dataset.k)) partes[i].motivo = '';   // agora a escolha é sua
        desenhar();
      }));
    });
    $('#ed-nota').oninput = e => { nota = e.target.value; };
    d.querySelectorAll('[data-rm]').forEach(b => b.onclick = () => { partes.splice(+b.dataset.rm, 1); desenhar(); });
    $('#ed-add').onclick = () => { partes.push({valor: Math.round((l.valor - soma) * 100) / 100, natureza: 'gasto', categoria: null, pessoa: null, obs: ''}); desenhar(); };
    $('#ed-x').onclick = () => d.close();
    $('#ed-ok').onclick = async () => {
      try { await put(`/api/lancamentos/${l.id}/partes`, {partes, nota, lembrar: $('#ed-lembrar').checked && partes.length === 1}); d.close(); aoSalvar && aoSalvar(); contarPendentes(); }
      catch (e) { $('#ed-erro').textContent = e.message; }
    };
    const db = $('#ed-del');
    if (db) db.onclick = async () => { if (confirm('Apagar este lançamento?')) { await del(`/api/lancamentos/${l.id}`); d.close(); aoSalvar && aoSalvar(); } };
  }
  desenhar();
  d.showModal();
}

// ---------------------------------------------------------------- lançamentos (como o Budget Tracking da planilha)
function tipoLanc(l) {
  if (l.pendente) return ['pend', 'Pendente'];
  const nats = new Set(l.partes.map(p => p.natureza));
  if (nats.size > 1) return ['acerto', 'Dividido'];
  const n = [...nats][0];
  if (n === 'poupanca') return ['transf', 'Poupança'];
  return n === 'renda' ? ['entrada', 'Entrada'] : n === 'gasto' ? (l.valor > 0 ? ['entrada', 'Estorno'] : ['saida', 'Saída']) : n === 'transferencia' ? ['transf', 'Transferência'] : ['acerto', 'Acerto'];
}
async function lancamentos(t) {
  const [meses, contas] = await Promise.all([api('/api/meses'), api('/api/contas')]);
  t.innerHTML = `<div class="titulo"><h2>Lançamentos</h2></div>
    <section class="painel vidro"><h3>Resumo <small>do que está filtrado abaixo</small></h3><div class="heroi lanc-heroi" id="lanc-heroi"></div></section>
    <section class="painel vidro">
    <div class="barra"><select id="f-mes"><option value="">todos os meses</option>${meses.map(m => `<option value="${m}">${MESES[+m.slice(5) - 1]} de ${m.slice(0, 4)}</option>`).join('')}</select>
      <select id="f-cat"><option value="">todas as categorias</option>${V.categorias.map(c => `<option value="${c.id}">${esc(c.nome)}</option>`).join('')}</select>
      <select id="f-tipo"><option value="">todos os tipos</option><option>Entrada</option><option>Saída</option><option>Transferência</option><option>Acerto</option><option>Dividido</option><option>Estorno</option><option>Poupança</option><option>Pendente</option></select>
      <input id="f-busca" placeholder="buscar" style="flex:1;min-width:140px"><button id="f-limpar">Limpar filtros</button></div>
    <div class="scroll"><table id="t-l"></table></div></section>`;
  $('#f-mes').value = params().get('cat') ? '' : (params().get('mes') ?? meses[0] ?? '');
  if (params().get('cat')) $('#f-cat').value = params().get('cat');
  let dados = [];
  async function carregar() {
    const p = new URLSearchParams();
    if ($('#f-mes').value) p.set('mes', $('#f-mes').value);
    if ($('#f-cat').value) p.set('categoria', $('#f-cat').value);
    if ($('#f-busca').value) p.set('busca', $('#f-busca').value);
    if ($('#f-tipo').value === 'Pendente') p.set('pendentes', 'true');
    dados = (await api('/api/lancamentos?' + p)).filter(l => !$('#f-tipo').value || tipoLanc(l)[1] === $('#f-tipo').value);
    const ps = dados.flatMap(l => l.partes);
    const ent = ps.filter(p => p.natureza === 'renda').reduce((a, p) => a + p.valor, 0), gas = -ps.filter(p => p.natureza === 'gasto').reduce((a, p) => a + p.valor, 0);
    const nEnt = dados.filter(l => l.partes.some(p => p.natureza === 'renda')).length, nGas = dados.filter(l => l.partes.some(p => p.natureza === 'gasto')).length;
    // Falta lançar: diferença entre o saldo que o app mostra e o calculado pelos lançamentos (a mesma do Painel).
    const conta = contas.find(c => c.id === 'nubank_conta'), falta = conta?.saldo_real != null ? conta.diferenca : null, bate = falta != null && Math.abs(falta) < .005;
    $('#lanc-heroi').innerHTML = `
      <div><div class="rot">Entradas</div><div class="grande">${brl(ent)}</div><div class="muted">${nEnt} lançamento(s)</div></div>
      <div><div class="rot">Gastos</div><div class="grande">${brl(gas)}</div><div class="muted">${nGas} lançamento(s)</div></div>
      <div><div class="rot">Resultado</div><div class="grande ${ent - gas < 0 ? 'neg' : 'pos'}">${sinal(ent - gas)}</div>
        <div class="muted">${dados.length} lançamento(s) · ${dados.filter(l => l.pendente).length} pendente(s)</div></div>
      <div><div class="rot">Falta lançar na conta</div><div class="grande ${falta == null ? 'muted' : bate ? 'pos' : 'warnc'}">${falta == null ? '?' : brl(Math.abs(falta))}</div>
        <div class="muted">${falta == null ? '<a href="#" data-saldo>informe o saldo do app</a>' : bate ? 'o saldo do app bate com os lançamentos'
          : `${falta < 0 ? 'gasto' : 'entrada'} que o app já mostra e ainda não entrou aqui · saldo do app ${brl(conta.saldo_real)} em ${dataBR(conta.data_real)} · <a href="#" data-saldo>atualizar</a>`}</div></div>`;
    tabela($('#t-l'), ['Data', 'Tipo', 'Categoria', 'Valor', 'Detalhes', 'Conta', 'Saldo da conta'], dados.map(l => {
      const [cls, nome] = tipoLanc(l);
      return [`<span class="nw">${dataCurta(l.data)}</span>`, `<span class="tipo ${cls}">${nome}</span>`,
        l.pendente ? '<span class="muted">a classificar</span>' : l.partes.map(p => `<span class="chip">${esc(p.categoria ? cat(p.categoria)?.nome : p.pessoa ? pessoa(p.pessoa)?.nome : p.meta ? 'meta ' + meta(p.meta)?.nome : NAT[p.natureza])}${l.partes.length > 1 ? ' ' + brl(p.valor) : ''}</span>`).join(''),
        `<b class="${l.valor > 0 ? 'pos' : ''}">${brl(l.valor)}</b>`,
        `${esc(l.contraparte || l.descricao)}<div class="muted">${[l.contraparte ? esc(l.descricao) : '', l.parcela ? 'parcela ' + l.parcela : '', ORIGEM[l.origem] || '', l.nota ? `<span class="obs-lanc">${esc(l.nota)}</span>` : ''].filter(Boolean).join(' · ')}</div>`,
        `<span class="nw">${CONTA[l.conta] || l.conta}</span>`, `<span class="nw ${l.saldo_conta < 0 ? 'neg' : ''}">${brl(l.saldo_conta)}</span>`];
    }), [3, 6], () => 'click');
    $('#t-l').querySelectorAll('tbody tr').forEach((tr, i) => tr.onclick = () => dados[i] && abrirEditor(dados[i], carregar));
    linhaNova();
  }
  // Linha vazia acima do lançamento mais recente: digitar e Enter, como na planilha.
  const TIPOS_NOVO = {saida: 'Saída', entrada: 'Entrada', guardar: 'Guardar em meta', resgatar: 'Resgatar de meta', paguei: 'Acerto: paguei', recebi: 'Acerto: recebi', transf: 'Transferência'};
  function opcoesAlvo(tipo) {
    if (tipo === 'saida' || tipo === 'entrada') return V.categorias.filter(c => c.tipo === (tipo === 'saida' ? 'gasto' : 'renda'))
      .map(c => `<option value="${c.id}">${esc(c.grupo)}: ${esc(c.nome)}</option>`).join('');
    if (tipo === 'guardar' || tipo === 'resgatar') return V.metas.filter(m => m.ativa).map(m => `<option value="${m.id}">${esc(m.nome)}</option>`).join('') || '<option value="">crie uma meta</option>';
    if (tipo === 'paguei' || tipo === 'recebi') return V.pessoas.map(p => `<option value="${p.id}">${esc(p.nome)}</option>`).join('');
    return '<option value="">entre contas suas</option>';
  }
  function linhaNova() {
    const tb = $('#t-l tbody');
    tb.insertAdjacentHTML('afterbegin', `<tr class="nova"><td><input type="date" id="n-data" value="${hojeISO()}"></td>
      <td><select id="n-tipo">${Object.entries(TIPOS_NOVO).map(([k, n]) => `<option value="${k}">${n}</option>`).join('')}</select></td>
      <td><select id="n-alvo">${opcoesAlvo('saida')}</select></td>
      <td class="n"><input type="number" step="0.01" min="0" id="n-valor" placeholder="0,00" style="width:100px;text-align:right"></td>
      <td><input id="n-desc" placeholder="o que foi (Enter lança)" style="width:100%"></td>
      <td><select id="n-conta">${V.contas.map(c => `<option value="${c.id}">${esc(CONTA[c.id] || c.nome)}</option>`).join('')}</select></td>
      <td><button class="prim" id="n-ok">Lançar</button></td></tr>`);
    $('#n-tipo').onchange = () => { $('#n-alvo').innerHTML = opcoesAlvo($('#n-tipo').value); };
    const lancar = async () => {
      const tipo = $('#n-tipo').value, v = Math.abs(+$('#n-valor').value), alvo = $('#n-alvo').value, desc = $('#n-desc').value.trim();
      if (!v || !desc) return alert('Preencha o valor e o que foi.');
      const saida = ['saida', 'guardar', 'paguei'].includes(tipo) || (tipo === 'transf' && !confirm('A transferência ENTROU nesta conta? (Cancelar = saiu)'));
      const valor = saida ? -v : v;
      const parte = tipo === 'saida' ? {natureza: 'gasto', categoria: alvo} : tipo === 'entrada' ? {natureza: 'renda', categoria: alvo}
        : tipo === 'guardar' || tipo === 'resgatar' ? {natureza: 'poupanca', meta: +alvo || null}
        : tipo === 'paguei' || tipo === 'recebi' ? {natureza: 'acerto', pessoa: alvo} : {natureza: 'transferencia'};
      try {
        await post('/api/lancamentos', {data: $('#n-data').value, conta: $('#n-conta').value, valor, descricao: desc,
          partes: [{valor, obs: '', ...parte}]});
        carregar(); contarPendentes();
      } catch (e) { alert(e.message); }
    };
    $('#n-ok').onclick = e => { e.stopPropagation(); lancar(); };
    $('#n-desc').onkeydown = e => { if (e.key === 'Enter') lancar(); };
    $('#n-valor').onkeydown = e => { if (e.key === 'Enter') lancar(); };
    tb.querySelector('tr.nova').onclick = e => e.stopPropagation();
  }
  // Limpar: todos os meses, categorias e tipos, sem busca (e tira o filtro que veio no endereço, ex.: da evolução).
  const filtrado = () => ['f-mes', 'f-cat', 'f-tipo', 'f-busca'].some(id => $('#' + id).value);
  const marcarLimpar = () => { $('#f-limpar').disabled = !filtrado(); };
  $('#f-limpar').onclick = () => {
    ['f-mes', 'f-cat', 'f-tipo', 'f-busca'].forEach(id => { $('#' + id).value = ''; });
    if (location.hash.includes('?')) history.replaceState(null, '', '#lancamentos');
    marcarLimpar(); carregar();
  };
  ['f-mes', 'f-cat', 'f-tipo'].forEach(id => $('#' + id).onchange = () => { marcarLimpar(); carregar(); });
  let tm; $('#f-busca').oninput = () => { marcarLimpar(); clearTimeout(tm); tm = setTimeout(carregar, 300); };
  marcarLimpar();
  carregar();
}

// ---------------------------------------------------------------- importar e lançar à mão
async function importar(t) {
  t.innerHTML = `<div class="titulo"><h2>Importar e lançar</h2></div>
    <section class="painel vidro"><h3>Extrato e fatura do banco <small>Nubank ou Bradesco · .pdf, .csv ou .xlsx</small></h3>
      <p class="sub">Quantos quiser de uma vez. O que já existe (mesmo arquivo de novo, ou o que veio pelo celular) não duplica. Extrato que não fecha com o total do banco é recusado. A fatura em aberto do Bradesco é imagem e é lida por OCR: leva uns segundos por página e só entra se cada cartão fechar com o total impresso. Para lançar algo à mão, use a primeira linha da tela <a href="#lancamentos">Lançamentos</a>.</p>
      <label class="drop" id="drop">Solte os arquivos aqui ou toque para escolher<input type="file" id="arq" multiple accept=".pdf,.csv,.xlsx" hidden></label>
      <div class="scroll" style="margin-top:10px"><table id="t-res"></table></div></section>
    <section class="painel vidro"><h3>Notificações descartadas pelo filtro <small>se alguma era compra, resgate</small></h3><div class="scroll"><table id="t-ign"></table></div></section>
    <section class="painel vidro"><h3>Últimas importações</h3><div class="scroll"><table id="t-imp"></table></div></section>`;
  const drop = $('#drop'), arq = $('#arq');
  ['dragover', 'dragenter'].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.add('sobre'); }));
  ['dragleave', 'drop'].forEach(ev => drop.addEventListener(ev, () => drop.classList.remove('sobre')));
  drop.addEventListener('drop', e => { e.preventDefault(); enviar(e.dataTransfer.files); });
  arq.onchange = () => enviar(arq.files);
  async function enviar(files) {
    const fd = new FormData();
    [...files].forEach(f => fd.append('arquivos', f));
    drop.firstChild.textContent = 'Lendo...';
    const r = await post('/api/importar', fd);
    drop.firstChild.textContent = 'Solte mais arquivos aqui ou toque para escolher';
    tabela($('#t-res'), ['Arquivo', 'Tipo', 'Novos', 'Casados com o celular', 'Já existiam', 'Observação'], r.map(x =>
      [esc(x.arquivo), x.tipo || '', x.novos ?? '', x.casados ?? '', x.repetidos ?? '', x.erro ? `<span class="erro">${esc(x.erro)}</span>` : esc((x.avisos || []).join('; '))]), [2, 3, 4]);
    carregarListas(); contarPendentes();
  }
  async function carregarListas() {
    const ign = await api('/api/ignorados');
    tabela($('#t-ign'), ['Quando', 'Motivo', 'Texto', ''], ign.map(i => [i.quando.slice(0, 16), esc(i.motivo), esc(i.title + ' | ' + i.body), `<button data-r="${i.id}">resgatar</button>`]));
    $('#t-ign').querySelectorAll('[data-r]').forEach(b => b.onclick = async () => { await post(`/api/ignorados/${b.dataset.r}/resgatar`, {}); carregarListas(); contarPendentes(); });
    const imp = await api('/api/importacoes');
    tabela($('#t-imp'), ['Quando', 'Arquivo', 'Tipo', 'Novos', 'Casados', 'Já existiam'], imp.map(i => [i.quando.slice(0, 16), esc(i.arquivo), i.tipo, i.novos, i.casados, i.repetidos]), [3, 4, 5]);
  }
  carregarListas();
}

// ---------------------------------------------------------------- pessoas
async function pessoas(t) {
  const [P, L] = await Promise.all([api('/api/painel'), api('/api/lancamentos')]);
  t.innerHTML = `<div class="titulo"><h2>Pessoas</h2><span class="muted">positivo: a pessoa te deve · negativo: você deve a ela</span></div>
    <div class="grade">
    <section class="painel vidro"><h3>Saldos</h3><div class="scroll"><table id="t-p"></table></div></section>
    <section class="painel vidro"><h3>Alguém pagou uma conta por você</h3>
      <p class="sub">Condomínio, Copel, gás, mercado da casa: o gasto é seu, o dinheiro saiu de outra pessoa. Vira gasto na categoria e dívida com ela, sem mexer no saldo da conta.</p>
      <form class="linha" id="f-pago">
        <label class="c">Data<input type="date" name="data" required></label>
        <label class="c">Quem pagou<select name="pessoa">${V.pessoas.map(p => `<option value="${p.id}">${esc(p.nome)}</option>`).join('')}</select></label>
        <label class="c">Sua parte (R$)<input type="number" step="0.01" min="0.01" name="valor" required></label>
        <label class="c">Categoria<select name="categoria">${V.categorias.filter(c => c.tipo === 'gasto').map(c => `<option value="${c.id}">${esc(c.nome)}</option>`).join('')}</select></label>
        <label class="c">O que foi<input name="descricao" required placeholder="Copel de novembro"></label>
        <button class="prim">Lançar</button></form></section>
    </div>
    <section class="painel vidro"><h3>Acertos recentes</h3><div class="scroll"><table id="t-ac"></table></div></section>`;
  $('#f-pago').data.value = hojeISO();
  $('#f-pago').onsubmit = async e => {
    e.preventDefault();
    const f = Object.fromEntries(new FormData(e.target)), v = +f.valor, nome = pessoa(f.pessoa).nome;
    await post('/api/lancamentos', {data: f.data, conta: 'nubank_conta', valor: 0, descricao: f.descricao, contraparte: nome,
      partes: [{valor: -v, natureza: 'gasto', categoria: f.categoria, motivo: 'conta paga por ' + nome}, {valor: v, natureza: 'acerto', pessoa: f.pessoa, motivo: nome + ' pagou por você'}]});
    rota();
  };
  tabela($('#t-p'), ['Pessoa', 'Saldo', 'Situação', 'Parcelas a vencer'], P.pessoas.filter(p => p.saldo || p.a_vencer).map(p =>
    [esc(p.nome), `<b class="${p.saldo < 0 ? 'neg' : 'pos'}">${brl(p.saldo)}</b>`, p.saldo < 0 ? 'você deve' : 'te deve', p.a_vencer ? brl(p.a_vencer) : '']), [1, 3]);
  const ac = L.flatMap(l => l.partes.filter(p => p.natureza === 'acerto').map(p => ({l, p}))).slice(0, 60);
  tabela($('#t-ac'), ['Data', 'Pessoa', 'Lançamento', 'Valor', 'Obs'], ac.map(({l, p}) =>
    [dataCurta(l.data), esc(pessoa(p.pessoa)?.nome || ''), esc(l.contraparte || l.descricao), brl(p.valor), esc([l.nota, p.obs, p.motivo].filter(Boolean).join(' · '))]), [3]);
}

// ---------------------------------------------------------------- projeção
const TIPO_EV = {renda_mensal: 'Renda mensal muda', gasto_mensal: 'Gasto mensal muda', entrada_unica: 'Entrada única', saida_unica: 'Saída única'};
async function plano(t) {
  const [P, prm, evs] = await Promise.all([api('/api/painel'), api('/api/parametros'), api('/api/eventos')]);
  const pl = P.plano, L = pl.linhas, fim = L[L.length - 1] || {};
  const quitado = L.find(l => l.deve_pessoas === 0);
  t.innerHTML = `<div class="titulo"><h2>Projeção até ${mesBR(pl.horizonte + '-01')}</h2><span class="muted">renda, custo de vida e aportes de cada mês vêm do <a href="#orcamento">Orçamento</a>, mais os eventos</span></div>
    <div class="mosaico" id="mosaico">
    ${cartao('proj-resumo', 'Resumo', '', `<div class="heroi" style="grid-template-columns:repeat(3,minmax(0,1fr))">
      <div><div class="rot">Falta cobrir no período</div><div class="grande ${pl.falta_total ? 'warnc' : 'pos'}">${brl0(pl.falta_total)}</div><div class="muted">soma dos meses no vermelho</div></div>
      <div><div class="rot">Quem você deve, quitado em</div><div class="grande">${quitado ? mesBR(quitado.mes + '-01') : 'não quita'}</div></div>
      <div><div class="rot">Saldo livre em ${mesBR(pl.horizonte + '-01')}</div><div class="grande ${(fim.livre || 0) > 0 ? 'pos' : 'warnc'}">${brl0(fim.livre)}</div><div class="muted">${brl0(fim.metas)} nas metas</div></div></div>`)}
    ${cartao('proj-grafico', 'Resultado mês a mês', 'cartão congelado', `<div class="legend"><span><i style="background:var(--ok)"></i>Sobra</span><span><i style="background:var(--ruim)"></i>Falta</span><span><i style="background:var(--acento);height:3px"></i>Saldo livre acumulado</span></div><div class="chart grafico" id="ch-proj"></div>`)}
    ${cartao('proj-premissas', 'Premissas', '', `<form class="linha" id="f-prm">
        <label class="c">Renda mensal base<input type="number" step="0.01" name="salario_mensal" value="${prm.salario_mensal}"></label>
        <label class="c">Horizonte (AAAA-MM)<input name="horizonte" value="${pl.horizonte}"></label>
        <label class="c">Taxa da ponte do PicPay<input type="number" step="0.001" name="taxa_ponte_picpay" value="${prm.taxa_ponte_picpay}"></label>
        <button class="prim">Recalcular</button></form>
      <p class="sub" style="margin-top:8px">Renda base = padrão do salário no <a href="#orcamento">Orçamento</a>. Custo de vida e aportes = orçado de cada mês. Reembolsos = parcelas que alguém te deve.</p>`)}
    ${cartao('proj-tabela', 'Mês a mês', '', '<div class="scroll"><table id="t-pl"></table></div>')}
    ${cartao('proj-eventos', 'Eventos', 'o que muda e quando', `<div class="scroll"><table id="t-ev" class="compacta"></table></div>
      <h3 style="margin-top:14px">Novo evento</h3>
      <form class="linha" id="f-ev">
        <label class="c">Nome<input name="nome" required placeholder="Estágio, bolsa nova, viagem..."></label>
        <label class="c">Tipo<select name="tipo">${Object.entries(TIPO_EV).map(([k, n]) => `<option value="${k}">${n}</option>`).join('')}</select></label>
        <label class="c">A partir de (AAAA-MM)<input name="inicio" required placeholder="2027-07"></label>
        <label class="c">Até (opcional)<input name="fim"></label>
        <label class="c">Valor (+ aumenta, - diminui)<input type="number" step="0.01" name="valor" required></label>
        <button class="prim">Adicionar</button></form>`)}
    </div>`;
  tabela($('#t-pl'), ['Mês', 'Renda', 'Reemb.', 'Únicos', 'Custo', 'Cartão', 'Metas', 'Resultado', 'Falta', 'Devo', 'Livre'],
    L.map(l => [`<b class="nw">${mesBR(l.mes + '-01')}</b>`, brl0(l.renda), brl0(l.reembolsos), l.unicos ? sinal(l.unicos) : '0', brl0(l.custo), brl0(l.cartao), brl0(l.aportes),
      `<b class="${l.resultado < 0 ? 'neg' : 'pos'}">${sinal(l.resultado)}</b>`, l.falta ? `<b class="warnc">${brl0(l.falta)}</b>` : '0', brl0(l.deve_pessoas), brl0(l.livre)]), [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]);
  // gráfico: barras do resultado do mês e linha do saldo livre acumulado
  desenharNoTamanho($('#ch-proj'), (W, H) => {
    const Lm = 46, B = 22, Tp = 10, n = L.length || 1, gw = (W - Lm) / n, bw = Math.max(4, gw * (FRACAO_BARRA[PREF.barras_larg] || .7) * .8);
    const vals = L.flatMap(l => [l.resultado, l.livre]);
    const {passo, topo, base} = escalaY(Math.max(100, ...vals), Math.min(0, ...vals), H - Tp - B);
    const y = v => Tp + (H - Tp - B) * (topo - v) / (topo - base || 1), cx = i => Lm + gw * i + gw / 2;
    let g = `<svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}">`;
    for (let v = base; v <= topo; v += passo) g += (PREF.grade !== false || v === 0 ? `<line x1="${Lm}" x2="${W}" y1="${y(v)}" y2="${y(v)}" stroke="var(--linha)" ${v === 0 ? 'stroke-width="1.6"' : ''}/>` : '')
      + `<text x="${Lm - 6}" y="${y(v) + 4}" font-size="10" text-anchor="end" fill="var(--mudo)">${kRot(v)}</text>`;
    L.forEach((l, i) => {
      const y0 = y(0), y1 = y(l.resultado), r = raioBarra(bw, Math.abs(y1 - y0));
      g += `<rect x="${cx(i) - bw / 2}" y="${Math.min(y0, y1)}" width="${bw}" height="${Math.max(Math.abs(y1 - y0), 1)}" rx="${r}" fill="${l.resultado < 0 ? 'var(--ruim)' : 'var(--ok)'}"/>`;
      // valor na ponta da barra: acima da positiva, abaixo da negativa
      const txt = Math.abs(l.resultado) >= 1000 ? (l.resultado / 1000).toLocaleString('pt-BR', {maximumFractionDigits: 1}) + 'k' : String(Math.round(l.resultado));
      g += `<text x="${cx(i)}" y="${l.resultado < 0 ? y1 + 12 : y1 - 4}" font-size="${gw < 30 ? 8.5 : 10}" font-weight="600" text-anchor="middle" fill="${l.resultado < 0 ? 'var(--ruim)' : 'var(--ok)'}">${txt}</text>`;
      g += `<rect x="${cx(i) - gw / 2}" y="${Tp}" width="${gw}" height="${H - Tp - B}" fill="transparent" data-tip="<b>${mesBR(l.mes + '-01')}</b><br>Resultado ${brl(l.resultado)}<br>Falta ${brl(l.falta)}<br>Saldo livre ${brl(l.livre)}"/>`;
      if (gw >= 34 || i % 2 === 0) g += `<text x="${cx(i)}" y="${H - 6}" font-size="10" text-anchor="middle" fill="var(--texto-2)">${mesBR(l.mes + '-01')}</text>`;
    });
    if (L.length) g += `<path d="${L.map((l, i) => `${i ? 'L' : 'M'}${cx(i)},${y(l.livre)}`).join(' ')}" fill="none" stroke="var(--acento)" stroke-width="2.5"/>`;
    $('#ch-proj').innerHTML = g + '</svg>';
  });
  ligarDicas(t);
  // eventos
  tabela($('#t-ev'), ['Ativo', 'Evento', 'Tipo', 'De', 'Até', 'Valor', ''], evs.map(e => [
    `<input type="checkbox" data-ev="${e.id}" data-k="ativo" ${e.ativo ? 'checked' : ''}>`, `<input data-ev="${e.id}" data-k="nome" value="${esc(e.nome)}" style="width:170px">`,
    `<span class="nw">${TIPO_EV[e.tipo]}</span>`, `<input data-ev="${e.id}" data-k="inicio" value="${e.inicio}" style="width:80px">`, `<input data-ev="${e.id}" data-k="fim" value="${e.fim || ''}" style="width:80px">`,
    `<input type="number" step="0.01" data-ev="${e.id}" data-k="valor" value="${e.valor}" style="width:90px">`, `<button data-rm-ev="${e.id}">apagar</button>`]), [5]);
  t.querySelectorAll('[data-ev]').forEach(i => i.onchange = async () => {
    const e = evs.find(x => x.id === +i.dataset.ev), k = i.dataset.k;
    const v = k === 'ativo' ? i.checked : k === 'valor' ? +i.value : (i.value || null);
    try { await put('/api/eventos/' + e.id, {...e, ativo: !!e.ativo, [k]: v}); rota(); } catch (err) { alert(err.message); }
  });
  t.querySelectorAll('[data-rm-ev]').forEach(b => b.onclick = async () => { if (confirm('Apagar este evento?')) { await del('/api/eventos/' + b.dataset.rmEv); rota(); } });
  $('#f-ev').onsubmit = async e => {
    e.preventDefault();
    const f = Object.fromEntries(new FormData(e.target));
    try { await post('/api/eventos', {...f, valor: +f.valor, fim: f.fim || null}); rota(); } catch (err) { alert(err.message); }
  };
  $('#f-prm').onsubmit = async e => { e.preventDefault(); for (const [k, v] of new FormData(e.target)) await put('/api/parametros/' + k, {valor: v}); rota(); };
}

// ---------------------------------------------------------------- orçamento (Budget Planning e Despesas Fixas da planilha)
const ICONE_LIXO = '<svg viewBox="0 0 16 16" width="12" height="12" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><path d="M2.5 4h11M6 4V2.5h4V4M4 4l.7 9.5h6.6L12 4"/></svg>';
const lixeira = (attr, id, titulo) => `<button class="botao-icone apagar" ${attr}="${esc(id)}" title="${titulo}" aria-label="${titulo}">${ICONE_LIXO}</button>`;
const numEd = v => v == null ? '' : String(Math.round(v * 100) / 100).replace('.', ',');
const numVer = v => v == null ? '' : (Math.round(v) || 0).toLocaleString('pt-BR');
function lerNum(s) {
  s = String(s).trim().replace(/^R\$\s*/, '');
  if (!s) return null;
  const v = s.includes(',') ? +s.replace(/\./g, '').replace(',', '.') : +s;
  return Number.isFinite(v) ? v : NaN;
}
const pontoCor = (cor, attr, id) => `<label class="ponto" style="background:${cor}" title="Escolher a cor"><input type="color" ${attr}="${esc(id)}" value="${cor}"></label>`;
const MODOS_ORC = [['orcado', 'Orçado'], ['realizado', 'Realizado'], ['diferenca', 'Diferença']];

async function orcamento(t) {
  const ano = +(params().get('ano') || new Date().getFullYear());
  const modo = store.get('orc-modo', 'orcado'), repetir = store.get('orc-repetir', '0') === '1';
  const [G, MS] = await Promise.all([api('/api/orcamento?ano=' + ano), api('/api/metas')]);
  V = await api('/api/vocabulario');
  const M = G.meses, atual = hojeISO().slice(0, 7), mesRef = M.includes(atual) ? atual : M[0];
  const renda = G.linhas.filter(l => l.tipo === 'renda'), gasto = G.linhas.filter(l => l.tipo === 'gasto');
  const poup = G.linhas.filter(l => l.tipo === 'poupanca' && (l.ativa || M.some(m => l.orcado[m] || l.realizado[m])));
  const grupos = [...new Set(gasto.map(l => l.grupo))];
  const futuro = m => m > atual;
  // Diferença: positivo é sempre a favor (gastou menos que o orçado, recebeu ou guardou mais).
  const val = (l, m) => modo === 'orcado' ? l.orcado[m] : futuro(m) ? null : modo === 'realizado' ? l.realizado[m]
    : l.tipo === 'gasto' ? (l.orcado[m] || 0) - l.realizado[m] : l.realizado[m] - (l.orcado[m] || 0);
  const soma = (ls, m) => ls.reduce((a, l) => a + (val(l, m) || 0), 0);
  const total = (ls, extra = () => 0) => m => modo !== 'orcado' && futuro(m) ? null : soma(ls, m) + extra(m);
  const alocar = (m, k) => [renda, gasto, poup].reduce((a, ls, i) => a + (i ? -1 : 1) * ls.reduce((b, l) => b + (l[k][m] || 0), 0), 0)
    - (k === 'realizado' ? G.parcelas[m] : 0);
  const alocarVal = m => modo === 'orcado' ? alocar(m, 'orcado') : futuro(m) ? null
    : modo === 'realizado' ? alocar(m, 'realizado') : alocar(m, 'realizado') - alocar(m, 'orcado');
  const fmt = v => v == null ? '' : (modo === 'diferenca' && v > .5 ? '+' : '') + numVer(v);
  const corDif = v => modo === 'diferenca' && v != null ? (v < -.5 ? 'neg' : v > .5 ? 'pos' : '') : '';
  const corSinal = v => v == null ? '' : v < -.5 ? 'neg' : v > .5 ? 'pos' : '';
  const anual = f => { const vs = M.map(f).filter(v => v != null); return vs.length ? vs.reduce((a, b) => a + b, 0) : null; };
  const celulas = (f, cor = corDif) => M.map(m => { const v = f(m); return `<td class="n ${m === atual ? 'atual' : ''} ${cor(v)}">${fmt(v)}</td>`; }).join('')
    + (v => `<td class="n ano ${cor(v)}">${fmt(v)}</td>`)(anual(f));
  const dicaPadrao = l => l.tipo === 'poupanca' ? 'padrão: aporte mensal da meta' : l.tipo === 'renda' ? (l.chave === 'salario' ? 'padrão: renda base' : 'sem padrão')
    : l.por_itens ? 'padrão: soma das despesas fixas' : 'padrão: teto da categoria';
  const linhaCat = l => {
    const nome = `<span class="nome-orc">${l.tipo === 'poupanca' ? '<i class="ponto" style="background:var(--s-poup)"></i>' : pontoCor(corCat(l.chave), 'data-cor-cat', l.chave)}
      <span>${esc(l.nome)}</span>${l.por_itens ? '<small class="etiqueta" title="orçada pela soma das despesas fixas">itens</small>' : ''}</span>`;
    if (modo !== 'orcado') return `<tr class="cat-orc"><td>${nome}</td>${celulas(m => val(l, m))}</tr>`;
    return `<tr class="cat-orc"><td>${nome}</td>${M.map(m => {
      const def = l.definido.includes(m);
      return `<td class="n ${m === atual ? 'atual' : ''}"><input class="cel ${def ? 'def' : 'pad'}" inputmode="decimal" data-orc="${esc(l.chave)}" data-mes="${m}"
        value="${numEd(l.orcado[m])}" placeholder="–" title="${def ? 'valor deste mês; apague para voltar ao padrão' : dicaPadrao(l)}"></td>`;
    }).join('')}<td class="n ano">${numVer(anual(m => l.orcado[m]))}</td></tr>`;
  };
  const linhaGrupo = g => `<tr class="grp-orc"><td><span class="nome-orc">${pontoCor(corGrupo(g), 'data-cor-grupo', g)}<span>${esc(g)}</span></span></td>${celulas(total(gasto.filter(l => l.grupo === g)))}</tr>`;
  const sec = (cls, nome) => `<tr class="sec-orc ${cls}"><td colspan="${M.length + 2}">${nome}</td></tr>`;
  const parcelas = modo === 'realizado' && M.some(m => G.parcelas[m])
    ? `<tr class="cat-orc"><td><span class="nome-orc"><i class="ponto" style="background:var(--mudo)"></i><span>Parcelas de compras antigas</span></span></td>${celulas(m => futuro(m) ? null : G.parcelas[m])}</tr>` : '';
  const grade = `<table class="grade-orc"><thead><tr><th>${ano}</th>${M.map(m => `<th class="n ${m === atual ? 'atual' : ''}">${MES3[+m.slice(5) - 1]}</th>`).join('')}<th class="n ano">Ano</th></tr></thead><tbody>
    <tr class="alocar"><td>A alocar</td>${celulas(alocarVal, corSinal)}</tr>
    ${sec('renda', 'Entradas')}${renda.map(linhaCat).join('')}<tr class="tot-orc renda"><td>Total de entradas</td>${celulas(total(renda))}</tr>
    ${sec('gasto', 'Gastos')}${grupos.map(g => linhaGrupo(g) + gasto.filter(l => l.grupo === g).map(linhaCat).join('')).join('')}${parcelas}
    <tr class="tot-orc gasto"><td>Total de gastos</td>${celulas(total(gasto, m => modo === 'realizado' ? G.parcelas[m] : 0))}</tr>
    ${sec('poup', 'Poupança')}${poup.length ? poup.map(linhaCat).join('') : `<tr><td colspan="${M.length + 2}" class="muted">Nenhuma meta ativa.</td></tr>`}
    <tr class="tot-orc poup"><td>Total poupado</td>${celulas(total(poup))}</tr></tbody></table>`;

  // despesas fixas: itens por categoria; a soma do mês pode ser o orçamento da categoria
  const comItens = gasto.filter(l => l.itens.length), mr = MES3[+mesRef.slice(5) - 1];
  const fixas = `<div class="scroll"><table class="compacta fixas"><thead><tr><th>Item</th><th class="n">Valor mensal</th><th>De</th><th>Até</th><th></th></tr></thead><tbody>
    ${comItens.length ? comItens.map(l => {
      const s = l.soma_itens[mesRef], o = l.orcado[mesRef], pelaSoma = l.por_itens && !l.definido.includes(mesRef);
      const resumo = pelaSoma ? `${mr}: <b>${brl(s)}</b> é o orçamento` : o == null ? `${mr}: itens <b>${brl(s)}</b> · sem orçamento`
        : `${mr}: itens <b>${brl(s)}</b> de ${brl(o)} orçados · sobra <b class="${o - s < 0 ? 'neg' : ''}">${brl(o - s)}</b>`;
      return `<tr class="fixa-cab"><td colspan="5"><div class="fixa-topo"><span class="nome-orc"><i class="ponto" style="background:${corCat(l.chave)}"></i><b>${esc(l.nome)}</b><small class="muted">${esc(l.grupo)}</small></span>
          <span class="muted">${resumo}</span>
          <label class="alternar"><input type="checkbox" data-por-itens="${esc(l.chave)}" ${l.por_itens ? 'checked' : ''}> usar a soma como orçamento</label></div></td></tr>`
        + l.itens.map(i => `<tr><td><input data-item="${i.id}" data-k="nome" value="${esc(i.nome)}" style="width:100%;min-width:150px"></td>
          <td class="n"><input data-item="${i.id}" data-k="valor" inputmode="decimal" value="${numEd(i.valor)}" style="width:96px;text-align:right"></td>
          <td><input data-item="${i.id}" data-k="inicio" value="${i.inicio || ''}" placeholder="sempre" style="width:86px"></td>
          <td><input data-item="${i.id}" data-k="fim" value="${i.fim || ''}" placeholder="sem fim" style="width:86px"></td>
          <td>${lixeira('data-rm-item', i.id, 'Apagar item')}</td></tr>`).join('');
    }).join('') : '<tr><td colspan="5" class="muted">Nenhum item ainda.</td></tr>'}</tbody></table></div>
    <form class="linha" id="f-item" style="margin-top:10px">
      <label class="c">Categoria<select name="categoria" required>${grupos.map(g => `<optgroup label="${esc(g)}">${gasto.filter(l => l.grupo === g)
        .map(l => `<option value="${esc(l.chave)}">${esc(l.nome)}</option>`).join('')}</optgroup>`).join('')}</select></label>
      <label class="c">Item<input name="nome" required placeholder="Aluguel, internet, academia..."></label>
      <label class="c">Valor mensal<input name="valor" inputmode="decimal" required></label>
      <label class="c">De (AAAA-MM, opcional)<input name="inicio" pattern="\\d{4}-\\d{2}"></label>
      <label class="c">Até (opcional)<input name="fim" pattern="\\d{4}-\\d{2}"></label>
      <button class="prim">Adicionar</button></form>`;

  const todosGrupos = [...new Set(V.categorias.map(c => c.grupo))];
  t.innerHTML = `<div class="titulo"><h2>Orçamento</h2><span class="muted">quanto você planeja receber, gastar e guardar em cada mês</span></div>
    <div class="periodo vidro">
      <button class="seta" data-ano="${ano - 1}" aria-label="Ano anterior">‹</button><span class="rotulo-periodo">${ano}</span><button class="seta" data-ano="${ano + 1}" aria-label="Próximo ano">›</button>
      <div class="segmentos">${MODOS_ORC.map(([k, n]) => `<button data-modo="${k}" class="${modo === k ? 'on' : ''}">${n}</button>`).join('')}</div>
      ${modo === 'orcado' ? `<label class="alternar"><input type="checkbox" id="orc-repetir" ${repetir ? 'checked' : ''}> ao editar um mês, repetir até dezembro</label>` : ''}
      <span class="espaco"></span>
      <span class="muted legenda-orc">${modo === 'orcado' ? '<span class="pad">cinza</span> = padrão · <b>escuro</b> = valor do mês' : modo === 'diferenca' ? '+ = a favor' : 'pelo que entrou nos lançamentos'}</span>
    </div>
    <div class="mosaico" id="mosaico">
    ${cartao('orc-grade', 'Planejamento mensal', '', `<div class="scroll grade-orc-wrap">${grade}</div>`)}
    ${cartao('orc-fixas', 'Despesas fixas', 'o que você planeja gastar em cada categoria', fixas)}
    ${cartao('orc-cats', 'Categorias', 'teto vazio = sem teto · fixa = não entra no "ainda pode gastar"', `
      <div class="subsecao">Cores dos grupos</div>
      <div class="cores-grupos">${todosGrupos.map(g => `<span class="chip-cor">${pontoCor(corGrupo(g), 'data-cor-grupo', g)}${esc(g)}</span>`).join('')}</div>
      <div class="subsecao">Gastos</div><div class="scroll"><table id="t-cats" class="compacta"></table></div>
      <div class="subsecao">Renda</div><div class="scroll"><table id="t-cats-renda" class="compacta"></table></div>
      <div class="subsecao">Nova categoria</div>
      <form class="linha" id="f-cat">
        <label class="c">Nome<input name="nome" required></label>
        <label class="c">Grupo<input name="grupo" list="grupos" required></label>
        <label class="c">Tipo<select name="tipo"><option value="gasto">gasto</option><option value="renda">renda</option></select></label>
        <label class="c">Teto mensal<input type="number" step="1" name="teto"></label>
        <label class="c"><span><input type="checkbox" name="fixa"> fixa</span></label>
        <button class="prim">Criar</button></form>
      <datalist id="grupos">${todosGrupos.map(g => `<option value="${esc(g)}">`).join('')}</datalist>`)}
    ${cartao('orc-metas', 'Metas de poupança', 'objetivo, prazo e quanto guardar por mês', `
      <p class="sub">Guarde numa conta separada (Caixinha ou CDB de liquidez diária). Aporte na Caixinha entra como poupança; para usar o dinheiro, o resgate desconta da meta e a compra entra como gasto. Se não quiser descontar, não ligue o resgate à meta.</p>
      <div class="scroll"><table id="t-metas-aj" class="compacta"></table></div>
      <form class="linha" id="f-meta" style="margin-top:10px">
        <label class="c">Nome<input name="nome" required placeholder="Reserva de emergência"></label>
        <label class="c">Objetivo (R$)<input type="number" step="0.01" name="alvo"></label>
        <label class="c">Prazo (AAAA-MM)<input name="data_alvo" pattern="\\d{4}-\\d{2}"></label>
        <label class="c">Aporte mensal planejado<input type="number" step="0.01" name="aporte_mensal" value="0"></label>
        <label class="c">Onde fica<input name="onde" placeholder="Caixinha Nubank"></label>
        <button class="prim">Criar meta</button></form>`)}
    </div>`;

  // re-renderiza mantendo a rolagem da grade e o foco na célula em que você estava
  const redesenhar = async () => {
    const a = document.activeElement, alvo = a?.dataset?.orc ? `.cel[data-orc="${CSS.escape(a.dataset.orc)}"][data-mes="${a.dataset.mes}"]` : null;
    const x = $('.grade-orc-wrap')?.scrollLeft || 0;
    await rota();
    const w = $('.grade-orc-wrap'); if (w) w.scrollLeft = x;
    const n = alvo && t.querySelector(alvo); if (n) { n.focus(); n.select(); }
  };
  t.querySelectorAll('[data-ano]').forEach(b => b.onclick = () => { location.hash = '#orcamento?ano=' + b.dataset.ano; });
  t.querySelectorAll('[data-modo]').forEach(b => b.onclick = () => { store.set('orc-modo', b.dataset.modo); rota(); });
  if ($('#orc-repetir')) $('#orc-repetir').onchange = e => store.set('orc-repetir', e.target.checked ? '1' : '0');
  const cels = [...t.querySelectorAll('.cel')];
  cels.forEach(i => {
    i.onchange = async () => {
      const v = lerNum(i.value);
      if (Number.isNaN(v)) { i.classList.add('invalido'); i.title = 'Número inválido'; return; }
      await put('/api/orcamento', {chave: i.dataset.orc, mes: i.dataset.mes, valor: v, ate_dezembro: repetir});
      redesenhar();
    };
    // Enter desce para a mesma coluna na linha de baixo, como na planilha
    i.onkeydown = e => {
      if (e.key !== 'Enter') return;
      e.preventDefault();
      const prox = cels.slice(cels.indexOf(i) + 1).find(c => c.dataset.mes === i.dataset.mes);
      prox ? prox.focus() : i.blur();
      prox?.select();
    };
  });
  t.querySelectorAll('[data-cor-cat]').forEach(i => i.onchange = async () => { await put('/api/categorias/' + i.dataset.corCat, {cor: i.value}); redesenhar(); });
  t.querySelectorAll('[data-cor-grupo]').forEach(i => i.onchange = async () => {
    await put('/api/parametros/cores_grupos', {valor: JSON.stringify({...(V.cores_grupos || {}), [i.dataset.corGrupo]: i.value})}); redesenhar();
  });
  t.querySelectorAll('[data-limpar-cor]').forEach(b => b.onclick = async () => { await put('/api/categorias/' + b.dataset.limparCor, {limpar_cor: true}); redesenhar(); });
  t.querySelectorAll('[data-por-itens]').forEach(i => i.onchange = async () => { await put('/api/categorias/' + i.dataset.porItens, {orcar_por_itens: i.checked}); redesenhar(); });
  // itens das despesas fixas
  const itens = Object.fromEntries(gasto.flatMap(l => l.itens).map(i => [i.id, i]));
  t.querySelectorAll('[data-item]').forEach(i => i.onchange = async () => {
    const it = itens[i.dataset.item], k = i.dataset.k;
    const v = k === 'valor' ? lerNum(i.value) : (i.value.trim() || null);
    if (k === 'valor' && (v == null || Number.isNaN(v))) { i.classList.add('invalido'); return; }
    try { await put('/api/itens-fixos/' + it.id, {categoria: it.categoria, nome: it.nome, valor: it.valor, inicio: it.inicio, fim: it.fim, [k]: v}); redesenhar(); }
    catch (err) { alert(err.message); }
  });
  t.querySelectorAll('[data-rm-item]').forEach(b => b.onclick = async () => { if (confirm('Apagar este item?')) { await del('/api/itens-fixos/' + b.dataset.rmItem); redesenhar(); } });
  $('#f-item').onsubmit = async e => {
    e.preventDefault();
    const f = Object.fromEntries(new FormData(e.target)), v = lerNum(f.valor);
    if (v == null || Number.isNaN(v)) return alert('Valor inválido.');
    try { await post('/api/itens-fixos', {categoria: f.categoria, nome: f.nome, valor: v, inicio: f.inicio || null, fim: f.fim || null}); redesenhar(); }
    catch (err) { alert(err.message); }
  };
  // categorias
  const corCel = c => pontoCor(corCat(c.id), 'data-cor-cat', c.id) + (c.cor ? ` <button class="mini" data-limpar-cor="${esc(c.id)}" title="Voltar à cor do grupo">do grupo</button>` : '');
  tabela($('#t-cats'), ['Cor', 'Grupo', 'Categoria', 'Teto mensal', 'Fixa', 'Uso', ''], V.categorias.filter(c => c.tipo === 'gasto').map(c => [corCel(c),
    `<input data-cat="${c.id}" data-k="grupo" value="${esc(c.grupo)}" list="grupos" style="width:120px">`,
    `<input data-cat="${c.id}" data-k="nome" value="${esc(c.nome)}" style="width:230px">`,
    `<input type="number" step="1" data-cat="${c.id}" data-k="teto" value="${c.teto ?? ''}" style="width:80px">`,
    `<input type="checkbox" data-cat="${c.id}" data-k="fixa" ${c.fixa ? 'checked' : ''}>`, c.uso, lixeira('data-apagar-cat', c.id, 'Apagar categoria')]), [5]);
  tabela($('#t-cats-renda'), ['Cor', 'Grupo', 'Categoria', 'Uso', ''], V.categorias.filter(c => c.tipo === 'renda').map(c => [corCel(c),
    `<input data-cat="${c.id}" data-k="grupo" value="${esc(c.grupo)}" list="grupos" style="width:120px">`,
    `<input data-cat="${c.id}" data-k="nome" value="${esc(c.nome)}" style="width:230px">`, c.uso, lixeira('data-apagar-cat', c.id, 'Apagar categoria')]), [3]);
  t.querySelectorAll('#t-cats [data-cor-cat], #t-cats-renda [data-cor-cat]').forEach(i => i.onchange = async () => { await put('/api/categorias/' + i.dataset.corCat, {cor: i.value}); redesenhar(); });
  t.querySelectorAll('#t-cats [data-limpar-cor], #t-cats-renda [data-limpar-cor]').forEach(b => b.onclick = async () => { await put('/api/categorias/' + b.dataset.limparCor, {limpar_cor: true}); redesenhar(); });
  t.querySelectorAll('[data-cat]').forEach(i => i.onchange = async () => {
    const k = i.dataset.k, corpo = k === 'fixa' ? {fixa: i.checked} : k === 'teto' ? (i.value === '' ? {limpar_teto: true} : {teto: +i.value}) : {[k]: i.value};
    await put('/api/categorias/' + i.dataset.cat, corpo); redesenhar();
  });
  t.querySelectorAll('[data-apagar-cat]').forEach(b => b.onclick = () => apagarCategoria(cat(b.dataset.apagarCat)));
  $('#f-cat').onsubmit = async e => {
    e.preventDefault();
    const f = new FormData(e.target);
    try { await post('/api/categorias', {nome: f.get('nome'), grupo: f.get('grupo'), tipo: f.get('tipo'), teto: f.get('teto') ? +f.get('teto') : null, fixa: f.get('fixa') === 'on'}); rota(); }
    catch (err) { alert(err.message); }
  };
  // metas
  tabela($('#t-metas-aj'), ['Ativa', 'Meta', 'Objetivo', 'Prazo', 'Aporte/mês', 'Onde', 'Guardado', ''], MS.map(m => [
    `<input type="checkbox" data-meta="${m.id}" data-k="ativa" ${m.ativa ? 'checked' : ''}>`, `<input data-meta="${m.id}" data-k="nome" value="${esc(m.nome)}" style="width:180px">`,
    `<input type="number" step="0.01" data-meta="${m.id}" data-k="alvo" value="${m.alvo ?? ''}" style="width:100px">`, `<input data-meta="${m.id}" data-k="data_alvo" value="${m.data_alvo || ''}" style="width:85px">`,
    `<input type="number" step="0.01" data-meta="${m.id}" data-k="aporte_mensal" value="${m.aporte_mensal}" style="width:90px">`, `<input data-meta="${m.id}" data-k="onde" value="${esc(m.onde)}" style="width:130px">`,
    brl(m.guardado_total), m.guardado_total ? '' : lixeira('data-rm-meta', m.id, 'Apagar meta')]), [6]);
  t.querySelectorAll('[data-meta]').forEach(i => i.onchange = async () => {
    const m = MS.find(x => x.id === +i.dataset.meta), k = i.dataset.k;
    const v = k === 'ativa' ? i.checked : ['alvo', 'aporte_mensal'].includes(k) ? (i.value === '' ? null : +i.value) : (i.value || null);
    await put('/api/metas/' + m.id, {nome: m.nome, descricao: m.descricao, alvo: m.alvo, data_alvo: m.data_alvo, aporte_mensal: m.aporte_mensal, onde: m.onde, ativa: !!m.ativa, [k]: k === 'aporte_mensal' ? (v || 0) : v});
    redesenhar();
  });
  t.querySelectorAll('[data-rm-meta]').forEach(b => b.onclick = async () => { if (!confirm('Apagar esta meta?')) return; try { await del('/api/metas/' + b.dataset.rmMeta); rota(); } catch (e) { alert(e.message); } });
  $('#f-meta').onsubmit = async e => {
    e.preventDefault();
    const f = Object.fromEntries(new FormData(e.target));
    await post('/api/metas', {nome: f.nome, alvo: f.alvo ? +f.alvo : null, data_alvo: f.data_alvo || null, aporte_mensal: +f.aporte_mensal || 0, onde: f.onde});
    rota();
  };
}

// ---------------------------------------------------------------- ajustes
const opcao = (rotulo, k, valores) => `<div class="opcao"><span class="rot">${rotulo}</span><div class="segmentos">${valores.map(([v, n]) =>
  `<button data-pref="${k}" data-v="${v}" class="${String(PREF[k]) === String(v) ? 'on' : ''}">${n}</button>`).join('')}</div></div>`;
async function ajustes(t) {
  const [papeis, prm, cel, ods, aparelho] = await Promise.all([api('/api/papeis'), api('/api/parametros'), api('/api/celular'), api('/api/exportar.ods/estado'), APP ? APP.ajustes() : null]);
  V = await api('/api/vocabulario');
  // Você e os colegas, mesmo quem ainda não tem parte (0%).
  const rateio = Object.fromEntries(['eu', ...V.pessoas.filter(p => p.tipo === 'colega').map(p => p.id)].map(k => [k, 0]));
  Object.assign(rateio, JSON.parse(prm.aluguel_rateio || '{}'));
  t.innerHTML = `<div class="titulo"><h2>Ajustes</h2></div>
    <section class="painel vidro"><h3>Aparência</h3>
      <div class="barra"><span class="muted">Tema</span><div class="segmentos"><button data-th="light" class="${store.get('tema', 'light') !== 'dark' ? 'on' : ''}">Claro</button><button data-th="dark" class="${store.get('tema') === 'dark' ? 'on' : ''}">Escuro</button></div>
        <button id="rever-tour">Rever o tour</button></div>
      <div class="papeis" id="papeis">
        <div class="papel ${!papeis.atual ? 'on' : ''}" data-papel=""><span>sem papel de parede</span></div>
        ${papeis.papeis.map(p => `<div class="papel ${p === papeis.atual ? 'on' : ''}" data-papel="${esc(p)}" style="background-image:url('/papel/${encodeURIComponent(p)}')"><span>${esc(p)}</span><button data-rm-papel="${esc(p)}">apagar</button></div>`).join('')}
        <label class="papel" style="place-items:center;cursor:pointer"><span style="background:none;color:var(--texto-2)">+ enviar imagem</span><input type="file" id="novo-papel" accept="image/*" hidden></label>
      </div></section>

    <section class="painel vidro"><h3>Visualização <small>vale para este aparelho</small></h3>
      <div class="opcoes">
        ${opcao('Largura da página', 'largura', [['reduzida', 'Reduzida'], ['total', 'Total']])}
        ${opcao('Densidade', 'densidade', [['compacta', 'Compacta'], ['confortavel', 'Confortável']])}
        ${opcao('Tamanho da fonte', 'fonte', [['pequena', 'Pequena'], ['media', 'Média'], ['grande', 'Grande']])}

        ${opcao('Estilo dos painéis', 'estilo', [['vidro', 'Vidro'], ['solido', 'Sólido'], ['contorno', 'Contorno'], ['plano', 'Plano']])}
        ${opcao('Cantos', 'cantos', [['redondos', 'Arredondados'], ['retos', 'Retos']])}
        ${opcao('Barras dos gráficos', 'barras', [['arredondadas', 'Arredondadas'], ['retas', 'Retas']])}
        ${opcao('Largura das barras', 'barras_larg', [['finas', 'Finas'], ['medias', 'Médias'], ['largas', 'Largas']])}
        ${opcao('Grade dos gráficos', 'grade', [[true, 'Mostrar'], [false, 'Esconder']])}

        ${opcao('Categorias', 'agrupar', [[true, 'Agrupadas'], [false, 'Lista única']])}
        ${opcao('Ordenar por', 'ordenar', [['excesso', 'Excesso'], ['uso', '% do teto'], ['valor', 'Valor'], ['nome', 'Nome']])}
        ${opcao('Grupos', 'grupos', [['auto', 'Abrir os estourados'], ['abertos', 'Todos abertos'], ['fechados', 'Todos fechados']])}
        ${opcao('Categorias sem gasto', 'vazias', [[false, 'Esconder'], [true, 'Mostrar']])}
      </div>
      <div class="barra" style="margin-top:10px"><span class="muted">Painéis do painel:</span>
        ${[['grafico', 'Entradas e gastos'], ['composicao', 'Para onde foi'], ['entradas', 'Entradas do período'], ['metas', 'Poupança e metas'], ['cobrancas', 'Próximas cobranças'], ['destinos', 'Maiores destinos'], ['plano', 'Projeção']]
          .map(([k, n]) => `<label class="alternar"><input type="checkbox" data-painel="${k}" ${PREF.paineis[k] ? 'checked' : ''}> ${n}</label>`).join('')}</div>
      <div class="subsecao" style="margin-top:12px">Ordem das abas <small class="muted">também dá para arrastar no menu</small></div>
      <div class="ordem-abas" id="ordem-abas"></div>
      <div class="barra"><button id="pref-padrao">Voltar ao padrão</button><button id="abas-padrao">Ordem padrão das abas</button><button id="mosaico-padrao">Restaurar disposição dos painéis</button>
        <span class="muted">Arraste cada painel pela alça ao lado do título; o canto de baixo à direita muda largura e altura (duplo clique volta à altura automática).</span></div></section>

    <div class="grade meio">
    <section class="painel vidro"><h3>Pessoas <small>como o nome aparece no extrato e o que sugerir</small></h3>
      <div class="scroll"><table id="t-pes" class="compacta"></table></div>
      <form class="linha" id="f-pes" style="margin-top:10px">
        <label class="c">Nome<input name="nome" required></label>
        <label class="c">Nome no extrato<input name="apelido_extrato" placeholder="FULANO DE TAL"></label>
        <label class="c">Tipo<select name="tipo"><option>colega</option><option>familia</option><option>credor</option><option>outro</option></select></label>
        <button class="prim">Adicionar</button></form></section>
    <section class="painel vidro"><h3>Rateio do aluguel <small>sugestão para o boleto da imobiliária</small></h3>
      <form class="linha" id="f-rateio">${Object.entries(rateio).map(([k, v]) => `<label class="c">${esc(k === 'eu' ? 'Você' : pessoa(k)?.nome || k)} (%)<input type="number" step="0.1" name="${esc(k)}" value="${(v * 100).toFixed(1)}"></label>`).join('')}
        <button class="prim">Salvar</button></form><p class="sub" id="rateio-msg"></p></section>
    </div>

    <div class="grade meio">
    ${aparelho ? cartaoAparelho(aparelho) : `<section class="painel vidro"><h3>Celular <small>app Finanças ou MacroDroid</small></h3>
      <p class="sub">Abra esta tela no celular. No app Finanças, copie o endereço e a chave. No MacroDroid, copie os três campos de baixo para a ação "Requisição HTTP" da macro.</p>
      ${[['Endereço do servidor (app Finanças)', cel.base], ['Chave (app Finanças)', cel.chave], ['URL (método POST)', cel.url], ['Cabeçalho Authorization', cel.authorization], ['Corpo (application/json)', cel.corpo]]
        .map(([k, v], i) => `<label class="c">${k}<span class="barra" style="margin:2px 0 8px"><input readonly value="${esc(v)}" style="flex:1" id="cel${i}"><button data-copiar="cel${i}">copiar</button></span></label>`).join('')}</section>`}
    <section class="painel vidro"><h3>Planilha e sessão</h3>
      <p class="sub">No modelo da planilha antiga (.ods): Budget Dashboard, Planning com o orçamento de cada mês, Tracking com renda, gasto e poupança (pendentes em âmbar), Despesas Fixas, e depois as tabelas do site em abas. A simples (.xlsx) tem só as tabelas.</p>
      <div class="barra"><button id="baixar-ods" class="prim" ${ods.disponivel ? '' : 'disabled'}>Baixar no modelo antigo (.ods)</button><a href="/api/exportar.xlsx"><button>Baixar tabelas (.xlsx)</button></a>${APP ? '' : '<button id="sair">Sair</button>'}</div>
      <p class="sub" id="ods-msg">${ods.disponivel ? '' : 'O modelo antigo (.ods) não sai aqui: ' + esc(ods.motivo) + '. A .xlsx funciona.'}</p></section>
    </div>`;

  const sugeridas = ['acerto', ...V.categorias.map(c => `${c.tipo}:${c.id}`)];
  // pessoas
  const opt = (sel) => sugeridas.map(s => `<option value="${s}" ${s === sel ? 'selected' : ''}>${s === 'acerto' ? 'acerto' : cat(s.split(':')[1])?.nome}</option>`).join('');
  tabela($('#t-pes'), ['Nome', 'No extrato', 'Quando entra', 'Quando sai'], V.pessoas.map(p => [
    `<input data-pes="${p.id}" data-k="nome" value="${esc(p.nome)}" style="width:140px">`, `<input data-pes="${p.id}" data-k="apelido_extrato" value="${esc(p.apelido_extrato)}" style="width:170px">`,
    `<select data-pes="${p.id}" data-k="sugere_entrada">${opt(p.sugere_entrada)}</select>`, `<select data-pes="${p.id}" data-k="sugere_saida">${opt(p.sugere_saida)}</select>`]));
  t.querySelectorAll('[data-pes]').forEach(i => i.onchange = async () => {
    const p = V.pessoas.find(x => x.id === i.dataset.pes);
    await put('/api/pessoas/' + p.id, {...p, [i.dataset.k]: i.value}); V = await api('/api/vocabulario');
  });
  $('#f-pes').onsubmit = async e => { e.preventDefault(); try { await post('/api/pessoas', Object.fromEntries(new FormData(e.target))); rota(); } catch (err) { alert(err.message); } };
  $('#f-rateio').onsubmit = async e => {
    e.preventDefault();
    const r = Object.fromEntries([...new FormData(e.target)].map(([k, v]) => [k, Math.round(+v * 10) / 1000]));
    const soma = Object.values(r).reduce((a, b) => a + b, 0);
    if (Math.abs(soma - 1) > .001) return ($('#rateio-msg').textContent = `A soma dá ${(soma * 100).toFixed(1)}%; precisa dar 100%.`);
    await put('/api/parametros/aluguel_rateio', {valor: JSON.stringify(r)}); $('#rateio-msg').textContent = 'Salvo.';
  };
  // visualização
  t.querySelectorAll('[data-pref]').forEach(b => b.onclick = () => {
    const v = b.dataset.v; salvarPref(b.dataset.pref, v === 'true' ? true : v === 'false' ? false : v);
    if (b.dataset.pref === 'grupos') store.set('grupos-abertos', '{}');
    rota();
  });
  t.querySelectorAll('[data-painel]').forEach(i => i.onchange = () => salvarPref('paineis', {...PREF.paineis, [i.dataset.painel]: i.checked}));
  $('#mosaico-padrao').onclick = () => { restaurarMosaicos(); alert('Disposição dos painéis restaurada.'); };
  const listaAbas = () => {
    const o = ordemAbas(), nome = h => $(`#nav a[href="${h}"]`).firstChild.textContent.trim();
    $('#ordem-abas').innerHTML = o.map((h, i) => `<span class="aba-item"><button class="mini" data-aba-mover="${i}" data-d="-1" ${i ? '' : 'disabled'} aria-label="Mover para a esquerda">&lsaquo;</button>${esc(nome(h))}<button class="mini" data-aba-mover="${i}" data-d="1" ${i < o.length - 1 ? '' : 'disabled'} aria-label="Mover para a direita">&rsaquo;</button></span>`).join('');
    $('#ordem-abas').querySelectorAll('[data-aba-mover]').forEach(b => b.onclick = () => {
      const o2 = ordemAbas(), i = +b.dataset.abaMover, j = i + +b.dataset.d;
      [o2[i], o2[j]] = [o2[j], o2[i]]; aplicarOrdemAbas(o2); listaAbas();
    });
  };
  listaAbas();
  $('#abas-padrao').onclick = () => { aplicarOrdemAbas([...ABAS_PADRAO]); listaAbas(); };
  $('#pref-padrao').onclick = () => { PREF = JSON.parse(JSON.stringify(PREF_PADRAO)); store.set('prefs', JSON.stringify(PREF)); store.set('grupos-abertos', '{}'); aplicarVisual(); rota(); };
  // aparência
  t.querySelectorAll('[data-th]').forEach(b => b.onclick = () => { store.set('tema', b.dataset.th); aplicarTema(); rota(); });
  $('#rever-tour').onclick = () => iniciarTour();
  t.querySelectorAll('[data-papel]').forEach(d => d.onclick = async e => { if (e.target.closest('button')) return; await put('/api/papeis/atual', {nome: d.dataset.papel}); await aplicarPapel(); rota(); });
  t.querySelectorAll('[data-rm-papel]').forEach(b => b.onclick = async () => { if (confirm('Apagar este papel de parede?')) { await del('/api/papeis/' + encodeURIComponent(b.dataset.rmPapel)); rota(); } });
  $('#novo-papel').onchange = async e => {
    const fd = new FormData(); fd.append('arquivo', e.target.files[0]);
    const r = await post('/api/papeis', fd); await put('/api/papeis/atual', {nome: r.nome}); await aplicarPapel(); rota();
  };
  // celular e sessão
  t.querySelectorAll('[data-copiar]').forEach(b => b.onclick = async () => {
    const i = $('#' + b.dataset.copiar); i.select();
    try { await navigator.clipboard.writeText(i.value); } catch (_) { document.execCommand('copy'); }
    b.textContent = 'copiado';
  });
  if ($('#sair')) $('#sair').onclick = async () => { await post('/api/logout', {}); mostrarLogin(); };
  if (aparelho) ligarAparelho(aparelho);
  $('#baixar-ods').onclick = async e => {
    const b = e.target, msg = $('#ods-msg');
    b.disabled = true; msg.textContent = 'Gerando no LibreOffice, leva uns 15 segundos...';
    try {
      const r = await fetch('/api/exportar.ods');
      if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || 'falhou');
      const a = Object.assign(document.createElement('a'), {href: URL.createObjectURL(await r.blob()),
        download: (r.headers.get('Content-Disposition') || '').match(/filename="([^"]+)"/)?.[1] || 'financas.ods'});
      a.click(); URL.revokeObjectURL(a.href); msg.textContent = '';
    } catch (err) { msg.textContent = 'Não deu: ' + err.message; }
    b.disabled = false;
  };
}

// Ajustes > Celular dentro do app: o servidor para sincronizar, a chave dele, os apps de banco lidos e o acesso a
// notificações. O celular funciona sozinho; o servidor só recebe e manda o que mudou quando está ao alcance.
function cartaoAparelho(a) {
  const u = a.ultima;
  const ultima = !u ? 'ainda não sincronizou' : `${new Date(u.quando).toLocaleString('pt-BR', {dateStyle: 'short', timeStyle: 'short'})}: ` +
    (u.ok ? `ok, ${u.enviadas} enviada(s) e ${u.recebidas} recebida(s)` : `<span class="neg">${esc(u.erro)}</span>`);
  const outros = a.apps.filter(p => !(p in a.apps_padrao));
  return `<section class="painel vidro"><h3>Celular <small>este aparelho</small></h3>
    <p class="sub">As notificações dos apps marcados viram lançamentos aqui na hora, sem precisar do servidor. Quando o servidor estiver ao alcance (mesma rede ou VPN), o app manda o que mudou aqui e recebe o que mudou lá.</p>
    <label class="c">Endereço do servidor<input id="app-url" inputmode="url" placeholder="http://192.168.0.10:8095" value="${esc(a.url)}"></label>
    <label class="c">Chave (API_KEY)<input id="app-chave" autocomplete="off" value="${esc(a.chave)}"></label>
    <div class="subsecao">Apps monitorados</div>
    <div class="barra">${Object.entries(a.apps_padrao).map(([p, n]) => `<label class="alternar"><input type="checkbox" data-app="${esc(p)}" ${a.apps.includes(p) ? 'checked' : ''}> ${esc(n)}</label>`).join('')}</div>
    <label class="c">Outros apps <small class="muted">nome do pacote, separados por vírgula</small><input id="app-outros" value="${esc(outros.join(', '))}"></label>
    <div class="barra"><button class="prim" id="app-salvar">Salvar</button><button id="app-testar">Testar conexão</button><button id="app-sync">Sincronizar agora</button><button id="app-acesso">Acesso a notificações</button></div>
    <p class="sub">Acesso a notificações: ${a.acesso ? '<b class="pos">liberado</b>' : '<b class="warnc">falta liberar</b> (toque em "Acesso a notificações" e ligue o Finanças)'}</p>
    <p class="sub">Última sincronização: ${ultima}</p>
    <p class="sub" id="app-msg"></p></section>`;
}
function ligarAparelho(a) {
  const msg = (texto, ok) => { $('#app-msg').innerHTML = `<span class="${ok ? 'pos' : 'neg'}">${esc(texto)}</span>`; };
  const coletar = () => ({url: $('#app-url').value, chave: $('#app-chave').value,
    apps: [...document.querySelectorAll('[data-app]')].filter(i => i.checked).map(i => i.dataset.app)
      .concat($('#app-outros').value.split(',').map(p => p.trim()).filter(Boolean))});
  $('#app-salvar').onclick = async () => { await APP.salvar(coletar()); msg('Salvo.', true); };
  $('#app-testar').onclick = async () => { msg('Testando...', true); const r = await APP.testar($('#app-url').value, $('#app-chave').value); msg(r.mensagem, r.ok); };
  $('#app-sync').onclick = async e => {
    e.target.disabled = true; msg('Sincronizando...', true);
    await APP.salvar(coletar());
    const r = await APP.sincronizar();
    V = await api('/api/vocabulario');
    await rota();
    msg(r.ok ? `Sincronizado: ${r.enviadas} enviada(s), ${r.recebidas} recebida(s).` : r.erro, r.ok);
  };
  $('#app-acesso').onclick = () => APP.acessoNotificacoes();
}

// Apagar categoria: se tiver lançamentos, eles vão para outra categoria do mesmo tipo antes.
function apagarCategoria(c) {
  const d = $('#editor');
  const outras = V.categorias.filter(x => x.tipo === c.tipo && x.id !== c.id);
  d.innerHTML = `<h3 style="margin:0 0 6px">Apagar "${esc(c.nome)}"</h3>
    ${c.uso ? `<p>Esta categoria tem <b>${c.uso}</b> lançamento(s). Para onde eles vão?</p>
      <select id="ap-destino" style="width:100%">${outras.map(x => `<option value="${x.id}">${esc(x.grupo)}: ${esc(x.nome)}</option>`).join('')}</select>` : '<p>Ela não tem lançamentos.</p>'}
    <div class="barra" style="margin-top:12px"><button class="prim" id="ap-ok">Apagar</button><button id="ap-x">Cancelar</button></div><p class="erro" id="ap-erro"></p>`;
  $('#ap-x').onclick = () => d.close();
  $('#ap-ok').onclick = async () => {
    try { await del('/api/categorias/' + c.id + (c.uso ? '?mover_para=' + $('#ap-destino').value : '')); d.close(); V = await api('/api/vocabulario'); rota(); }
    catch (e) { $('#ap-erro').textContent = e.message; }
  };
  d.showModal();
}

// Clicar fora da caixa fecha o modal. Só conta se o clique começou e terminou fora (arrastar para selecionar
// texto e soltar fora não fecha).
(() => {
  const dlg = $('#editor');
  const fora = e => { const r = dlg.getBoundingClientRect(); return e.target === dlg && (e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom); };
  let comecouFora = false;
  dlg.addEventListener('mousedown', e => { comecouFora = fora(e); });
  dlg.addEventListener('click', e => { if (comecouFora && fora(e)) dlg.close(); comecouFora = false; });
})();

// ---------------------------------------------------------------- ajuda: o (?) ao lado do título de cada cartão
const AJUDA = {
  'painel:periodo': `<p>O Painel mostra uma semana, um mês ou um ano. As setas vão para o período anterior ou o próximo, e <b>Hoje</b> volta para o atual.</p>
    <p><b>Comparar</b> mostra, nos números e nas categorias, a diferença para o período anterior.</p>
    <p>Renda que cai a partir do dia 25 conta no mês seguinte (o salário do dia 25 é do mês que vem). Na visão de semana isso não se aplica.</p>`,
  'painel:resumo': `<p><b>Resultado</b>: entradas menos gastos do período. Transferências entre suas contas e acertos com pessoas não entram. <b>Juros e taxas</b> é a parte dos gastos que foi juro, IOF ou tarifa.</p>
    <p><b>Ainda pode gastar</b>: o orçado das categorias variáveis (as que não são fixas e têm valor orçado) menos o que já foi gasto nelas. A marca na barra é o ritmo: quanto do período já passou.</p>
    <p><b>Conta</b>: o saldo que você informou do app; a diferença para o calculado é o que falta lançar. <b>Dívida do cartão</b>: fatura em aberto e limite livre. <b>Você deve / te devem</b>: saldos com pessoas. <b>Pendentes</b>: lançamentos esperando classificação.</p>`,
  'painel:categorias': `<p>Gasto de cada categoria no período contra o orçado (o teto). No mês vale o orçado do mês; na semana, o do mês dividido por 4; no ano, a soma dos meses até agora.</p>
    <p>Parcela de compra antiga (da 2ª em diante) não conta contra o teto: aparece à parte como parcelas antigas.</p>
    <p>Toque numa categoria para ver a evolução dela; o ícone de barras ao lado do grupo mostra a do grupo. Ordem, agrupamento e categorias sem gasto se mudam em Ajustes.</p>`,
  'painel:grafico': `<p>Entradas, gastos e poupança de cada mês (ou semana), com o <b>orçado</b> em tom claro atrás de cada barra, como o gráfico Tracked (vs. Budget) da planilha.</p>
    <p>As caixas ligam e desligam cada série. No modo ano aparecem jan a dez, e os meses que ainda não chegaram mostram só o orçado. Passe o mouse ou toque numa coluna para ver os valores.</p>`,
  'painel:composicao': `<p>Quanto do gasto do período foi para cada grupo de categorias, em valor e porcentagem, contando as parcelas antigas. As cores dos grupos se escolhem no Orçamento.</p>`,
  'painel:entradas': `<p>Renda do período por categoria (o bloco Income da planilha), com o número de lançamentos. Com Comparar ligado, mostra o período anterior e a diferença.</p>`,
  'painel:metas': `<p>Quanto foi guardado em cada meta no período contra o planejado, e o total guardado contra o objetivo.</p>
    <p>Guardar é um lançamento de poupança ligado à meta (o aporte na Caixinha, por exemplo); o resgate ligado à meta desconta dela.</p>`,
  'painel:cobrancas': `<p>Parcelas já contratadas que ainda vão cair no cartão, agrupadas pelo mês da fatura.</p>`,
  'painel:destinos': `<p>Onde mais saiu dinheiro em gastos no período, somado por estabelecimento ou pessoa, com quantas vezes.</p>`,
  'painel:plano': `<p>Os próximos 4 meses da projeção: renda, custo de vida, cartão, resultado, quanto falta cobrir, quanto ainda deve a pessoas e o saldo livre. A projeção completa fica na aba Projeção.</p>`,

  'projecao:titulo': `<p>Projeção mês a mês até o horizonte. Renda, custo de vida e aportes vêm do Orçamento de cada mês; os eventos somam ou tiram a partir do mês que você marcar.</p>
    <p>O cartão fica congelado: entram a fatura atual, com o juro do rotativo, e as parcelas já contratadas. A sobra de cada mês paga primeiro quem você deve, e o resto vira saldo livre.</p>`,
  'projecao:proj-resumo': `<p><b>Falta cobrir</b>: soma dos meses que fecham no vermelho. <b>Quitado em</b>: mês em que a dívida com pessoas zera com as sobras. <b>Saldo livre</b>: o que sobra no fim do horizonte depois de pagar pessoas, com o total guardado nas metas embaixo.</p>`,
  'projecao:proj-grafico': `<p>Barras: resultado de cada mês (verde sobra, vermelho falta), com o valor na ponta. Linha azul: saldo livre acumulado.</p>`,
  'projecao:proj-premissas': `<p><b>Renda mensal base</b>: o padrão do salário no Orçamento. <b>Horizonte</b>: até quando projetar (AAAA-MM). <b>Taxa da ponte do PicPay</b>: a taxa de passar dinheiro do crédito pelo PicPay, usada para separar a taxa do valor principal.</p>`,
  'projecao:proj-tabela': `<p>Os números de cada mês: renda, reembolsos de parcelas que alguém te deve, entradas e saídas únicas, custo de vida, cartão, metas, resultado, falta, quanto ainda deve a pessoas e o saldo livre acumulado.</p>`,
  'projecao:proj-eventos': `<p>O que muda e quando: renda ou gasto mensal que muda a partir de um mês (e, se quiser, até outro), ou uma entrada ou saída única. Valor positivo aumenta, negativo diminui. Desmarque <b>Ativo</b> para ver a projeção sem o evento.</p>`,

  'orcamento:titulo': `<p>O Budget Planning da planilha: quanto você planeja receber, gastar e guardar em cada mês. Painel, metas e Projeção usam esses valores.</p>`,
  'orcamento:periodo': `<p>Escolha o ano e o modo. <b>Orçado</b>: valores planejados, editáveis. <b>Realizado</b>: o que entrou nos lançamentos. <b>Diferença</b>: positivo é a favor (gastou menos que o orçado, recebeu ou guardou mais).</p>
    <p>Com <b>repetir até dezembro</b> marcado, o valor digitado num mês vale também para os meses seguintes do ano.</p>`,
  'orcamento:orc-grade': `<p>Cada categoria em cada mês. Em cinza fica o padrão: o teto da categoria, a renda base no salário, o aporte mensal da meta, ou a soma das despesas fixas se a categoria usa itens. Em escuro, o valor que você definiu para aquele mês; apague a célula para voltar ao padrão.</p>
    <p>Enter desce para a linha de baixo na mesma coluna. <b>A alocar</b> é entradas menos gastos menos poupança. O ponto colorido ao lado do nome muda a cor da categoria ou do grupo.</p>`,
  'orcamento:orc-fixas': `<p>A aba Despesas Fixas da planilha: os itens que você planeja pagar em cada categoria (aluguel, internet, academia), com mês de início e de fim opcionais.</p>
    <p>Cada categoria mostra a soma dos itens no mês, quanto foi orçado e o que sobra para o resto. Marque <b>usar a soma como orçamento</b> para o padrão da categoria passar a ser a soma dos itens.</p>`,
  'orcamento:orc-cats': `<p>Categorias de gasto e de renda: grupo, nome, teto mensal (o padrão do orçamento) e se é fixa (fixa não entra no ainda pode gastar). Ao apagar uma categoria com lançamentos, você escolhe para qual eles vão. As cores valem para o site inteiro.</p>`,
  'orcamento:orc-metas': `<p>Metas de poupança: objetivo, prazo, aporte mensal (o padrão do orçamento da meta) e onde o dinheiro fica. Meta com aportes não se apaga, só se desativa.</p>`,

  'pendentes:titulo': `<p>Lançamentos que ainda não têm classificação completa. Um toque numa sugestão classifica; <b>Dividir</b> separa em partes (a sua e a de outra pessoa, por exemplo). Nada com pessoa é classificado sozinho: o site só sugere.</p>
    <p>Com <b>sugerir da próxima vez</b> marcado, a mesma escolha vira sugestão quando o mesmo lugar aparecer de novo.</p>`,
  'lancamentos:s-resumo': `<p>Entradas, gastos e resultado do que está filtrado na tabela (mês, categoria, tipo, busca), pela data de cada lançamento. Por isso o mês daqui pode diferir do Painel, que conta a renda do dia 25 em diante no mês seguinte.</p>
    <p><b>Falta lançar na conta</b>: a diferença entre o saldo que o app do Nubank mostra e o que os lançamentos daqui somam, a mesma do Painel. Não depende do filtro. Some quando o extrato ou o celular trazem o que faltava; atualize o saldo do app quando ele mudar.</p>`,
  'lancamentos:titulo': `<p>Todos os lançamentos, filtráveis por mês, categoria, tipo e busca. A primeira linha da tabela lança algo à mão. Toque num lançamento para mudar a classificação, dividir em partes ou apagar (só os lançados à mão ou pelo celular).</p>
    <p>A última coluna é o saldo da conta (ou do cartão) logo depois de cada lançamento.</p>`,
  'importar:titulo': `<p>Traz extratos e faturas do Nubank e do Bradesco e mostra o que o filtro do celular descartou.</p>`,
  'importar:s-extrato-e-fatura-do-banco': `<p>Solte o extrato da conta e a fatura do cartão. Nubank: .pdf ou .csv. Bradesco: extrato em .pdf, .csv ou .xlsx e a fatura em aberto que o aplicativo gera em .pdf. O que já existe não duplica, e o que veio pelo celular é casado com a linha do arquivo. Extrato que não fecha com o total ou com a corrente de saldos do banco é recusado. A fatura do Bradesco é imagem: é lida por OCR e só entra se cada cartão fechar com o "Total para" impresso. Na primeira importação, as contas Bradesco e Cartão Bradesco são criadas, a conta com o saldo que o extrato mostra antes do primeiro lançamento.</p>`,
  'importar:s-notificacoes-descartadas-pelo-filtro': `<p>Notificações do celular que o filtro entendeu que não eram compra. Se alguma era, <b>resgatar</b> a transforma em lançamento.</p>`,
  'importar:s-ultimas-importacoes': `<p>Histórico das importações: quantos lançamentos novos, quantos casaram com o que veio pelo celular e quantos já existiam.</p>`,
  'pessoas:titulo': `<p>Quanto você deve a cada pessoa e quanto cada uma te deve. Positivo: a pessoa te deve. Negativo: você deve a ela.</p>`,
  'pessoas:s-saldos': `<p>Saldo com cada pessoa, somando acertos, contas divididas e parcelas que alguém te deve. Parcelas a vencer são as que ainda vão cair.</p>`,
  'pessoas:s-alguem-pagou-uma-conta-por-voce': `<p>Quando outra pessoa paga uma conta sua (condomínio, luz, mercado da casa): o gasto entra na categoria e vira dívida com ela, sem mexer no saldo da sua conta.</p>`,
  'pessoas:s-acertos-recentes': `<p>Os últimos acertos com pessoas: Pix que você mandou ou recebeu para quitar o que devia ou te deviam.</p>`,
  'ajustes:titulo': `<p>Aparência, visualização, pessoas, rateio do aluguel, celular e planilha. Categorias e metas ficam no Orçamento.</p>`,
  'ajustes:s-aparencia': `<p>Tema claro ou escuro e papel de parede. Envie uma imagem para usar como fundo.</p>`,
  'ajustes:s-visualizacao': `<p>Vale só para este aparelho: largura, densidade, fonte, estilo dos painéis e dos gráficos, como as categorias aparecem no Painel, quais painéis mostrar e a ordem das abas.</p>
    <p>Cada painel se move pela alça ao lado do título e muda de tamanho pelo canto de baixo à direita.</p>`,
  'ajustes:s-pessoas': `<p>Como o nome de cada pessoa aparece no extrato (para reconhecer o Pix) e o que sugerir quando entra ou sai dinheiro dela: acerto ou uma categoria.</p>`,
  'ajustes:s-rateio-do-aluguel': `<p>Quanto de cada boleto da imobiliária é de cada morador. Vira sugestão de divisão quando o boleto aparece: sua parte como gasto e a dos outros como acerto. A soma precisa dar 100%.</p>`,
  'ajustes:s-celular': APP ? `<p>Este aparelho: o endereço e a chave do servidor (o Finanças no computador), quais apps de banco ler e o acesso a notificações. Sem servidor, tudo continua funcionando aqui; com ele ao alcance, o app manda o que mudou aqui e recebe o que mudou lá.</p>`
    : `<p>O endereço e a chave para o app Finanças do celular, e os dados para a macro do MacroDroid mandar as notificações do banco para o site: endereço, chave e corpo da requisição. Abra esta tela no celular e copie cada campo.</p>`,
  'ajustes:s-planilha-e-sessao': `<p>Baixa tudo em planilha: no modelo antigo (.ods, preenchido pelo LibreOffice, leva alguns segundos) ou só as tabelas (.xlsx). Sair encerra a sessão neste aparelho.</p>`,
};
const popAjuda = Object.assign(document.createElement('div'), {className: 'ajuda-pop', hidden: true});
document.body.appendChild(popAjuda);
let ajudaDe = null;
const fecharAjuda = () => { popAjuda.hidden = true; ajudaDe = null; };
function abrirAjuda(b, html) {
  if (ajudaDe === b) return fecharAjuda();
  popAjuda.innerHTML = html; popAjuda.hidden = false; ajudaDe = b;
  const r = b.getBoundingClientRect(), w = Math.min(380, innerWidth - 24);
  popAjuda.style.width = w + 'px';
  popAjuda.style.left = Math.max(12, Math.min(r.left - 12, innerWidth - w - 12)) + 'px';
  const embaixo = r.bottom + 8;
  popAjuda.style.top = (embaixo + popAjuda.offsetHeight > innerHeight - 8 ? Math.max(8, r.top - popAjuda.offsetHeight - 8) : embaixo) + 'px';
}
document.addEventListener('click', e => { if (!popAjuda.hidden && !popAjuda.contains(e.target) && !e.target.closest('.ajuda-btn')) fecharAjuda(); });
document.addEventListener('keydown', e => { if (e.key === 'Escape') fecharAjuda(); });
addEventListener('scroll', fecharAjuda, {passive: true, capture: true});
addEventListener('hashchange', fecharAjuda);
function ligarAjuda(raiz, pagina) {
  raiz.querySelectorAll(':scope > .cartao').forEach(c => {
    const html = AJUDA[`${pagina}:${c.dataset.id}`];
    if (!html || c.querySelector('.ajuda-btn')) return;
    const b = Object.assign(document.createElement('button'), {type: 'button', className: 'ajuda-btn', textContent: '?', title: 'Como funciona'});
    b.setAttribute('aria-label', 'Como funciona');
    b.onclick = e => { e.stopPropagation(); abrirAjuda(b, html); };
    const alvo = c.querySelector('.titulo-cartao') || c.querySelector('.titulo h2') || c.querySelector('.cartao-topo > .alca');
    alvo?.after(b);
  });
}

// ---------------------------------------------------------------- tour do primeiro acesso
// Na primeira entrada neste aparelho (no app, na primeira abertura), passa por cada tela e cada painel: o que mostra,
// como ler e o que colocar. Fica marcado como visto neste aparelho; Ajustes > Aparência tem "Rever o tour".
const cartaoTour = id => `#mosaico > .cartao[data-id="${id}"]`;
const PASSOS_TOUR = [
  {titulo: 'Bem-vindo ao Finanças', texto: `<p>Em poucos minutos este tour passa por cada tela e cada painel: o que mostra, como ler os números e o que você coloca em cada lugar.</p>
    <p>Use <b>Próximo</b> e <b>Voltar</b> (ou as setas do teclado). Dá para sair a qualquer hora e rever depois em <b>Ajustes</b>.</p>`},
  {rota: 'painel', alvo: '#nav', titulo: 'As abas', texto: `<p><b>Painel</b>: o resumo. <b>Pendentes</b>: o que falta classificar (o número vermelho diz quantos). <b>Lançamentos</b>: tudo que entrou e saiu. <b>Orçamento</b>: quanto você planeja gastar. <b>Importar</b>: extratos e faturas. <b>Pessoas</b>: quem deve a quem. <b>Projeção</b>: os próximos meses. <b>Ajustes</b>: aparência, pessoas e celular.</p>
    <p>O botão de sol ou lua troca o tema claro e escuro.</p>`},
  {rota: 'painel', alvo: cartaoTour('periodo'), titulo: 'Qual período ver', texto: `<p>Escolha <b>semana</b>, <b>mês</b> ou <b>ano</b>. As setas vão para o período anterior ou o próximo, e <b>Hoje</b> volta ao atual.</p>
    <p><b>Comparar</b> mostra, em cada número, a diferença para o período anterior. Salário que cai do dia 25 em diante conta no mês seguinte.</p>`},
  {rota: 'painel', alvo: cartaoTour('resumo'), titulo: 'Resumo do período', texto: `<p>Os números que mais importam, num painel só. Os próximos passos explicam cada parte.</p>
    <p>Todo painel se arrasta pela alça (os seis pontinhos ao lado do título), muda de largura no botão à direita do título e tem um <b>?</b> que explica de novo.</p>`},
  {rota: 'painel', alvo: cartaoTour('resumo') + ' .heroi > div:nth-child(1)', titulo: 'Resultado', texto: `<p>Entradas menos gastos do período. <b class="pos">Verde</b>: sobrou dinheiro. <b class="neg">Vermelho</b>: gastou mais do que entrou.</p>
    <p>Transferência entre contas suas e acerto com pessoas não contam: não são ganho nem gasto seu. <b>Juros e taxas</b> é a parte dos gastos que foi juro, IOF ou tarifa. <b>Guardado em metas</b> aparece quando você guarda dinheiro.</p>`},
  {rota: 'painel', alvo: cartaoTour('resumo') + ' .heroi > div:nth-child(2)', titulo: 'Ainda pode gastar', texto: `<p>Quanto ainda cabe no orçamento das categorias variáveis (mercado, delivery, transporte, lazer). A barra enche conforme você gasta; o traço vertical é o ritmo, até onde a barra deveria ir hoje.</p>
    <p><b class="pos">Verde</b>: no ritmo. <b class="warnc">Amarelo</b>: gastando mais rápido que o ritmo. <b class="neg">Vermelho</b>: o orçamento estourou.</p>
    <p class="tour-dados"><b>O que colocar:</b> o teto de cada categoria, no <b>Orçamento</b>. Sem teto, este número fica zerado.</p>`},
  {rota: 'painel', alvo: cartaoTour('resumo') + ' .kpis', titulo: 'Conta, cartão, pessoas e pendentes', texto: `<p><b>Conta</b>: o saldo que o app do banco mostra; a diferença para o que os lançamentos somam é o que ainda não foi lançado. <b>Dívida do cartão</b>: a fatura em aberto e o limite livre. <b>Você deve / te devem</b>: os saldos com pessoas. <b>Pendentes</b>: quantos lançamentos esperam você.</p>
    <p class="tour-dados"><b>O que colocar:</b> toque em <b>informar saldo do app</b> e digite o saldo que o app do banco mostra agora. Atualize de vez em quando.</p>`},
  {rota: 'painel', alvo: cartaoTour('categorias'), titulo: 'Categorias', texto: `<p>Cada categoria contra o teto do período: quanto gastou, o teto, a porcentagem e quanto resta (<b class="pos">verde</b>) ou passou (<b class="neg">vermelho</b>). Os grupos abrem com um toque, e o ícone de barras ao lado do grupo mostra a evolução dos últimos meses.</p>
    <p>Parcela de compra antiga (da 2ª em diante) aparece à parte, como parcelas antigas, e não conta contra o teto.</p>`},
  {rota: 'painel', alvo: cartaoTour('grafico'), titulo: 'Entradas e gastos', texto: `<p>Entradas, gastos e poupança de cada mês (ou semana), com o orçado em tom claro atrás de cada barra. As caixinhas ligam e desligam cada série; toque numa coluna para ver os valores.</p>`},
  {rota: 'painel', alvo: cartaoTour('composicao'), titulo: 'Para onde foi', texto: `<p>A fatia de cada grupo (moradia, alimentação, transporte...) no gasto do período, em valor e porcentagem.</p>`},
  {rota: 'painel', alvo: cartaoTour('entradas'), titulo: 'Entradas do período', texto: `<p>O que entrou, por categoria de renda (salário, ajuda dos pais, extras), com quantos lançamentos.</p>
    <p class="tour-dados"><b>O que colocar:</b> nada direto: vem dos lançamentos classificados como renda.</p>`},
  {rota: 'painel', alvo: cartaoTour('metas'), titulo: 'Poupança e metas', texto: `<p>Cada meta: quanto você planejou guardar no período, quanto guardou, quanto falta e o total contra o objetivo.</p>
    <p class="tour-dados"><b>O que colocar:</b> crie as metas no <b>Orçamento</b> (reserva de emergência, uma compra). Guardar é lançar como poupança ligada à meta, por exemplo o dinheiro que vai para a caixinha.</p>`},
  {rota: 'painel', alvo: cartaoTour('cobrancas'), titulo: 'Próximas cobranças no cartão', texto: `<p>As parcelas que ainda vão cair no cartão, agrupadas pelo mês da fatura. Aparecem sozinhas quando uma compra parcelada entra (pela fatura ou pelo celular).</p>`},
  {rota: 'painel', alvo: cartaoTour('destinos'), titulo: 'Maiores destinos', texto: `<p>Onde mais saiu dinheiro no período, somado por lugar ou por pessoa, com quantas vezes.</p>`},
  {rota: 'painel', alvo: cartaoTour('plano'), titulo: 'Projeção', texto: `<p>Os próximos 4 meses: renda, custo de vida, cartão, resultado, quanto falta cobrir, quanto ainda deve a pessoas e o saldo livre. A conta completa fica na aba <b>Projeção</b>.</p>`},
  {rota: 'pendentes', alvo: () => $('#lista')?.closest('.cartao'), titulo: 'Pendentes', texto: `<p>O que o sistema não classifica sozinho: lugar novo, Pix para uma pessoa (o mesmo Pix pode ter outra finalidade), recarga do PicPay no crédito.</p>
    <p class="tour-dados"><b>O que fazer:</b> toque numa sugestão ou numa categoria e pronto. <b>Dividir</b> separa em partes, por exemplo a sua parte e a de um colega. Com <b>sugerir da próxima vez</b> marcado, o mesmo lugar já chega com a sugestão.</p>`},
  {rota: 'lancamentos', alvo: '#lanc-heroi', titulo: 'Lançamentos: o resumo', texto: `<p>Entradas, gastos e resultado do que está filtrado na tabela, e quanto falta lançar na conta (a diferença para o saldo que o app do banco mostra).</p>`},
  {rota: 'lancamentos', alvo: () => $('#f-mes')?.closest('.barra'), titulo: 'Filtros', texto: `<p>Mês, categoria, tipo (entrada, saída, transferência, acerto, poupança, pendente) ou uma busca pelo nome. O resumo acima acompanha o filtro.</p>`},
  {rota: 'lancamentos', alvo: () => $('#n-data')?.closest('tr'), titulo: 'Lançar à mão', texto: `<p>A primeira linha da tabela lança o que não passa pelo banco: dinheiro vivo, uma conta que alguém pagou por você, um acerto.</p>
    <p class="tour-dados"><b>O que colocar:</b> a data, o tipo (saída, entrada, guardar em meta, acerto...), a categoria ou a pessoa, o valor, o que foi e a conta. Enter lança.</p>`},
  {rota: 'lancamentos', alvo: '#t-l', titulo: 'Tudo que entrou e saiu', texto: `<p>Do mais novo ao mais antigo. Toque num lançamento para mudar a categoria, dividir em partes ou apagar (só os lançados à mão ou pelo celular; o do extrato é a fonte). A última coluna é o saldo da conta logo depois de cada lançamento.</p>`},
  {rota: 'orcamento', alvo: cartaoTour('orc-cats'), titulo: 'Suas categorias', texto: `<p>Grupo, nome, teto mensal e se é fixa. Categoria fixa (aluguel, academia) não entra no <b>ainda pode gastar</b>.</p>
    <p class="tour-dados"><b>Comece por aqui:</b> dê um teto para mercado, delivery, transporte e lazer. Crie ou apague categorias do seu jeito.</p>`},
  {rota: 'orcamento', alvo: cartaoTour('orc-grade'), titulo: 'Orçamento mês a mês', texto: `<p>Quanto você planeja receber, gastar e guardar em cada mês. Em cinza está o padrão (o teto da categoria); digite numa célula para mudar só aquele mês, e marque <b>repetir até dezembro</b> para valer nos seguintes.</p>
    <p>Os modos <b>Realizado</b> e <b>Diferença</b> mostram o que aconteceu e o quanto ficou a favor ou contra.</p>`},
  {rota: 'orcamento', alvo: cartaoTour('orc-fixas'), titulo: 'Despesas fixas', texto: `<p>Os itens que você paga todo mês em cada categoria (aluguel, internet, academia), com início e fim se tiverem.</p>
    <p class="tour-dados"><b>O que colocar:</b> cada conta fixa com o valor. Marque <b>usar a soma como orçamento</b> para a categoria orçar pela soma dos itens.</p>`},
  {rota: 'orcamento', alvo: cartaoTour('orc-metas'), titulo: 'Metas', texto: `<p class="tour-dados"><b>O que colocar:</b> o nome da meta, o objetivo em reais, o prazo, quanto guardar por mês e onde o dinheiro fica (a caixinha do banco, por exemplo).</p>`},
  {rota: 'importar', alvo: cartaoTour('s-extrato-e-fatura-do-banco'), titulo: 'Importar extrato e fatura', texto: `<p>Solte aqui os arquivos do banco. <b>Nubank</b>: extrato e fatura em .pdf ou .csv. <b>Bradesco</b>: extrato em .pdf, .csv ou .xlsx e a fatura em aberto em .pdf.</p>
    <p>O que já existe não duplica, e a compra que veio pelo celular é casada com a linha do arquivo. Extrato que não fecha com o total do banco é recusado.</p>
    <p class="tour-dados"><b>Quando:</b> uma vez por mês, ou sempre que quiser conferir. É assim que o saldo e o cartão ficam completos.</p>`},
  {rota: 'importar', alvo: cartaoTour('s-notificacoes-descartadas-pelo-filtro'), titulo: 'Notificações descartadas', texto: `<p>Notificações do banco que o filtro entendeu que não eram compra (aviso de fatura, propaganda, código de segurança). Se alguma era compra, <b>Resgatar</b> transforma em lançamento.</p>`},
  {rota: 'importar', alvo: cartaoTour('s-ultimas-importacoes'), titulo: 'Últimas importações', texto: `<p>O histórico: quantos lançamentos novos, quantos casaram com o que veio pelo celular e quantos já existiam.</p>`},
  {rota: 'pessoas', alvo: cartaoTour('s-saldos'), titulo: 'Quem deve a quem', texto: `<p>Positivo: a pessoa te deve. Negativo: você deve a ela. Muda quando uma parte de um lançamento é um <b>acerto</b>: dividir uma conta, receber o Pix de volta, pagar o que devia.</p>`},
  {rota: 'pessoas', alvo: cartaoTour('s-alguem-pagou-uma-conta-por-voce'), titulo: 'Alguém pagou por você', texto: `<p class="tour-dados"><b>O que colocar:</b> quando outra pessoa paga uma conta sua (a luz, o mercado da casa), lance aqui: o gasto entra na categoria e vira dívida com ela, sem mexer no saldo da sua conta.</p>`},
  {rota: 'projecao', alvo: cartaoTour('proj-resumo'), titulo: 'Projeção', texto: `<p>Mês a mês até o horizonte: renda, custo de vida (do Orçamento), o cartão já contratado e o resultado. <b>Falta cobrir</b> soma os meses no vermelho; <b>saldo livre</b> é o que sobra depois de pagar quem você deve.</p>`},
  {rota: 'projecao', alvo: cartaoTour('proj-eventos'), titulo: 'Eventos', texto: `<p class="tour-dados"><b>O que colocar:</b> o que muda e quando: um aumento, uma renda que acaba, uma viagem, o 13º. A projeção recalcula na hora.</p>`},
  {rota: 'ajustes', alvo: cartaoTour('s-pessoas'), titulo: 'Pessoas', texto: `<p class="tour-dados"><b>O que colocar:</b> quem divide contas com você, com o nome como aparece no extrato do banco. Assim o Pix dessa pessoa é reconhecido e vem com sugestão.</p>`},
  {rota: 'ajustes', alvo: cartaoTour('s-rateio-do-aluguel'), titulo: 'Rateio do aluguel', texto: `<p class="tour-dados"><b>O que colocar:</b> se você divide o aluguel, quanto é de cada um (a soma dá 100%). O boleto da imobiliária vira sua parte como gasto e a dos outros como acerto.</p>`},
  {rota: 'ajustes', alvo: cartaoTour('s-celular'), titulo: 'Celular', texto: APP
    ? `<p>Este aparelho. As notificações dos apps de banco marcados viram lançamentos aqui na hora, mesmo sem servidor.</p>
      <p class="tour-dados"><b>O que colocar:</b> toque em <b>Acesso a notificações</b> e ligue o Finanças. Se tiver o Finanças no computador, coloque o endereço dele (ex.: http://192.168.0.10:8095) e a chave, que aparecem em Ajustes no computador, e toque em <b>Testar conexão</b>.</p>`
    : `<p>Para o celular mandar as compras na hora.</p>
      <p class="tour-dados"><b>O que fazer:</b> no app Finanças do celular, copie o <b>endereço</b> e a <b>chave</b> daqui. Quem usa o MacroDroid copia os três campos de baixo.</p>`},
  {rota: 'ajustes', alvo: cartaoTour('s-aparencia'), titulo: 'Aparência', texto: `<p>Tema claro ou escuro e papel de parede. Logo abaixo, em Visualização, o jeito como o site aparece neste aparelho. O botão <b>Rever o tour</b> fica aqui.</p>`},
  {rota: 'painel', titulo: 'Pronto para começar', texto: `<p>Um bom começo:</p>
    <p>1. No <b>Orçamento</b>, dê um teto para as categorias que você quer controlar.<br>2. Em <b>Ajustes</b>, cadastre quem divide contas com você.<br>3. Em <b>Importar</b>, traga o extrato e a fatura do mês${APP ? ', e libere o acesso a notificações para as compras entrarem sozinhas' : ', ou deixe o celular mandar as compras'}.<br>4. Classifique o que aparecer em <b>Pendentes</b>.</p>
    <p>O <b>?</b> de cada painel explica de novo.</p>`},
];
const tourFoco = Object.assign(document.createElement('div'), {className: 'tour-foco', hidden: true});
const tourCaixa = Object.assign(document.createElement('div'), {className: 'tour-caixa', hidden: true});
tourCaixa.setAttribute('role', 'dialog');
document.body.append(tourFoco, tourCaixa);
let tourI = -1, tourEl = null;
const tourAberto = () => tourI >= 0;
const alvoTour = p => { const el = !p.alvo ? null : typeof p.alvo === 'function' ? p.alvo() : $(p.alvo); return el && el.getClientRects().length ? el : null; };
function iniciarTour() { const ja = tourAberto(); mostrarPasso(0); if (!ja) requestAnimationFrame(seguirTour); }
function fecharTour(fim) {
  tourI = -1; tourEl = null; tourFoco.hidden = tourCaixa.hidden = true;
  store.set('tour', 'visto');
  if (fim) location.hash = '#painel';
}
async function mostrarPasso(i) {
  tourI = i; tourEl = null;
  const p = PASSOS_TOUR[i], n = PASSOS_TOUR.length;
  fecharAjuda();
  if (p.rota && (location.hash.slice(1) || 'painel').split('?')[0] !== p.rota) location.hash = '#' + p.rota;
  tourCaixa.innerHTML = `<div class="tour-topo"><b>${p.titulo}</b><span class="muted">${i + 1} de ${n}</span></div><div class="tour-texto">${p.texto}</div>
    <div class="tour-botoes"><button data-tour="sair">Sair do tour</button><span class="espaco"></span>${i ? '<button data-tour="voltar">Voltar</button>' : ''}
      <button class="prim" data-tour="proximo">${i === n - 1 ? 'Começar a usar' : 'Próximo'}</button></div>`;
  tourCaixa.hidden = tourFoco.hidden = false;
  tourCaixa.querySelector('[data-tour="sair"]').onclick = () => fecharTour(false);
  tourCaixa.querySelector('[data-tour="proximo"]').onclick = () => (i === n - 1 ? fecharTour(true) : mostrarPasso(i + 1));
  const voltar = tourCaixa.querySelector('[data-tour="voltar"]');
  if (voltar) voltar.onclick = () => mostrarPasso(i - 1);
  for (let t = 0; p.alvo && t < 50 && tourI === i; t++) {     // a tela da aba pode levar um instante para desenhar
    const el = alvoTour(p);
    if (el) { await new Promise(r => setTimeout(r, 300)); if (tourI === i) { el.scrollIntoView({block: 'center'}); tourEl = el; } break; }
    await new Promise(r => setTimeout(r, 100));
  }
}
// O destaque acompanha o alvo (rolagem, mudança de tamanho, o mosaico se arrumando) a cada quadro.
function seguirTour() {
  if (!tourAberto()) return;
  const el = tourEl && document.body.contains(tourEl) ? tourEl : null, m = el ? 6 : 0;
  const r = el ? el.getBoundingClientRect() : {left: innerWidth / 2, top: innerHeight / 2, width: 0, height: 0, right: innerWidth / 2, bottom: innerHeight / 2};
  Object.assign(tourFoco.style, {left: r.left - m + 'px', top: r.top - m + 'px', width: r.width + 2 * m + 'px', height: r.height + 2 * m + 'px'});
  const c = tourCaixa, w = c.offsetWidth, h = c.offsetHeight, folga = 12;
  if (innerWidth < 700) {                       // celular: o balão fica embaixo, ou em cima se o destaque estiver embaixo
    c.style.left = c.style.right = '8px';
    c.style.top = (el && r.top + r.height / 2 > innerHeight / 2 ? folga : innerHeight - h - folga) + 'px';
  } else {
    c.style.right = 'auto';
    let x, y;
    if (!el) { x = (innerWidth - w) / 2; y = (innerHeight - h) / 2; }
    else if (innerHeight - r.bottom > h + 2 * folga) { x = r.left; y = r.bottom + folga; }
    else if (r.top > h + 2 * folga) { x = r.left; y = r.top - h - folga; }
    else if (innerWidth - r.right > w + 2 * folga) { x = r.right + folga; y = r.top; }
    else { x = r.left - w - folga; y = r.top; }
    c.style.left = Math.max(folga, Math.min(x, innerWidth - w - folga)) + 'px';
    c.style.top = Math.max(folga, Math.min(y, innerHeight - h - folga)) + 'px';
  }
  requestAnimationFrame(seguirTour);
}
document.addEventListener('keydown', e => {
  if (!tourAberto()) return;
  if (e.key === 'Escape') fecharTour(false);
  else if (e.key === 'ArrowRight') tourCaixa.querySelector('[data-tour="proximo"]').click();
  else if (e.key === 'ArrowLeft' && tourI > 0) mostrarPasso(tourI - 1);
});

// ---------------------------------------------------------------- partida
aplicarTema();
aplicarVisual();
if ('serviceWorker' in navigator) navigator.serviceWorker.register('sw.js').catch(() => {});
iniciar().catch(() => {});
