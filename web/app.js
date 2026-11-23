import { scoreGrid, GROUPS, isMarket, marketLabel, prob, kelly, toDecimal, settle } from './model.js';

const $ = sel => document.querySelector(sel);
const view = $('#view');
const esc = s => String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
const pct = (p, d = 1) => (100 * p).toFixed(d) + '%';
const fair = p => (p > 0.001 ? (1 / p).toFixed(2) : '—');
const num = s => parseFloat(String(s).replace(',', '.'));
const SIDE = { '1': 'home', 'X': 'draw', '2': 'away' };
// football-data.co.uk names (no accents) -> how people write them. Data keeps the canonical name; tn() is display only.
const NAME = {
  'Club America': 'América', 'Club Leon': 'León', 'Juarez': 'Juárez', 'Queretaro': 'Querétaro',
  'Mazatlan FC': 'Mazatlán', 'Atl. San Luis': 'Atlético de San Luis', 'Guadalajara Chivas': 'Chivas',
  'UNAM Pumas': 'Pumas', 'Tigres UANL': 'Tigres', 'Club Tijuana': 'Tijuana',
  'Man United': 'Manchester United', 'Man City': 'Manchester City', "Nott'm Forest": 'Nottingham Forest',
  'Ath Madrid': 'Atlético de Madrid', 'Ath Bilbao': 'Athletic Club', 'Betis': 'Real Betis', 'Sociedad': 'Real Sociedad',
  'Celta': 'Celta de Vigo', 'Vallecano': 'Rayo Vallecano', 'Espanol': 'Espanyol', 'Alaves': 'Alavés', 'Cadiz': 'Cádiz',
  'Almeria': 'Almería', 'Leganes': 'Leganés', 'Malaga': 'Málaga', 'La Coruna': 'Deportivo La Coruña', 'Sp Gijon': 'Sporting de Gijón',
  'Bayern Munich': 'Bayern Múnich', "M'gladbach": 'Mönchengladbach', 'Ein Frankfurt': 'Eintracht Frankfurt', 'FC Koln': 'Colonia',
  'Leverkusen': 'Bayer Leverkusen', 'Hertha': 'Hertha Berlín',
  'Union Berlin': 'Unión Berlín', 'Fortuna Dusseldorf': 'Fortuna Düsseldorf',
  'Nurnberg': 'Núremberg', 'Greuther Furth': 'Greuther Fürth', 'St Pauli': 'St. Pauli',
  'Verona': 'Hellas Verona', 'Paris SG': 'PSG', 'St Etienne': 'Saint-Étienne', 'Nimes': 'Nîmes', 'Ajaccio GFCO': 'Gazélec Ajaccio',
};
const tn = name => NAME[name] || name;
// Filter chips use short names; unknown codes fall back to the name in the data.
const LEAGUE = { mex: 'Liga MX', epl: 'Premier', esp: 'LaLiga', ger: 'Bundesliga', ita: 'Serie A', fra: 'Ligue 1' };
const leagueName = code => LEAGUE[code] || S.data.leagues?.find(l => l.code === code)?.name || code || '';
// Initials badge: hue from the canonical name, hsl(h 50% 28%) keeps white text ≥5.5:1 for every hue.
function crest(name) {
  const words = tn(name).split(/[\s-]+/).filter(w => w && !/^(de|del|la|el|fc|cf|ac|as)$/i.test(w));
  const ini = (words.length > 1 ? words.slice(0, 3).map(w => w[0]).join('') : (words[0] || '?').slice(0, 3)).toUpperCase();
  let h = 0;
  for (const c of name) h = (h * 31 + c.charCodeAt(0)) >>> 0;
  return `<span class="crest" aria-hidden="true" style="--h:${h % 360}">${esc(ini)}</span>`;
}
const started = f => Date.parse(f.kickoff) < Date.now();
const FOOT = `<p class="foot muted small">Solo mayores de 18 · Información, no asesoría · No somos casa de apuestas ·
  Juega con responsabilidad (Línea de la Vida 800 911 2000) · <a href="terminos.html">Términos, fuentes y privacidad</a></p>`;
const TERMS_V = 1;  // bump when terminos.html changes: everyone sees "Antes de empezar" again
const icon = (name, cls) => `<svg class="i${cls ? ' ' + cls : ''}" aria-hidden="true"><use href="icons/ui.svg#${name}"/></svg>`;

function load(key, dflt) {
  try { return JSON.parse(localStorage.getItem(key)) ?? dflt; } catch { return dflt; }
}
function save(key, val) {
  try { localStorage.setItem(key, JSON.stringify(val)); } catch { /* private mode / quota: ignore */ }
}

const S = {
  data: null, sample: false, grids: new Map(), league: load('bp.league', 'all'), mleague: null,
  legs: load('bp.legs', []).filter(l => l && l.fid && isMarket(l.key)),
  bankroll: load('bp.bankroll', ''),
  saved: load('bp.saved', []).filter(s => s && Array.isArray(s.legs)),
};

const fixture = id => S.data.fixtures.find(f => f.id === id);
function grid(f) {
  if (!S.grids.has(f.id)) S.grids.set(f.id, scoreGrid(f.lambda, f.mu, f.rho ?? S.data.leagues?.find(l => l.code === f.league)?.model?.rho ?? 0));
  return S.grids.get(f.id);
}
// Margin-free reference probabilities from the pipeline: Pinnacle, or the books' consensus.
// The backtest shows the (closing) market beats the model.
function ref(f) {
  const m = f.market?.fair;
  return m ? { ...m, label: m.source === 'pinnacle' ? 'Pinnacle' : 'Consenso' } : null;
}
const stamp = iso => new Date(iso).toLocaleString('es-MX', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
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
// Leagues present in fixtures or results, in LEAGUE order (unknown codes last).
function leaguesIn() {
  const have = new Set([...S.data.fixtures, ...S.data.results].map(x => x.league).filter(Boolean));
  return [...new Set([...Object.keys(LEAGUE), ...have])].filter(c => have.has(c));
}
const chips = (act, codes, on, all) => `<div class="chips" role="group" aria-label="Liga">${(all ? ['all', ...codes] : codes).map(c =>
  `<button class="chip" data-act="${act}" data-code="${esc(c)}" aria-pressed="${c === on}">${c === 'all' ? 'Todas' : esc(leagueName(c))}</button>`).join('')}</div>`;
const tag = code => code ? `<span class="tag">${esc(leagueName(code))}</span>` : '';

function resultsHtml(rs) {
  if (!rs.length) return '';
  const day = d => new Date(d + 'T12:00:00').toLocaleDateString('es-MX', { day: 'numeric', month: 'short' });
  const by = new Map();
  for (const r of [...rs].sort((a, b) => b.date.localeCompare(a.date))) {
    if (!by.has(r.league)) by.set(r.league, []);
    by.get(r.league).push(r);
  }
  return '<h2 class="sec">Resultados recientes</h2>' + [...by].map(([lg, list]) => `<div class="card board">${tag(lg)}
    ${list.map(r => `<div class="score"><span class="d muted small">${day(r.date)}</span><span class="h">${esc(tn(r.home))}</span>
      <b>${r.hg}–${r.ag}</b><span class="a">${esc(tn(r.away))}</span></div>`).join('')}</div>`).join('');
}

function viewPartidos() {
  const codes = leaguesIn();
  if (S.league !== 'all' && !codes.includes(S.league)) S.league = 'all';
  const mine = x => S.league === 'all' || x.league === S.league;
  const list = S.data.fixtures.filter(mine).sort((a, b) => a.kickoff.localeCompare(b.kickoff));
  const head = '<h1>Próximos partidos</h1>' + (codes.length > 1 ? chips('league', codes, S.league, true) : '');
  const res = resultsHtml(S.data.results.filter(mine));
  if (!list.length) return head + `<div class="empty">${icon('pitch', 'art')}<p class="muted">No hay partidos próximos${S.league === 'all' ? '' : ' de ' + esc(leagueName(S.league))} en los datos.</p></div>` + res;
  const now = Date.now();
  const anyMarket = list.some(f => f.market);
  return head
    + (anyMarket ? '<p class="muted small"><span class="value">Resaltado</span> = ese momio paga más de lo justo. El % es la ganancia esperada si consigues ese momio.</p>' : '')
    + list.map(f => {
    const g = grid(f);
    const p = ['1', 'X', '2'].map(k => prob(g, [k]));
    const r = ref(f);
    const model = p.map(pi => `<td>${pct(pi, 0)}</td>`).join('');
    // the reference (or the model when there is none) gets the big numbers
    const main = r ? `<tr class="big"><td>${r.label}</td>${['home', 'draw', 'away'].map(s => `<td>${pct(r[s], 0)}</td>`).join('')}</tr>
        <tr class="muted small"><td>Nuestro modelo</td>${model}</tr>`
      : `<tr class="big"><td>Nuestro modelo</td>${model}</tr>`;
    const best = r
      ? `<tr><td>Mejor momio<br><span class="muted small">(alguna casa)</span></td>${['home', 'draw', 'away'].map(s => {
           const o = f.market[s], edge = r[s] * o - 1;
           return edge > 0 ? `<td class="value">${o.toFixed(2)}<br><span class="small">${icon('trend')}+${pct(edge)} valor</span></td>` : `<td>${o.toFixed(2)}</td>`;
         }).join('')}</tr>`
      : '<tr><td colspan="4" class="muted small">Aún no hay momios de referencia para este partido.</td></tr>';
    const past = new Date(f.kickoff).getTime() < now;
    return `<a class="card tile${past ? ' past' : ''}" href="#/partido/${encodeURIComponent(f.id)}">
      <div class="row meta">${tag(f.league)}<span class="kick">${icon('clock')} ${when(f.kickoff)}${past ? ' · ya comenzó' : ''}</span></div>
      <div class="teams"><span class="team">${crest(f.home)}${esc(tn(f.home))}</span><span class="team">${crest(f.away)}${esc(tn(f.away))}</span>${icon('chevron-right', 'go')}</div>
      <table><tr><th></th><th>Local</th><th>Empate</th><th>Visita</th></tr>
        ${main}${best}</table></a>`;
  }).join('')
    + (anyMarket ? '<p class="muted small">Pinnacle = probabilidad de sus momios (de la última actualización) sin margen (si no cotiza, el consenso de las casas). En el backtest, el mercado predijo mejor que nuestro modelo. Un momio resaltado paga más de lo justo según esa referencia (prob. × momio &gt; 1); suele estar en una casa extranjera, así que compáralo con el de tu casa.</p>' : '')
    + res;
}

// ---------- Partido ----------
function marketButton(f, g, k) {
  const p = prob(g, [k]);
  const on = S.legs.some(l => l.fid === f.id && l.key === k);
  let extra = '';
  const r = SIDE[k] && ref(f);
  if (r) {
    const s = SIDE[k], o = f.market[s], edge = r[s] * o - 1;
    extra = `<span class="ref muted small">${r.label} ${pct(r[s])} (momio justo ${fair(r[s])}) · mejor momio ${o.toFixed(2)}${edge > 0 ? ` <span class="value">${icon('trend')}+${pct(edge)} valor</span>` : ''}</span>`;
  }
  return `<button class="mk${on ? ' on' : ''}" data-act="leg" data-fid="${esc(f.id)}" data-key="${k}"${started(f) ? ' disabled' : ''}>
    <span class="lbl">${icon('plus', 'add')}${icon('check', 'added')}${esc(marketLabel(k, tn(f.home), tn(f.away)))}</span>
    <span class="nums">Modelo <b>${pct(p)}</b> (momio justo ${fair(p)})</span>${extra}</button>`;
}

function viewPartido(id) {
  const f = fixture(id);
  if (!f) return '<p>Partido no encontrado. <a href="#/">Volver a partidos</a></p>';
  const g = grid(f), N = 6;
  let max = 0;
  for (let h = 0; h < N; h++) for (let a = 0; a < N; a++) max = Math.max(max, g[h][a]);
  const heat = Array.from({ length: N }, (_, h) =>
    `<tr><th>${h}</th>${Array.from({ length: N }, (_, a) => {
      const al = 0.45 * g[h][a] / max;  // light shading keeps the numbers ≥4.5:1 in both themes
      return `<td style="--a:${al.toFixed(2)}">${(100 * g[h][a]).toFixed(1)}</td>`;
    }).join('')}</tr>`).join('');
  const top = g.flatMap((row, h) => row.map((p, a) => ({ h, a, p }))).sort((x, y) => y.p - x.p).slice(0, 5);
  const buttons = keys => keys.map(k => marketButton(f, g, k)).join('');
  return `<p class="nav"><a class="back" href="#/">${icon('chevron-left')}Partidos</a></p>
    <p class="row meta">${tag(f.league)}<span class="kick">${icon('clock')} ${when(f.kickoff)}</span></p>
    <h1 class="match"><span class="team">${crest(f.home)}${esc(tn(f.home))}</span><span class="vs">vs</span><span class="team">${crest(f.away)}${esc(tn(f.away))}</span></h1>
    <p class="muted small">${started(f) ? 'Ya comenzó · ' : ''}Goles esperados ${f.lambda.toFixed(2)} – ${f.mu.toFixed(2)}</p>
    ${started(f) ? `<p class="note">${icon('info')}Este partido ya comenzó: las probabilidades son de antes del partido y no sirven para apostar en vivo.</p>` : ''}
    ${f.market ? '' : `<p class="note">${icon('info')}Aún no hay momios de referencia para este partido: solo se muestra nuestro modelo.</p>`}
    <p class="muted small">Toca un resultado para agregarlo (o quitarlo) del parlay. Momio justo = 1 ÷ probabilidad del modelo.</p>
    <div class="card"><h2>${GROUPS[0][0]}</h2>${buttons(GROUPS[0][1])}</div>
    <details class="card"><summary>Marcadores y mapa</summary>
      <h3>Marcadores más probables</h3>
      <table><tr><th>Marcador</th><th>Prob.</th><th>Momio justo</th></tr>
      ${top.map(s => `<tr><td>${s.h}–${s.a}</td><td>${pct(s.p)}</td><td>${fair(s.p)}</td></tr>`).join('')}</table>
      <h3 style="margin-top:.8rem">Mapa de marcadores (%)</h3>
      <table class="heat"><tr><th></th><th colspan="${N}">Goles ${esc(tn(f.away))} →</th></tr>
        <tr><th>${esc(tn(f.home))} ↓</th>${Array.from({ length: N }, (_, a) => `<th>${a}</th>`).join('')}</tr>${heat}</table>
    </details>
    ${GROUPS.slice(1).map(([title, keys]) => `<details class="card"><summary>${title}</summary>${buttons(keys)}</details>`).join('')}`;
}

function toggleLeg(btn) {
  const { fid, key } = btn.dataset;
  const i = S.legs.findIndex(l => l.fid === fid && l.key === key);
  if (i >= 0) S.legs.splice(i, 1);
  else {
    const f = fixture(fid);
    if (started(f)) return;
    // no pre-filled odds: the best price is often from a book the user can't bet at
    // league, canonical names and kickoff let the leg find its result after the fixture leaves the data
    S.legs.push({ fid, key, odds: '', league: f.league, home: f.home, away: f.away, kickoff: f.kickoff });
  }
  btn.classList.toggle('on', i < 0);
  save('bp.legs', S.legs);
  updateCount();
}

// ---------- Parlay ----------
// Final score of a leg: same league and canonical teams, played within a day of kickoff (UTC date vs local date).
function resultOf(l) {
  if (!l.league || !l.kickoff) return null;  // legs saved before results existed stay Pendiente
  const k = Date.parse(String(l.kickoff).slice(0, 10));
  return S.data.results.find(r => r.league === l.league && r.home === l.home && r.away === l.away
    && Math.abs(Date.parse(r.date) - k) <= 864e5) || null;
}
function legStatus(l) {
  const r = resultOf(l);
  return !r || !isMarket(l.key) ? 'pending' : settle(l.key, r.hg, r.ag) ? 'won' : 'lost';
}
function overall(legs) {
  const st = legs.map(legStatus);
  return st.includes('lost') ? 'lost' : st.length && st.every(x => x === 'won') ? 'won' : 'pending';
}
// leg = selección (Ganada), parlay = Ganado
const badge = (st, parlay) => `<span class="st ${st}">${icon({ won: 'check', lost: 'x', pending: 'clock' }[st])}${
  st === 'pending' ? 'Pendiente' : (st === 'won' ? 'Ganad' : 'Perdid') + (parlay ? 'o' : 'a')}</span>`;

function parlayCalc() {
  const byMatch = new Map(), live = [];
  let missing = false, finished = 0;
  for (const l of S.legs) {
    if (resultOf(l)) { finished++; continue; }  // decided legs leave the calculation
    const f = fixture(l.fid);
    if (!f) { missing = true; continue; }
    live.push(l);
    if (!byMatch.has(f.id)) byMatch.set(f.id, { f, keys: [] });
    byMatch.get(f.id).keys.push(l.key);
  }
  let p = 1;  // joint within a match (score grid), independent across matches
  for (const { f, keys } of byMatch.values()) p *= prob(grid(f), keys);
  const os = live.map(l => toDecimal(l.odds));
  const O = os.length && os.every(o => o > 1) ? os.reduce((a, b) => a * b, 1) : NaN;
  const sameMatch = [...byMatch.values()].some(m => m.keys.length > 1);
  // Pinnacle reference: only for 1X2 legs from different matches (it has no grid for combos).
  let pRef = sameMatch ? NaN : 1, allPin = true;
  for (const l of live) {
    const r = !missing && SIDE[l.key] && ref(fixture(l.fid));
    pRef *= r ? r[SIDE[l.key]] : NaN;
    allPin &&= r?.label === 'Pinnacle';
  }
  const past = [...byMatch.values()].some(m => started(m.f));
  // typo guard: a typed momio far above the best market price (e.g. 18.5 for 1.85)
  const typos = live.filter(l => {
    const f = fixture(l.fid), s = SIDE[l.key];
    return f?.market && s && toDecimal(l.odds) > 1.5 * f.market[s];
  }).map(l => { const f = fixture(l.fid); return `${marketLabel(l.key, tn(f.home), tn(f.away))}: ${l.odds} (mejor del mercado ${f.market[SIDE[l.key]].toFixed(2)})`; });
  return { p, pRef, refLabel: allPin ? 'Pinnacle' : 'consenso', O, missing, sameMatch, past, typos, finished };
}

function summaryHtml() {
  if (!S.legs.length) return '';
  const c = parlayCalc();
  if (c.missing) return `<p class="note">${icon('info')}Hay selecciones de partidos que ya no están en los datos y sin resultado. Quítalas para calcular el parlay.</p>`;
  if (c.finished) {
    // a parlay with a decided leg can't be bet any more: report it, never suggest a stake
    const st = overall(S.legs), hasRef = Number.isFinite(c.pRef);
    return `<p class="note">${icon('info')}${st === 'lost' ? 'Una selección ya perdió: este parlay está <b>perdido</b>.'
      : st === 'won' ? 'Todas las selecciones terminaron y acertaron: este parlay está <b>ganado</b>.'
      : `${c.finished} de ${S.legs.length} selecciones ya terminaron y acertaron; no cuentan en el cálculo. Las que faltan aciertan juntas ${pct(hasRef ? c.pRef : c.p, 1)} de las veces según ${hasRef ? c.refLabel : 'nuestro modelo'}.`}
      El parlay ya empezó, así que no sugerimos apuesta.</p>`;
  }
  let notes = '';
  if (c.sameMatch) notes += `<p class="note">${icon('info')}Hay varias selecciones del mismo partido: están correlacionadas, así que el modelo las calcula juntas con la tabla de marcadores. La casa no paga el producto de los momios en ese caso (muchas ni lo aceptan), así que no calculamos ganancia ni apuesta sugerida.</p>`;
  if (c.p === 0) notes += `<p class="note">${icon('info')}Estas selecciones no pueden cumplirse a la vez (probabilidad 0).</p>`;
  if (c.typos.length) notes += `<p class="note">${icon('info')}¿Escribiste bien el momio? Es mucho mayor que el mejor del mercado: ${c.typos.map(esc).join('; ')}. Corrígelo para ver la apuesta sugerida.</p>`;
  if (c.past) notes +=`<p class="note">${icon('info')}Un partido de este parlay ya comenzó: las probabilidades son de antes del partido y no sirven para apostar en vivo.</p>`;
  const hasOdds = Number.isFinite(c.O) && !c.sameMatch;  // same-match legs: the product of odds isn't what books pay
  const hasRef = Number.isFinite(c.pRef);
  const pBet = hasRef ? c.pRef : c.p;
  const ev = hasOdds ? c.p * c.O - 1 : NaN;
  const evRef = hasOdds && hasRef ? c.pRef * c.O - 1 : NaN;
  const bank = num(S.bankroll);
  // stake only against the market reference: the model alone is less accurate (backtest)
  const canStake = hasOdds && hasRef && !c.past && !S.sample && !S.stale && !c.typos.length;
  const CAP = 0.05;  // never suggest more than 5% of the fund, whatever Kelly says
  const frac = Math.min(kelly(pBet, c.O) / 4, CAP);
  const stake = canStake && bank > 0 ? bank * frac : NaN;
  const evB = e => `<b class="${e > 0 ? 'value' : e < 0 ? 'neg' : ''}">${Number.isFinite(e) ? (e > 0 ? icon('trend') + '+' : '') + pct(e) : '—'}</b>`;
  const evMain = hasRef ? evRef : ev;
  const money = v => '$' + v.toFixed(2);
  return notes + `<div class="verdict">
      <div>Apuesta sugerida: <b>${Number.isFinite(stake) ? money(stake) : '—'}</b>${Number.isFinite(stake) && frac === CAP ? ' <span class="muted small">(tope: 5% de tu fondo)</span>' : ''}</div>
      <div>${c.sameMatch ? 'Sin cálculo para selecciones del mismo partido.'
        : !Number.isFinite(c.O) ? 'Escribe el momio de cada selección.'
        : canStake && !(bank > 0) ? 'Escribe tu fondo para ver la apuesta sugerida.'
        : stake > 0 ? `Si aciertas cobras <b>${money(stake * c.O)}</b>; si fallas (${pct(1 - pBet, 0)} de las veces) pierdes <b>${money(stake)}</b>`
        : `Por cada $100 cobrarías <b>${money(100 * c.O)}</b> si aciertas (${pct(pBet, 0)} de las veces)`}</div>
    </div>
    <div class="stats">
      <div>Probabilidad de acertar<b>${pct(pBet, 2)}</b><span class="muted small">según ${hasRef ? c.refLabel : 'nuestro modelo'}</span></div>
      <div>Ganancia esperada${evB(evMain)}</div>
    </div>
    <details><summary>Ver detalle</summary><div class="stats">
      <div>Prob. modelo<b>${pct(c.p, 2)}</b></div>
      <div>Ganancia esperada (modelo)${evB(ev)}</div>
      <div>Momio justo${hasRef ? ` (${c.refLabel})` : ''}<b>${hasRef ? fair(c.pRef) : '—'}</b></div>
      <div>Momio combinado<b>${Number.isFinite(c.O) ? c.O.toFixed(2) : '—'}</b></div>
    </div></details>
    <p class="muted small">${!Number.isFinite(c.O) ? 'Escribe el momio de tu casa de apuestas en cada selección.'
      : c.sameMatch ? ''
      : !hasRef ? 'Sin referencia de Pinnacle para alguna selección (mercados que no son 1X2 o partido sin momios): la probabilidad es de nuestro modelo, que en el backtest es menos preciso que el mercado, así que no sugerimos apuesta.'
      : evMain > 0 ? `Tu momio paga más de lo justo según ${c.refLabel}.`
      : `Tu momio no supera el momio justo de ${c.refLabel}: la apuesta sugerida es $0.`}</p>
    <p class="muted small">Ganancia esperada = lo que ganarías en promedio por cada $100 apostados si hicieras esta apuesta muchas veces (+6% ≈ $6), suponiendo que la probabilidad es correcta. La apuesta sugerida usa ¼ de la fórmula de Kelly, con tope de 5% de tu fondo: más cuando hay ventaja, $0 cuando no. Solo mayores de 18; apuesta solo lo que estés dispuesto a perder.</p>`;
}

function viewParlay() {
  const legs = S.legs.map((l, i) => {
    const f = fixture(l.fid), res = resultOf(l);
    const home = tn(f ? f.home : l.home || '?'), away = tn(f ? f.away : l.away || '?');
    const r = f && SIDE[l.key] && ref(f);
    const sub = res ? `Final: ${esc(tn(res.home))} ${res.hg}–${res.ag} ${esc(tn(res.away))}`
      : f ? `${esc(home)} vs ${esc(away)} · modelo ${pct(prob(grid(f), [l.key]))}`
      + (r ? ` · momio justo ${r.label} ${fair(r[SIDE[l.key]])}` : '') + (started(f) ? ' · ya comenzó' : '') : 'Partido no disponible';
    return `<div class="leg"><div><b>${esc(marketLabel(l.key, home, away))}</b> ${badge(legStatus(l))}<br><span class="muted small">${sub}</span></div>
      <label class="small muted">Momio <input data-act="odds" data-i="${i}" placeholder="ej. 1.85" aria-label="Momio" value="${esc(l.odds ?? '')}"></label>
      <button class="ghost" data-act="del" data-i="${i}" aria-label="Quitar">${icon('x')}</button></div>`;
  }).join('');
  const saved = S.saved.map((s, i) => {
    const ls = s.legs.filter(l => l && isMarket(l.key));
    return `<div class="saved"><div class="leg"><div><b>${esc(s.name)}</b> ${badge(overall(ls), true)}<br>
      <span class="muted small">${s.legs.length} selección${s.legs.length === 1 ? '' : 'es'} · ${new Date(s.at).toLocaleDateString('es-MX')}</span></div>
      <button class="ghost" data-act="load" data-i="${i}">Cargar</button>
      <button class="ghost" data-act="rm" data-i="${i}" aria-label="Borrar">${icon('trash')}</button></div>
      <ul class="slegs">${ls.map(l => `<li><span>${esc(marketLabel(l.key, tn(l.home || '?'), tn(l.away || '?')))}
        <span class="muted small">${esc(tn(l.home || '?'))} vs ${esc(tn(l.away || '?'))}</span></span>${badge(legStatus(l))}</li>`).join('')}</ul></div>`;
  }).join('');
  return `<h1>Parlay</h1>
    <div class="card">${legs ? `<div class="row ptitle"><h2>Tu parlay</h2>${badge(overall(S.legs), true)}</div>` + legs + '<p class="muted small" style="margin:.4rem 0 0">Acepta momio decimal (1.85) o americano (+150 / −120).</p>'
      : `<div class="empty">${icon('ticket')}<p class="muted">Tu parlay está vacío. Elige un partido y toca un resultado (por ejemplo «Gana Monterrey») para agregarlo.</p><a class="btn" href="#/">Ver partidos</a></div>`}</div>
    ${S.legs.length ? `<div class="card">
      <div class="row" style="margin-bottom:.6rem"><label for="bank">Tu fondo para apostar ($)</label>
        <input id="bank" data-act="bank" inputmode="decimal" value="${esc(S.bankroll)}"></div>
      <div id="summary" aria-live="polite">${summaryHtml()}</div></div>
    <div class="card"><div class="row"><input id="pname" class="wide" placeholder="Nombre del parlay" aria-label="Nombre del parlay">
      <button class="btn" data-act="save">${icon('save')} Guardar</button></div>
      <p style="margin:.6rem 0 0"><button class="ghost" data-act="clear">${icon('trash')} Vaciar parlay</button></p></div>` : ''}
    ${saved ? `<h2>Guardados</h2><div class="card">${saved}</div>` : ''}`;
}

// ---------- Modelo ----------
function calibSvg(bins) {
  const W = 300, P = 34, L = W - P - 18;
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
  const ls = S.data.leagues || [];
  const L = ls.find(l => l.code === S.mleague) || ls[0];
  const b = L?.backtest, m = L?.model, lname = esc(L?.name || leagueName(L?.code));
  const row = (name, mod, mkt, d) => {
    const better = mkt == null || mod == null ? '' : mod < mkt ? 'model' : 'market';
    return `<tr><td>${name}</td><td${better === 'model' ? ' class="best"' : ''}>${mod?.toFixed(d) ?? '—'}</td>
      <td${better === 'market' ? ' class="best"' : ''}>${mkt?.toFixed(d) ?? '—'}</td></tr>`;
  };
  const bt = b ? `<div class="card"><h2>Backtest: ${lname}</h2>
      <p class="muted small">${b.n} partidos · ${esc(b.from)} a ${esc(b.to)} · reentrenando cada semana · menor es mejor</p>
      <table><tr><th>Métrica</th><th>Modelo</th><th>Mercado (cierre)</th></tr>
        ${row('RPS (error, menor es mejor)', b.rps_model, b.rps_market, 4)}${row('Log loss', b.logloss_model, b.logloss_market, 3)}</table>
      ${b.rps_market < b.rps_model ? `<p class="small">En ${b.n} partidos de ${lname}, el mercado (Pinnacle al cierre, o el promedio de casas si no hay Pinnacle) predijo un poco mejor que nuestro modelo; por eso usamos los momios de Pinnacle como referencia.</p>` : ''}</div>
    ${b.calibration?.length ? `<div class="card"><h2>Calibración: ${lname}</h2>${calibSvg(b.calibration)}
      <p class="muted small">Cada punto agrupa predicciones parecidas (local, empate y visita). Si el modelo está bien calibrado, los puntos caen sobre la diagonal: cuando dice 40%, pasa cerca del 40% de las veces. El tamaño indica cuántos casos hay.</p></div>` : ''}`
    : '<p class="muted">No hay datos de backtest.</p>';
  return `<h1>Modelo</h1>
    <p class="note">${icon('info')}<b>Probabilidades, no certezas.</b> Un 60% significa que de cada 10 partidos así el favorito gana unos 6 y no gana 4. Las casas de apuestas conocen lesiones, alineaciones y movimientos de dinero, y además cobran un margen: ganarles a largo plazo es muy difícil. Si el mercado tiene mejor RPS o log loss que el modelo, el mercado predice mejor. Apuesta solo lo que estés dispuesto a perder.</p>
    ${ls.length > 1 ? chips('mleague', ls.map(l => l.code), L.code, false) : ''}
    ${bt}
    ${m ? `<div class="card"><h2>Parámetros: ${lname}</h2><table>
      <tr><td>Modelo</td><td>${esc(m.name)}</td></tr>
      <tr><td>Partidos usados</td><td>${m.n_matches ?? '—'}</td></tr>
      <tr><td>Ventaja de local (log)</td><td>${m.home_adv ?? '—'}</td></tr>
      <tr><td>ρ (ajuste de marcadores bajos)</td><td>${m.rho ?? '—'}</td></tr>
      <tr><td>ξ (peso de partidos recientes)</td><td>${m.xi ?? '—'}</td></tr></table>
      <p class="muted small">Dixon–Coles: cada equipo tiene fuerza de ataque y defensa; de ahí salen los goles esperados de cada lado y una tabla de marcadores (Poisson con corrección para 0–0, 1–0, 0–1 y 1–1). Todos los mercados salen de esa tabla. Se ajusta por separado en cada liga. Explicación paso a paso en <a href="aprende.html#modelo">Aprende</a>.</p></div>` : ''}
    <p class="muted small">Aviso legal, juego responsable, fuentes, marcas y privacidad: <a href="terminos.html">Términos</a>.</p>`;
}

// ---------- Antes de empezar (terms) ----------
// Shown before the tutorial until accepted; acceptance is stored (versioned) only on this device.
function terms(minor) {
  const d = $('#tour');
  d.dataset.mode = 'terms';
  d.innerHTML = minor
    ? `${icon('info', 'big')}<h2 id="tour-t">Solo para mayores de 18</h2>
      <p>Esta app es solo para mayores de 18 años. Si apostar te preocupa a ti o a alguien cercano, puedes llamar gratis a la Línea de la Vida: <a href="tel:8009112000">800 911 2000</a> (24 h).</p>
      <div class="row"><button class="ghost" data-act="terms" data-i="0">‹ Volver</button></div>`
    : `${icon('info', 'big')}<h2 id="tour-t">Antes de empezar</h2>
      <ul class="terms">
        <li><b>Solo mayores de 18.</b></li>
        <li><b>Información, no asesoría:</b> las probabilidades pueden fallar y la apuesta sugerida es solo un cálculo.</li>
        <li><b>No somos casa de apuestas:</b> no aceptamos apuestas ni manejamos dinero.</li>
        <li><b>Tus datos se quedan en tu teléfono:</b> sin cuentas, cookies ni analítica.</li>
        <li><b>Juega con responsabilidad.</b> ¿Ayuda? Línea de la Vida 800 911 2000.</li>
      </ul>
      <p class="small"><a href="terminos.html">Leer los términos completos ›</a></p>
      <div class="row"><button class="ghost" data-act="terms" data-i="-1">Soy menor de 18</button>
        <button class="btn" data-act="terms" data-i="1">Tengo 18 o más y entiendo</button></div>`;
  if (!d.open) d.showModal();
  (d.querySelector('.btn') || d.querySelector('.ghost')).focus();
}

// ---------- Tutorial ----------
const installed = matchMedia('(display-mode: standalone)').matches || navigator.standalone;
const TOUR = [
  ['ticket', '¿Qué es un parlay?', 'Juntas varias selecciones en una sola apuesta. Los momios se multiplican: 2.00 × 1.80 = 3.60, así que $100 cobran $360… pero <b>tienes que acertar todas</b>. Si una falla, pierdes la apuesta.'],
  ['info', 'Probabilidad y momio justo', 'Cada resultado muestra qué tan probable es. El momio justo = 1 ÷ probabilidad (50% → 2.00). Usamos como referencia los momios de Pinnacle sin su margen (o el consenso de las casas si Pinnacle no cotiza); «Nuestro modelo» es una segunda opinión.'],
  ['trend', '¿Qué es «valor»?', `Un momio <span class="value">resaltado</span> paga más de lo justo: «+5% valor» significa que, si consigues ese momio, a la larga ganarías unos $5 por cada $100 apostados (si la referencia acierta). Ese momio suele estar en una casa extranjera: compáralo con el de tu casa en la pestaña Parlay.`],
  ['plus', 'Arma tu parlay', 'Hay partidos de la Liga MX y de las grandes ligas de Europa (Premier League, LaLiga, Bundesliga, Serie A y Ligue 1); filtra por liga arriba de la lista. Abre un partido y toca un resultado (+) para agregarlo. En la pestaña <b>Parlay</b> escribe el momio de tu casa de apuestas: sirve decimal (1.85) o americano (+150 / −120).'],
  ['chart', '¿Cuánto apostar?', 'Escribe tu fondo y la app sugiere una apuesta prudente (¼ de Kelly). Si dice $0, no hay ventaja: mejor no apostar. Más selecciones = menos probable acertar. <b>Solo mayores de 18.</b> Apuesta solo lo que estés dispuesto a perder.'],
  ...(installed ? [] : [['ball', 'Instala la app', (/iPhone|iPad/.test(navigator.userAgent)
    ? 'En Safari toca <b>Compartir</b> y luego <b>«Agregar a inicio»</b>.'
    : 'En el menú ⋮ del navegador toca <b>«Instalar app»</b> (o «Agregar a pantalla principal»).')
    + ' Se abre como app y funciona sin conexión con los últimos datos.']]),
];

function tour(i) {
  const d = $('#tour'), [ic, title, body] = TOUR[i], last = i === TOUR.length - 1;
  d.dataset.mode = 'tour';
  d.innerHTML = `${icon(ic, 'big')}<h2 id="tour-t">${title}</h2><p>${body}</p>
    <p class="dots" aria-hidden="true">${TOUR.map((_, j) => `<span${j === i ? ' class="on"' : ''}></span>`).join('')}</p>
    <p class="muted small">Paso ${i + 1} de ${TOUR.length}</p>
    <div class="row">${i ? `<button class="ghost" data-act="tour" data-i="${i - 1}">‹ Atrás</button>` : `<button class="ghost" data-act="tour" data-i="-1">Saltar</button>`}
      <button class="btn" data-act="tour" data-i="${last ? -1 : i + 1}">${last ? '¡Listo!' : 'Siguiente ›'}</button></div>`;
  if (!d.open) d.showModal();
  d.querySelector('.btn').focus();  // innerHTML swap drops focus; keep it on the main action
}
$('#tour').addEventListener('close', e => { if (e.target.dataset.mode === 'tour') save('bp.tour', true); });  // Esc, Saltar and ¡Listo! all count as seen
$('#tour').addEventListener('cancel', e => { if (e.target.dataset.mode === 'terms') e.preventDefault(); });  // Esc can't skip the terms

// ---------- Shell ----------
function updateCount() {
  const c = $('#nlegs'), go = $('#goparlay'), n = S.legs.length;
  c.hidden = !n;
  c.textContent = n;
  go.hidden = !n || location.hash === '#/parlay';
  go.innerHTML = `Ver parlay (${n}) ${icon('chevron-right')}`;
}

function render() {
  const h = location.hash.slice(1) || '/';
  let html, tab = 'partidos';
  if (h.startsWith('/partido/')) {
    let id = '';
    try { id = decodeURIComponent(h.slice(9)); } catch { /* malformed link: shows "no encontrado" */ }
    html = viewPartido(id);
  }
  else if (h === '/parlay') { html = viewParlay(); tab = 'parlay'; }
  else if (h === '/modelo') { html = viewModelo(); tab = 'modelo'; }
  else html = viewPartidos();
  const sample = S.sample ? `<p class="note">${icon('info')}<b>Datos de ejemplo inventados</b> (no se pudieron cargar los reales). No los uses para apostar.</p>` : '';
  const stale = S.stale && !S.sample ? `<p class="note">${icon('info')}<b>Datos atrasados:</b> la última actualización fue el ${esc(stamp(S.data.generated_at))}; partidos y momios pueden haber cambiado y no sugerimos apuestas hasta la próxima actualización.</p>` : '';
  view.innerHTML = sample + stale + html + FOOT;
  document.querySelectorAll('.tabs a').forEach(a => a.classList.toggle('on', a.dataset.tab === tab));
  updateCount();
}

document.addEventListener('click', e => {
  const t = e.target.closest('[data-act]');
  if (!t) return;
  const act = t.dataset.act, i = Number(t.dataset.i);
  if (act === 'retry') return location.reload();
  if (act === 'tour') return i < 0 ? $('#tour').close() : tour(i);
  if (act === 'terms') {
    if (i !== 1) return terms(i < 0);
    save('bp.terms', TERMS_V);
    $('#tour').dataset.mode = '';
    return load('bp.tour', false) ? $('#tour').close() : tour(0);
  }
  if (!S.data) return;
  if (act === 'leg') return toggleLeg(t);
  if (act === 'del') S.legs.splice(i, 1);
  else if (act === 'clear') {
    if (!confirm('¿Vaciar el parlay?')) return;
    S.legs = [];
  }
  else if (act === 'league') { S.league = t.dataset.code; save('bp.league', S.league); }
  else if (act === 'mleague') S.mleague = t.dataset.code;
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
  // re-render drops focus: keep it on the chip that was pressed
  if (act === 'league' || act === 'mleague') $(`[data-act="${act}"][data-code="${CSS.escape(t.dataset.code)}"]`)?.focus();
  if (act === 'save') {
    const b = $('[data-act="save"]');
    b.innerHTML = `${icon('check')} Guardado`;
    setTimeout(() => { b.innerHTML = `${icon('save')} Guardar`; }, 1500);
  }
});

document.addEventListener('input', e => {
  const t = e.target;
  if (t.dataset.act === 'odds') { S.legs[Number(t.dataset.i)].odds = t.value; save('bp.legs', S.legs); }
  else if (t.dataset.act === 'bank') { S.bankroll = t.value; save('bp.bankroll', S.bankroll); }
  else return;
  const s = $('#summary');
  if (!s) return;
  const open = s.querySelector('details')?.open;  // keep "Ver detalle" open while typing
  s.innerHTML = summaryHtml();
  if (open) s.querySelector('details').open = true;
});

let listY = 0;  // scroll of the match list, restored when coming back to it
window.addEventListener('hashchange', e => {
  const isList = h => (h.slice(1) || '/') === '/';
  if (isList(new URL(e.oldURL).hash)) listY = window.scrollY;
  render();
  window.scrollTo(0, isList(location.hash) ? listY : 0);
});

if ('serviceWorker' in navigator) navigator.serviceWorker.register('sw.js').catch(() => {});

(async () => {
  try {
    const r = await loadData();
    S.data = r.data;
    S.sample = r.sample;
  } catch {
    view.innerHTML = `<div class="empty">${icon('wifi-off')}<p>No se pudieron cargar los datos. Revisa tu conexión e intenta de nuevo.</p><button class="btn" data-act="retry">Reintentar</button></div>`;
    return;
  }
  S.data.fixtures = (S.data.fixtures || []).filter(f => f && f.id && f.kickoff && f.lambda > 0 && f.mu > 0);
  S.data.results = (Array.isArray(S.data.results) ? S.data.results : [])
    .filter(r => r && r.home && r.away && /^\d{4}-\d\d-\d\d$/.test(r.date) && Number.isInteger(r.hg) && Number.isInteger(r.ag));
  $('#badge').hidden = !S.sample;
  const gen = Date.parse(S.data.generated_at);
  S.stale = !(Date.now() - gen < 36 * 3600e3);  // missing date or >36 h old: the daily job didn't run
  if (gen) $('#updated').textContent = 'Actualizado ' + stamp(S.data.generated_at);
  render();
  if (load('bp.terms', 0) !== TERMS_V) terms(false);
  else if (!load('bp.tour', false)) tour(0);
})();
