/* render.js — tekent het verzuimdashboard uit window.DATA.
   De data komt uit dashboard.py; hier wordt niets meer gerekend behalve
   optellen per selectie (afdeling/leerjaar-tab en filters). */
(function () {
  'use strict';

  var D          = window.DATA || {};
  var LEERLINGEN = D.leerlingen || [];
  var CODES      = D.codes || {};
  var WEKEN      = D.weken || [];
  var CFG        = D.config || {};
  var GROEPEN    = D.groepen || ['Alle'];

  var NORM_CRIT = CFG.normCrit || 16;
  var NORM_WARN = CFG.normWarn || 10;
  var NORM_LAAT = CFG.normLaat || 6;

  function codeNaam(c) { return (CODES[c] && CODES[c].naam) || c; }

  function status(l) {
    if (l.ong >= NORM_CRIT) return 'crit';
    if (l.ong >= NORM_WARN) return 'warn';
    return 'neut';
  }

  var state = { groep: 'Alle', filter: null, sort: 'ong' };

  function inGroep(l) { return state.groep === 'Alle' || l.groep === state.groep; }
  function basis() { return LEERLINGEN.filter(inGroep); }

  function zichtbaar() {
    var lijst = basis().filter(function (l) { return l.ong > 0 || l.laat > 0; });
    if (state.filter === 'crit') lijst = lijst.filter(function (l) { return status(l) === 'crit'; });
    if (state.filter === 'warn') lijst = lijst.filter(function (l) { return status(l) === 'warn'; });
    if (state.filter === 'laat') lijst = lijst.filter(function (l) { return l.laat >= NORM_LAAT; });

    var s = state.sort;
    return lijst.slice().sort(function (a, b) {
      if (s === 'naam') return a.naam.localeCompare(b.naam, 'nl');
      if (s === 'laat') return b.laat - a.laat || b.ong - a.ong;
      if (s === 'ziek') return b.ziek - a.ziek || b.ong - a.ong;
      return b.ong - a.ong || b.laat - a.laat;
    });
  }

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) {
      return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c];
    });
  }

  var ICO = {
    crit: '<svg class="ico" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" aria-hidden="true"><path d="M8 2.6 1.8 13.4h12.4z"/><path d="M8 6.6v3.2"/><circle cx="8" cy="11.7" r=".55" fill="currentColor" stroke="none"/></svg>',
    warn: '<svg class="ico" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" aria-hidden="true"><circle cx="8" cy="8" r="6"/><path d="M8 4.8V8.4"/><circle cx="8" cy="11.2" r=".55" fill="currentColor" stroke="none"/></svg>',
    late: '<svg class="ico" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="8" cy="8" r="6"/><path d="M8 4.6V8.2l2.4 1.5"/></svg>'
  };

  /* ── Actiebalk ──────────────────────────────────────────────────────────── */
  function tekenActiebalk() {
    var b = basis();
    var nCrit = b.filter(function (l) { return status(l) === 'crit'; }).length;
    var nWarn = b.filter(function (l) { return status(l) === 'warn'; }).length;
    var nLaat = b.filter(function (l) { return l.laat >= NORM_LAAT; }).length;

    var defs = [
      { key: 'crit', cls: 'crit', ico: ICO.crit, n: nCrit, t: 'Meldplicht bereikt',
        s: NORM_CRIT + ' uur of meer ongeoorloofd' },
      { key: 'warn', cls: 'warn', ico: ICO.warn, n: nWarn, t: 'Nadert de grens',
        s: NORM_WARN + ' t/m ' + (NORM_CRIT - 1) + ' uur ongeoorloofd' },
      { key: 'laat', cls: 'late', ico: ICO.late, n: nLaat, t: 'Vaak te laat',
        s: NORM_LAAT + ' keer of vaker deze periode' }
    ];

    document.getElementById('actiebalk').innerHTML = defs.map(function (d) {
      return '<button class="signal ' + d.cls + '" data-signal="' + d.key + '" ' +
        'aria-pressed="' + (state.filter === d.key) + '">' + d.ico +
        '<span class="n">' + d.n + '</span>' +
        '<span class="lbl"><b>' + d.t + '</b>' + d.s + '</span></button>';
    }).join('');
  }

  /* ── Kerncijfers ────────────────────────────────────────────────────────── */
  function tekenTiles() {
    var b = basis();
    var ong  = b.reduce(function (t, l) { return t + l.ong; }, 0);
    var laat = b.reduce(function (t, l) { return t + l.laat; }, 0);
    var ziek = b.reduce(function (t, l) { return t + l.ziek; }, 0);
    var raak = b.filter(function (l) { return l.ong > 0 || l.laat > 0; }).length;
    var gem  = b.length ? (ong / b.length).toFixed(1).replace('.', ',') : '0,0';

    var tiles = [
      { k: 'Leerlingen', v: b.length, d: raak + ' met een registratie deze periode' },
      { k: 'Ongeoorloofde uren', v: ong, u: 'u', d: gem + ' uur per leerling gemiddeld' },
      { k: 'Keer te laat', v: laat,
        d: b.filter(function (l) { return l.laat >= NORM_LAAT; }).length +
           ' leerlingen ' + NORM_LAAT + '× of vaker' },
      { k: 'Ziekte-uren', v: ziek, u: 'u', d: 'geoorloofd, telt niet mee in de norm' }
    ];

    document.getElementById('tiles').innerHTML = tiles.map(function (t) {
      return '<div class="tile"><div class="k">' + t.k + '</div>' +
        '<div class="v">' + t.v + (t.u ? '<small>' + t.u + '</small>' : '') + '</div>' +
        '<div class="d">' + t.d + '</div></div>';
    }).join('');
  }

  /* ── Tabs (afdeling + leerjaar) ─────────────────────────────────────────── */
  function tekenTabs() {
    document.getElementById('tabs').innerHTML = GROEPEN.map(function (g) {
      var n = g === 'Alle' ? LEERLINGEN.length
            : LEERLINGEN.filter(function (l) { return l.groep === g; }).length;
      return '<button class="tab" role="tab" data-groep="' + esc(g) + '" ' +
        'aria-selected="' + (state.groep === g) + '">' +
        esc(g) + '<span class="cnt">' + n + '</span></button>';
    }).join('');
  }

  /* ── Signaleringslijst ──────────────────────────────────────────────────── */
  function tekenLijst() {
    var lijst = zichtbaar();
    var el = document.getElementById('lijst');
    document.getElementById('lijst-telling').textContent =
      lijst.length + ' van ' + basis().length + ' leerlingen';

    if (!lijst.length) {
      el.innerHTML = '<div class="leeg">Geen leerlingen die aan dit filter voldoen.</div>';
      return;
    }

    el.innerHTML = lijst.map(function (l, i) {
      var st = status(l);
      var pct = Math.min(100, l.ong / NORM_CRIT * 100);
      var label = st === 'crit' ? 'Meldplicht'
                : st === 'warn' ? 'Nadert grens'
                : l.ong === 0 ? 'Alleen te laat' : 'In beeld';
      var ico = st === 'crit' ? ICO.crit : st === 'warn' ? ICO.warn
              : l.ong === 0 ? ICO.late : '';

      /* Registraties per dag, nieuwste dag eerst. */
      var perDag = {}, volgorde = [];
      (l.entries || []).forEach(function (e) {
        if (!perDag[e.datum]) { perDag[e.datum] = []; volgorde.push(e.datum); }
        perDag[e.datum].push(e);
      });
      var dagen = volgorde.sort().reverse().map(function (dt) {
        var es = perDag[dt].slice().sort(function (a, b) { return (a.uur || 0) - (b.uur || 0); });
        return '<div class="dag"><span class="dl">' + esc(es[0].daglabel || dt) + '</span>' +
          '<span class="dc">' + es.map(function (e) {
            var cls = e.soort === 'ong' ? ' ong' : e.soort === 'laat' ? ' laat' : '';
            var tip = codeNaam(e.code) + (e.vak ? ' · ' + e.vak : '');
            return '<span class="chip' + cls + '" data-tip="' + esc(tip) + '">' +
              '<b>' + esc(e.code) + '</b> ' + esc(e.uurlabel) + '</span>';
          }).join('') + '</span></div>';
      }).join('');

      var sub = l.klas
        + (l.mentorgroep ? ' · ' + l.mentorgroep : '')
        + (l.mentor ? ' · mentor ' + l.mentor : '');

      return '<details class="rij"' + (i === 0 ? ' open' : '') + '>' +
        '<summary class="rij-hd">' +
          '<span class="stripe ' + st + '"></span>' +
          '<span class="wie"><span class="naam">' + esc(l.naam) + '</span>' +
            '<span class="sub">' + esc(sub) + '</span></span>' +
          '<span class="meter">' +
            '<span class="meter-track">' +
              '<span class="meter-fill ' + st + '" style="width:' + pct.toFixed(1) + '%"></span>' +
              '<span class="meter-mark" data-tip="Meldgrens: ' + NORM_CRIT + ' uur"></span>' +
            '</span>' +
            '<span class="meter-cap"><span><b>' + l.ong + ' u</b> ongeoorloofd</span>' +
              '<span>' + l.laat + '× te laat</span></span>' +
          '</span>' +
          '<span class="rij-eind">' +
            '<span class="pill ' + st + '">' + ico + label + '</span>' +
            '<svg class="chev" width="11" height="11" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6 3l5 5-5 5"/></svg>' +
          '</span>' +
        '</summary>' +
        '<div class="detail">' + (dagen || '<p class="leeg">Geen registraties.</p>') + '</div>' +
      '</details>';
    }).join('');
  }

  /* ── Weektrend ──────────────────────────────────────────────────────────── */
  function tekenWeken() {
    var perWeek = WEKEN.map(function () { return { ong: 0, geo: 0 }; });
    basis().forEach(function (l) {
      (l.entries || []).forEach(function (e) {
        var w = perWeek[e.week];
        if (!w) return;
        if (e.soort === 'ong') w.ong++;
        else if (e.soort === 'geo') w.geo++;
      });
    });
    var max = Math.max.apply(null, perWeek.map(function (w) { return w.ong + w.geo; })) || 1;

    document.getElementById('weken').innerHTML = perWeek.map(function (w, i) {
      var tot = w.ong + w.geo;
      var breedte = tot / max * 100;
      return '<div class="bar-row">' +
        '<span class="bar-lbl"><b>' + esc(WEKEN[i].label) + '</b><br>' + esc(WEKEN[i].sub) + '</span>' +
        '<span class="bar-track">' +
          '<span class="bar-stack" style="max-width:' + breedte.toFixed(1) + '%">' +
            (w.ong ? '<span class="seg" style="flex:' + w.ong + ';background:var(--s-ongeoorloofd)" ' +
              'data-tip="Ongeoorloofd: ' + w.ong + ' uur"></span>' : '') +
            (w.geo ? '<span class="seg" style="flex:' + w.geo + ';background:var(--s-geoorloofd)" ' +
              'data-tip="Geoorloofd: ' + w.geo + ' uur"></span>' : '') +
          '</span>' +
          '<span class="bar-val">' + tot + '</span>' +
        '</span></div>';
    }).join('');
  }

  /* ── Per mentorgroep ────────────────────────────────────────────────────── */
  function tekenGroepen() {
    var perGroep = {};
    basis().forEach(function (l) {
      var sleutel = l.mentorgroep || l.klas;          // geen mentorgroep? dan de klas
      var g = perGroep[sleutel] ||
        (perGroep[sleutel] = { naam: sleutel, mentor: l.mentor, ong: 0, n: 0 });
      g.ong += l.ong; g.n++;
      if (!g.mentor && l.mentor) g.mentor = l.mentor;
    });
    var rijen = Object.keys(perGroep).map(function (k) { return perGroep[k]; })
      .sort(function (a, b) { return b.ong - a.ong; }).slice(0, 10);
    var max = rijen.length ? (rijen[0].ong || 1) : 1;

    document.getElementById('klassen').innerHTML = rijen.map(function (g) {
      return '<div class="klas-row">' +
        '<span class="klas-top"><span class="kn">' + esc(g.naam) + '</span>' +
          '<span class="km">' + esc(g.mentor || '') + '</span></span>' +
        '<span class="klas-val">' + g.ong + ' u</span>' +
        '<span class="klas-bar" data-tip="' + esc(g.naam) + ': ' + g.ong + ' uur over ' + g.n + ' leerlingen">' +
          '<i style="width:' + (g.ong / max * 100).toFixed(1) + '%"></i></span>' +
      '</div>';
    }).join('') || '<div class="leeg">Geen registraties.</div>';
  }

  /* ── Codeverdeling ──────────────────────────────────────────────────────── */
  function tekenCodes() {
    var tel = {};
    basis().forEach(function (l) {
      (l.entries || []).forEach(function (e) { tel[e.code] = (tel[e.code] || 0) + 1; });
    });
    var rijen = Object.keys(tel).map(function (c) { return { code: c, n: tel[c] }; })
      .sort(function (a, b) { return b.n - a.n; });
    var max = rijen.length ? rijen[0].n : 1;

    document.getElementById('codes').innerHTML = rijen.map(function (r) {
      return '<div class="code-row">' +
        '<span class="cn"><b>' + esc(r.code) + '</b> ' + esc(codeNaam(r.code)) + '</span>' +
        '<span class="ct"><i style="width:' + (r.n / max * 100).toFixed(1) + '%"></i></span>' +
        '<span class="cv">' + r.n + '</span></div>';
    }).join('') || '<div class="leeg">Geen registraties.</div>';
  }

  function tekenAlles() {
    tekenActiebalk(); tekenTiles(); tekenTabs();
    tekenLijst(); tekenWeken(); tekenGroepen(); tekenCodes();
  }

  /* ── Bediening ──────────────────────────────────────────────────────────── */
  document.addEventListener('click', function (ev) {
    var tab = ev.target.closest('[data-groep]');
    if (tab) { state.groep = tab.dataset.groep; tekenAlles(); return; }

    var sig = ev.target.closest('[data-signal]');
    if (sig) {
      state.filter = state.filter === sig.dataset.signal ? null : sig.dataset.signal;
      tekenActiebalk(); tekenLijst();
    }
  });

  document.getElementById('sort').addEventListener('change', function (ev) {
    state.sort = ev.target.value;
    tekenLijst();
  });

  /* ── Tooltip ────────────────────────────────────────────────────────────── */
  var tip = document.getElementById('tip'), huidig = null;
  document.addEventListener('mousemove', function (ev) {
    var t = ev.target.closest('[data-tip]');
    if (!t) { if (huidig) { tip.classList.remove('on'); huidig = null; } return; }
    if (t !== huidig) { huidig = t; tip.textContent = t.dataset.tip; tip.classList.add('on'); }
    var r = t.getBoundingClientRect();
    tip.style.left = Math.min(window.innerWidth - 12, Math.max(12, r.left + r.width / 2)) + 'px';
    tip.style.top = (r.top - 7) + 'px';
  });

  tekenAlles();
})();
