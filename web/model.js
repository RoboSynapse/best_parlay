// Dixon–Coles score grid and the markets derived from it. Pure functions, no DOM.

export const MAXG = 10;

function poisson(l) {
  const p = [Math.exp(-l)];
  for (let k = 1; k <= MAXG; k++) p.push(p[k - 1] * l / k);
  return p;
}

// grid[h][a] = P(home scores h, away scores a), 0..MAXG goals, renormalised.
export function scoreGrid(lam, mu, rho) {
  const px = poisson(lam), py = poisson(mu);
  const tau = (h, a) =>
    h === 0 && a === 0 ? 1 - lam * mu * rho :
    h === 0 && a === 1 ? 1 + lam * rho :
    h === 1 && a === 0 ? 1 + mu * rho :
    h === 1 && a === 1 ? 1 - rho : 1;
  let s = 0;
  const g = px.map((ph, h) => py.map((pa, a) => {
    const v = Math.max(0, ph * pa * tau(h, a));
    s += v;
    return v;
  }));
  return g.map(row => row.map(v => v / s));
}

// Single markets: key -> [test(h, a), label template]. {h}/{a} = team names.
const BASE = {
  '1': [(h, a) => h > a, 'Gana {h}'],
  'X': [(h, a) => h === a, 'Empate'],
  '2': [(h, a) => h < a, 'Gana {a}'],
  '1X': [(h, a) => h >= a, '{h} o empate'],
  'X2': [(h, a) => h <= a, 'Empate o {a}'],
  '12': [(h, a) => h !== a, '{h} o {a}'],
  'o15': [(h, a) => h + a > 1.5, 'Más de 1.5 goles'],
  'u15': [(h, a) => h + a < 1.5, 'Menos de 1.5 goles'],
  'o25': [(h, a) => h + a > 2.5, 'Más de 2.5 goles'],
  'u25': [(h, a) => h + a < 2.5, 'Menos de 2.5 goles'],
  'o35': [(h, a) => h + a > 3.5, 'Más de 3.5 goles'],
  'u35': [(h, a) => h + a < 3.5, 'Menos de 3.5 goles'],
  'by': [(h, a) => h > 0 && a > 0, 'Ambos anotan: sí'],
  'bn': [(h, a) => h === 0 || a === 0, 'Ambos anotan: no'],
};

const COMBOS = [];
for (const r of ['1', 'X', '2']) for (const m of ['o25', 'u25', 'by', 'bn']) COMBOS.push(r + '+' + m);

export const GROUPS = [
  ['Resultado (1X2)', ['1', 'X', '2']],
  ['Doble oportunidad', ['1X', 'X2', '12']],
  ['Goles', ['o15', 'u15', 'o25', 'u25', 'o35', 'u35']],
  ['Ambos anotan', ['by', 'bn']],
  ['Combinadas', COMBOS],
];

// A key is one base market or several joined with '+' (all must hold).
export function isMarket(key) {
  return typeof key === 'string' && key.split('+').every(k => k in BASE);
}

export function marketLabel(key, home, away) {
  return key.split('+')
    .map(k => BASE[k][1].replace('{h}', home).replace('{a}', away))
    .join(' y ');
}

// P(all keys hold) — sums grid cells, so same-match legs are combined jointly.
export function prob(grid, keys) {
  const tests = keys.flatMap(k => k.split('+')).map(k => BASE[k][0]);
  let p = 0;
  grid.forEach((row, h) => row.forEach((v, a) => {
    if (tests.every(t => t(h, a))) p += v;
  }));
  return p;
}

// Kelly fraction for decimal odds; 0 when there is no edge.
export function kelly(p, odds) {
  if (!(odds > 1) || !(p > 0)) return 0;
  return Math.max(0, (p * odds - 1) / (odds - 1));
}
