import { scoreGrid, GROUPS, isMarket, marketLabel, prob, implied, kelly } from './model.js';

const $ = sel => document.querySelector(sel);
const view = $('#view');
const esc = s => String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
const pct = (p, d = 1) => (100 * p).toFixed(d) + '%';
const fair = p => (p > 0.001 ? (1 / p).toFixed(2) : '—');
const num = s => parseFloat(String(s).replace(',', '.'));
const SIDE = { '1': 'home', 'X': 'draw', '2': 'away' };
const STAGE = { regular: 'Fase regular', playin: 'Play-in', liguilla: 'Liguilla' };

function load(key, dflt) {
  try { return JSON.parse(localStorage.getItem(key)) ?? dflt; } catch { return dflt; }
}
function save(key, val) {
  try { localStorage.setItem(key, JSON.stringify(val)); } catch { /* private mode / quota: ignore */ }
}

const S = {
  data: null, sample: false, grids: new Map(),
  legs: load('bp.legs', []).filter(l => l && l.fid && isMarket(l.key)),
  bankroll: load('bp.bankroll', '1000'),
  saved: load('bp.saved', []).filter(s => s && Array.isArray(s.legs)),
};

const fixture = id => S.data.fixtures.find(f => f.id === id);
function grid(f) {
  if (!S.grids.has(f.id)) S.grids.set(f.id, scoreGrid(f.lambda, f.mu, f.rho ?? S.data.model?.rho ?? 0));
  return S.grids.get(f.id);
}
const when = iso => new Date(iso).toLocaleString('es-MX', { weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });

async function loadData() {
  for (const [url, sample] of [['data/predictions.json', false], ['data/predictions.sample.json', true]]) {
    try {
      const r = await fetch(url, { cache: 'no-cache' });
      if (r.ok) return { data: await r.json(), sample };
    } catch { /* try the next one */ }
  }
  throw new Error('sin datos');
}

// ---------- Partidos ----------
function viewPartidos() {
  const list = [...S.data.fixtures].sort((a, b) => a.kickoff.localeCompare(b.kickoff));
  if (!list.length) return '<h1>Partidos</h1><p class="muted">No hay partidos próximos en los datos.</p>';
  const now = Date.now();
  return '<h1>Próximos partidos</h1>' + list.map(f => {
    const g = grid(f);
    const p = ['1', 'X', '2'].map(k => prob(g, [k]));
    const imp = implied(f.market);
    const o = imp && [f.market.home, f.market.draw, f.market.away];
    const model = p.map((pi, i) => {
      const edge = o ? pi * o[i] - 1 : 0;
      return edge > 0
        ? `<td class="value">${pct(pi, 0)}<br><small>+${pct(edge)}</small></td>`
        : `<td>${pct(pi, 0)}</td>`;
    }).join('');
    const market = imp
      ? `<tr><td>Mercado</td>${[imp.home, imp.draw, imp.away].map(q => `<td>${pct(q, 0)}</td>`).join('')}</tr>
         <tr><td class="muted small">Cuota</td>${o.map(x => `<td class="muted small">${x.toFixed(2)}</td>`).join('')}</tr>`
      : '<tr><td colspan="4" class="muted small">Sin cuotas de mercado para este partido</td></tr>';
    const past = new Date(f.kickoff).getTime() < now;
    return `<a class="card${past ? ' past' : ''}" href="#/partido/${encodeURIComponent(f.id)}">
      <div class="row"><span class="teams">${esc(f.home)} vs ${esc(f.away)}</span><span class="muted small">›</span></div>
      <div class="muted small">${when(f.kickoff)} · ${STAGE[f.stage] || esc(f.stage || '')}${past ? ' · ya comenzó' : ''}</div>
      <table><tr><th></th><th>1</th><th>X</th><th>2</th></tr>
        <tr><td>Modelo</td>${model}</tr>${market}</table></a>`;
  }).join('') + '<p class="muted small">Mercado = probabilidad implícita de las cuotas sin margen. Resaltado = el modelo ve valor (prob. × cuota &gt; 1), con la ventaja estimada.</p>';
}

// ---------- Partido ----------
function marketButton(f, g, k) {
  const p = prob(g, [k]);
  const on = S.legs.some(l => l.fid === f.id && l.key === k);
  let extra = '';
  if (SIDE[k] && f.market && f.market[SIDE[k]] > 1) {
    const o = f.market[SIDE[k]], edge = p * o - 1;
    extra = `<br><span class="muted small">mercado ${o.toFixed(2)}</span>${edge > 0 ? ` <span class="value small">+${pct(edge)}</span>` : ''}`;
  }
  return `<button class="mk${on ? ' on' : ''}" data-act="leg" data-fid="${esc(f.id)}" data-key="${k}">
    <span class="lbl">${esc(marketLabel(k, f.home, f.away))}</span>
    <span class="nums"><b>${pct(p)}</b> · justa ${fair(p)}${extra}</span></button>`;
}

function viewPartido(id) {
  const f = fixture(id);
  if (!f) return '<p>Partido no encontrado. <a href="#/">Volver a partidos</a></p>';
  const g = grid(f), N = 6;
  let max = 0;
  for (let h = 0; h < N; h++) for (let a = 0; a < N; a++) max = Math.max(max, g[h][a]);
  const heat = Array.from({ length: N }, (_, h) =>
    `<tr><th>${h}</th>${Array.from({ length: N }, (_, a) =>
      `<td style="--a:${(0.85 * g[h][a] / max).toFixed(2)}">${(100 * g[h][a]).toFixed(1)}</td>`).join('')}</tr>`).join('');
  const top = g.flatMap((row, h) => row.map((p, a) => ({ h, a, p }))).sort((x, y) => y.p - x.p).slice(0, 5);
  return `<p><a href="#/">‹ Partidos</a></p>
    <h1>${esc(f.home)} vs ${esc(f.away)}</h1>
    <p class="muted small">${when(f.kickoff)} · ${STAGE[f.stage] || esc(f.stage || '')} · goles esperados ${f.lambda.toFixed(2)} – ${f.mu.toFixed(2)}</p>
    ${f.market ? '' : '<p class="note">Sin cuotas de mercado para este partido: solo se muestra el modelo.</p>'}
    <div class="card"><h2>Marcadores más probables</h2>
      <table><tr><th>Marcador</th><th>Prob.</th><th>Cuota justa</th></tr>
      ${top.map(s => `<tr><td>${s.h}–${s.a}</td><td>${pct(s.p)}</td><td>${fair(s.p)}</td></tr>`).join('')}</table>
      <h3 style="margin-top:.8rem">Mapa de marcadores (%) · filas ${esc(f.home)}, columnas ${esc(f.away)}</h3>
      <table class="heat"><tr><th></th>${Array.from({ length: N }, (_, a) => `<th>${a}</th>`).join('')}</tr>${heat}</table>
    </div>
    <p class="muted small">Toca un mercado para agregarlo (o quitarlo) del parlay. Cuota justa = 1 / probabilidad del modelo.</p>
    ${GROUPS.map(([title, keys]) => `<div class="card"><h2>${title}</h2>${keys.map(k => marketButton(f, g, k)).join('')}</div>`).join('')}`;
}

function toggleLeg(btn) {
  const { fid, key } = btn.dataset;
  const i = S.legs.findIndex(l => l.fid === fid && l.key === key);
  if (i >= 0) S.legs.splice(i, 1);
  else {
    const f = fixture(fid);
    const o = f.market && SIDE[key] ? f.market[SIDE[key]] : null;
    S.legs.push({ fid, key, odds: o ? String(o) : '', home: f.home, away: f.away });
  }
  btn.classList.toggle('on', i < 0);
  save('bp.legs', S.legs);
  updateCount();
}

// ---------- Parlay ----------
function parlayCalc() {
  const byMatch = new Map();
  let missing = false;
  for (const l of S.legs) {
    const f = fixture(l.fid);
    if (!f) { missing = true; continue; }
    if (!byMatch.has(f.id)) byMatch.set(f.id, { f, keys: [] });
    byMatch.get(f.id).keys.push(l.key);
  }
  let p = 1;  // joint within a match (score grid), independent across matches
  for (const { f, keys } of byMatch.values()) p *= prob(grid(f), keys);
  const os = S.legs.map(l => num(l.odds));
  const O = os.length && os.every(o => o > 1) ? os.reduce((a, b) => a * b, 1) : NaN;
  const sameMatch = [...byMatch.values()].some(m => m.keys.length > 1);
  return { p, O, missing, sameMatch };
}

function summaryHtml() {
  if (!S.legs.length) return '';
  const c = parlayCalc();
  if (c.missing) return '<p class="note">Hay selecciones de partidos que ya no están en los datos. Quítalas para calcular el parlay.</p>';
  let notes = '';
  if (c.sameMatch) notes += '<p class="note">Hay varias selecciones del mismo partido: están correlacionadas, así que el modelo las calcula juntas con la tabla de marcadores. Muchas casas de apuestas no aceptan combinarlas en un parlay (o pagan menos).</p>';
  if (c.p === 0) notes += '<p class="note">Estas selecciones no pueden cumplirse a la vez (probabilidad 0).</p>';
  const hasOdds = Number.isFinite(c.O);
  const ev = hasOdds ? c.p * c.O - 1 : NaN;
  const bank = num(S.bankroll);
  const stake = hasOdds && bank > 0 ? bank * kelly(c.p, c.O) / 4 : NaN;
  return notes + `<div class="stats">
      <div>Prob. modelo<b>${pct(c.p, 2)}</b></div>
      <div>Cuota justa<b>${fair(c.p)}</b></div>
      <div>Cuota combinada<b>${hasOdds ? c.O.toFixed(2) : '—'}</b></div>
      <div>Valor esperado (EV)<b class="${ev > 0 ? 'value' : ''}">${hasOdds ? (ev > 0 ? '+' : '') + pct(ev) : '—'}</b></div>
      <div style="grid-column:1/-1">Apuesta sugerida (¼ Kelly)<b>${Number.isFinite(stake) ? '$' + stake.toFixed(2) : '—'}</b></div>
    </div>
    <p class="muted small">${!hasOdds ? 'Escribe la cuota decimal de tu casa de apuestas en cada selección.'
      : ev > 0 ? 'EV = prob. × cuota − 1. Kelly ¼ reduce el riesgo si el modelo se equivoca.'
      : 'Sin ventaja según el modelo: la apuesta sugerida es $0.'}</p>`;
}

function viewParlay() {
  const legs = S.legs.map((l, i) => {
    const f = fixture(l.fid);
    const home = f ? f.home : l.home || '?', away = f ? f.away : l.away || '?';
    const sub = f ? `${esc(home)} vs ${esc(away)} · modelo ${pct(prob(grid(f), [l.key]))}` : 'Partido no disponible';
    return `<div class="leg"><div><b>${esc(marketLabel(l.key, home, away))}</b><br><span class="muted small">${sub}</span></div>
      <input data-act="odds" data-i="${i}" inputmode="decimal" placeholder="cuota" aria-label="Cuota" value="${esc(l.odds ?? '')}">
      <button class="ghost" data-act="del" data-i="${i}" aria-label="Quitar">✕</button></div>`;
  }).join('');
  const saved = S.saved.map((s, i) => `<div class="leg"><div><b>${esc(s.name)}</b><br>
      <span class="muted small">${s.legs.length} selecciones · ${new Date(s.at).toLocaleDateString('es-MX')}</span></div>
      <button class="ghost" data-act="load" data-i="${i}">Cargar</button>
      <button class="ghost" data-act="rm" data-i="${i}" aria-label="Borrar">✕</button></div>`).join('');
  return `<h1>Parlay</h1>
    <div class="card">${legs || '<p class="muted">Aún no hay selecciones. Abre un partido y toca un mercado para agregarlo.</p>'}</div>
    ${S.legs.length ? `<div class="card">
      <div class="row" style="margin-bottom:.6rem"><label for="bank">Bankroll ($)</label>
        <input id="bank" data-act="bank" inputmode="decimal" value="${esc(S.bankroll)}"></div>
      <div id="summary">${summaryHtml()}</div></div>
    <div class="card"><div class="row"><input id="pname" class="wide" placeholder="Nombre del parlay">
      <button class="btn" data-act="save">Guardar</button></div>
      <p style="margin:.6rem 0 0"><button class="ghost" data-act="clear">Vaciar parlay</button></p></div>` : ''}
    ${saved ? `<h2>Guardados</h2><div class="card">${saved}</div>` : ''}`;
}

// ---------- Modelo ----------
function calibSvg(bins) {
  const W = 300, P = 34, L = W - P - 10;
  const x = v => +(P + v * L).toFixed(1), y = v => +(W - P - v * L).toFixed(1);
  const maxN = Math.max(...bins.map(b => b.n || 1));
  const pts = [...bins].sort((a, b) => a.pred - b.pred);
  const ticks = [0, 0.25, 0.5, 0.75, 1].map(t => `
    <line x1="${x(t)}" y1="${y(0)}" x2="${x(t)}" y2="${y(1)}" style="stroke:var(--line)"/>
    <line x1="${x(0)}" y1="${y(t)}" x2="${x(1)}" y2="${y(t)}" style="stroke:var(--line)"/>
    <text x="${x(t)}" y="${y(0) + 13}" text-anchor="middle">${t * 100}%</text>
    <text x="${x(0) - 4}" y="${y(t) + 3}" text-anchor="end">${t * 100}%</text>`).join('');
  return `<svg class="calib" viewBox="0 0 ${W} ${W}" role="img" aria-label="Calibración: probabilidad predicha contra frecuencia observada">
    ${ticks}
    <line x1="${x(0)}" y1="${y(0)}" x2="${x(1)}" y2="${y(1)}" style="stroke:var(--muted)" stroke-dasharray="4 4"/>
    <polyline fill="none" style="stroke:var(--accent)" stroke-width="2" points="${pts.map(b => `${x(b.pred)},${y(b.obs)}`).join(' ')}"/>
    ${pts.map(b => `<circle cx="${x(b.pred)}" cy="${y(b.obs)}" r="${(2.5 + 6 * Math.sqrt((b.n || 1) / maxN)).toFixed(1)}" style="fill:var(--accent)" fill-opacity=".75"><title>Predicho ${pct(b.pred)} · observado ${pct(b.obs)} · n=${b.n}</title></circle>`).join('')}
    <text x="${x(0.5)}" y="${W - 4}" text-anchor="middle">Probabilidad del modelo</text>
    <text x="10" y="${y(0.5)}" text-anchor="middle" transform="rotate(-90 10 ${y(0.5)})">Frecuencia observada</text>
  </svg>`;
}

function viewModelo() {
  const { backtest: b, model: m } = S.data;
  const row = (name, mod, mkt, d) => {
    const better = mkt == null || mod == null ? '' : mod < mkt ? 'model' : 'market';
    return `<tr><td>${name}</td><td${better === 'model' ? ' class="value"' : ''}>${mod?.toFixed(d) ?? '—'}</td>
      <td${better === 'market' ? ' class="value"' : ''}>${mkt?.toFixed(d) ?? '—'}</td></tr>`;
  };
  const bt = b ? `<div class="card"><h2>Backtest (sin ver el futuro)</h2>
      <p class="muted small">${b.n} partidos · ${esc(b.from)} a ${esc(b.to)} · menor es mejor</p>
      <table><tr><th>Métrica</th><th>Modelo</th><th>Mercado</th></tr>
        ${row('RPS', b.rps_model, b.rps_market, 4)}${row('Log loss', b.logloss_model, b.logloss_market, 3)}</table></div>
    ${b.calibration?.length ? `<div class="card"><h2>Calibración</h2>${calibSvg(b.calibration)}
      <p class="muted small">Cada punto agrupa predicciones parecidas (local, empate y visita). Si el modelo está bien calibrado, los puntos caen sobre la diagonal: cuando dice 40%, pasa cerca del 40% de las veces. El tamaño indica cuántos casos hay.</p></div>` : ''}`
    : '<p class="muted">No hay datos de backtest.</p>';
  return `<h1>Modelo</h1>
    <p class="note"><b>Probabilidades, no certezas.</b> Un 60% significa que de cada 10 partidos así el favorito gana unos 6 y no gana 4. Las casas de apuestas conocen lesiones, alineaciones y movimientos de dinero, y además cobran un margen: ganarles a largo plazo es muy difícil. Si el mercado tiene mejor RPS o log loss que el modelo, el mercado predice mejor. Apuesta solo lo que estés dispuesto a perder.</p>
    ${bt}
    ${m ? `<div class="card"><h2>Parámetros</h2><table>
      <tr><td>Modelo</td><td>${esc(m.name)}</td></tr>
      <tr><td>Partidos usados</td><td>${m.n_matches ?? '—'}</td></tr>
      <tr><td>Ventaja de local (log)</td><td>${m.home_adv ?? '—'}</td></tr>
      <tr><td>ρ (ajuste de marcadores bajos)</td><td>${m.rho ?? '—'}</td></tr>
      <tr><td>ξ (peso de partidos recientes)</td><td>${m.xi ?? '—'}</td></tr></table>
      <p class="muted small">Dixon–Coles: cada equipo tiene fuerza de ataque y defensa; de ahí salen los goles esperados de cada lado y una tabla de marcadores (Poisson con corrección para 0–0, 1–0, 0–1 y 1–1). Todos los mercados salen de esa tabla.</p></div>` : ''}`;
}

// ---------- Shell ----------
function updateCount() {
  const c = $('#nlegs');
  c.hidden = !S.legs.length;
  c.textContent = S.legs.length;
}

function render() {
  const h = location.hash.slice(1) || '/';
  let html, tab = 'partidos';
  if (h.startsWith('/partido/')) html = viewPartido(decodeURIComponent(h.slice(9)));
  else if (h === '/parlay') { html = viewParlay(); tab = 'parlay'; }
  else if (h === '/modelo') { html = viewModelo(); tab = 'modelo'; }
  else html = viewPartidos();
  view.innerHTML = html;
  document.querySelectorAll('.tabs a').forEach(a => a.classList.toggle('on', a.dataset.tab === tab));
  updateCount();
}

document.addEventListener('click', e => {
  const t = e.target.closest('[data-act]');
  if (!t || !S.data) return;
  const act = t.dataset.act, i = Number(t.dataset.i);
  if (act === 'leg') return toggleLeg(t);
  if (act === 'del') S.legs.splice(i, 1);
  else if (act === 'clear') S.legs = [];
  else if (act === 'load') S.legs = S.saved[i].legs.filter(l => l && isMarket(l.key)).map(l => ({ ...l }));
  else if (act === 'save' || act === 'rm') {
    if (act === 'rm') {
      if (!confirm('¿Borrar este parlay guardado?')) return;
      S.saved.splice(i, 1);
    } else {
      const name = $('#pname').value.trim() || 'Parlay ' + new Date().toLocaleString('es-MX', { dateStyle: 'short', timeStyle: 'short' });
      S.saved.unshift({ name, at: new Date().toISOString(), legs: S.legs.map(l => ({ ...l })) });
    }
    save('bp.saved', S.saved);
  } else return;
  save('bp.legs', S.legs);
  render();
});

document.addEventListener('input', e => {
  const t = e.target;
  if (t.dataset.act === 'odds') { S.legs[Number(t.dataset.i)].odds = t.value; save('bp.legs', S.legs); }
  else if (t.dataset.act === 'bank') { S.bankroll = t.value; save('bp.bankroll', S.bankroll); }
  else return;
  const s = $('#summary');
  if (s) s.innerHTML = summaryHtml();
});

window.addEventListener('hashchange', () => { render(); window.scrollTo(0, 0); });

if ('serviceWorker' in navigator) navigator.serviceWorker.register('sw.js').catch(() => {});

(async () => {
  try {
    const r = await loadData();
    S.data = r.data;
    S.sample = r.sample;
  } catch {
    view.innerHTML = '<p>No se pudieron cargar los datos. Revisa tu conexión e intenta de nuevo.</p>';
    return;
  }
  S.data.fixtures = (S.data.fixtures || []).filter(f => f && f.id && f.kickoff && f.lambda > 0 && f.mu > 0);
  $('#badge').hidden = !S.sample;
  if (S.data.generated_at) $('#updated').textContent = 'Actualizado ' + new Date(S.data.generated_at).toLocaleDateString('es-MX', { day: 'numeric', month: 'short' });
  render();
})();
