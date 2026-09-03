/* render.js — tekent het verzuimdashboard uit window.DATA.
   De cijfers komen uit dashboard.py; hier wordt alleen opgeteld per selectie:
   de tab (afdeling/leerjaar), de codeknoppen en de signaalfilters.

   Drie dingen om te weten:
   - De codeknoppen bepalen wat je ziet. Standaard staan alleen ongeoorloofd en
     te laat aan; zet ZI aan en het ziekteverzuim komt erbij.
   - De signalen (meldplicht, nadert de grens, vaak te laat) rekenen altijd over
     álle registraties, ongeacht welke codes je toont. Dat is een norm, geen
     weergave — anders zou wegklikken van een code iemand groen maken.
   - Contactmomenten staan in localStorage van deze browser, niet op de server. */
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

  var OPSLAG_SLEUTEL = 'vzs.contacten.v1';

  function codeNaam(c) { return (CODES[c] && CODES[c].naam) || c; }
  function codeSoort(c) { return (CODES[c] && CODES[c].soort) || 'geo'; }

  /* Codes die echt in deze data voorkomen, met hun aantal. */
  var codeTelling = {};
  LEERLINGEN.forEach(function (l) {
    (l.entries || []).forEach(function (e) {
      codeTelling[e.code] = (codeTelling[e.code] || 0) + 1;
    });
  });
  var AANWEZIGE_CODES = Object.keys(codeTelling).sort(function (a, b) {
    var v = { ong: 0, laat: 1, geo: 2 };
    return (v[codeSoort(a)] - v[codeSoort(b)]) || (codeTelling[b] - codeTelling[a]);
  });

  function standaardSelectie() {
    var uit = {};
    AANWEZIGE_CODES.forEach(function (c) {
      if (codeSoort(c) !== 'geo') uit[c] = true;   // geoorloofd staat uit tot je het aanzet
    });
    return uit;
  }

  var state = {
    groep: 'Alle',
    filter: null,
    sort: 'ong',
    codes: standaardSelectie()
  };

  function aan(code) { return !!state.codes[code]; }
  function zichtbaar(l) {
    return (l.entries || []).filter(function (e) { return aan(e.code); });
  }
  function tel(entries, soort) {
    return entries.filter(function (e) { return e.soort === soort; }).length;
  }

  /* Status volgt de norm, dus altijd op álle ongeoorloofde uren. */
  function status(l) {
    if (l.ong >= NORM_CRIT) return 'crit';
    if (l.ong >= NORM_WARN) return 'warn';
    return 'neut';
  }

  function inGroep(l) { return state.groep === 'Alle' || l.groep === state.groep; }
  function basis() { return LEERLINGEN.filter(inGroep); }

  function lijstLeerlingen() {
    var lijst = basis().filter(function (l) { return zichtbaar(l).length > 0; });
    if (state.filter === 'crit') lijst = lijst.filter(function (l) { return status(l) === 'crit'; });
    if (state.filter === 'warn') lijst = lijst.filter(function (l) { return status(l) === 'warn'; });
    if (state.filter === 'laat') lijst = lijst.filter(function (l) { return l.laat >= NORM_LAAT; });
    if (state.filter === 'ct') lijst = lijst.filter(function (l) { return contacten(l.id).length > 0; });

    var s = state.sort;
    return lijst.slice().sort(function (a, b) {
      if (s === 'naam')    return a.naam.localeCompare(b.naam, 'nl');
      if (s === 'laat')    return b.laat - a.laat || b.ong - a.ong;
      if (s === 'ziek')    return b.ziek - a.ziek || b.ong - a.ong;
      if (s === 'getoond') return zichtbaar(b).length - zichtbaar(a).length;
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
    late: '<svg class="ico" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="8" cy="8" r="6"/><path d="M8 4.6V8.2l2.4 1.5"/></svg>',
    bel:  '<svg class="ico" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3.2 2.8h2.4l1.1 2.7-1.4 1a7.6 7.6 0 0 0 3.2 3.2l1-1.4 2.7 1.1v2.4a1 1 0 0 1-1.1 1A11 11 0 0 1 2.2 3.9a1 1 0 0 1 1-1.1z"/></svg>'
  };

  /* ── Contactmomenten (alleen in deze browser) ───────────────────────────── */
  function alleContacten() {
    try {
      return JSON.parse(localStorage.getItem(OPSLAG_SLEUTEL) || '{}') || {};
    } catch (e) { return {}; }
  }
  function bewaarContacten(alles) {
    try {
      localStorage.setItem(OPSLAG_SLEUTEL, JSON.stringify(alles));
      return true;
    } catch (e) { return false; }
  }
  function contacten(id) {
    var lijst = alleContacten()[id];
    return Array.isArray(lijst) ? lijst : [];
  }
  function voegContactToe(id, contact) {
    var alles = alleContacten();
    (alles[id] = alles[id] || []).push(contact);
    alles[id].sort(function (a, b) { return (b.datum || '').localeCompare(a.datum || ''); });
    return bewaarContacten(alles);
  }
  function verwijderContact(id, sleutel) {
    var alles = alleContacten();
    alles[id] = (alles[id] || []).filter(function (c) { return String(c.gemaakt) !== String(sleutel); });
    if (!alles[id].length) delete alles[id];
    return bewaarContacten(alles);
  }
  function aantalContacten() {
    var alles = alleContacten(), n = 0;
    Object.keys(alles).forEach(function (k) { n += (alles[k] || []).length; });
    return n;
  }

  var SOORTEN = ['telefoon ouders', 'gesprek leerling', 'mail', 'mentor ingelicht',
                 'leerplicht gemeld', 'anders'];

  function datumKort(iso) {
    if (!iso) return '';
    var d = new Date(iso + 'T00:00:00');
    if (isNaN(d)) return iso;
    var mnd = ['jan','feb','mrt','apr','mei','jun','jul','aug','sep','okt','nov','dec'];
    return d.getDate() + ' ' + mnd[d.getMonth()];
  }
  function vandaag() {
    var d = new Date(), p = function (n) { return String(n).padStart(2, '0'); };
    return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate());
  }

  function contactBlok(l) {
    var lijst = contacten(l.id);
    var rijen = lijst.map(function (c) {
      return '<div class="ct-rij">' +
        '<span class="ct-datum">' + esc(datumKort(c.datum)) + '</span>' +
        '<span class="ct-soort">' + esc(c.soort || '') + '</span>' +
        '<span class="ct-notitie">' + esc(c.notitie || '') + '</span>' +
        '<button class="ct-weg" data-weg="' + esc(l.id) + '|' + esc(c.gemaakt) +
        '" title="Verwijderen" aria-label="Verwijderen">×</button>' +
      '</div>';
    }).join('') || '<div class="ct-leeg">Nog geen contact vastgelegd.</div>';

    var opties = SOORTEN.map(function (s) {
      return '<option value="' + esc(s) + '">' + esc(s) + '</option>';
    }).join('');

    return '<div class="contact" data-id="' + esc(l.id) + '">' +
      '<div class="ct-kop">Contact</div>' +
      '<div class="ct-lijst">' + rijen + '</div>' +
      '<div class="ct-form">' +
        '<input type="date" class="ct-in-datum" value="' + vandaag() + '" aria-label="Datum">' +
        '<select class="ct-in-soort" aria-label="Soort contact">' + opties + '</select>' +
        '<input type="text" class="ct-in-notitie" placeholder="Notitie (optioneel)" aria-label="Notitie">' +
        '<button class="ct-opslaan" data-opslaan="' + esc(l.id) + '">Vastleggen</button>' +
      '</div>' +
    '</div>';
  }

  /* ── Logboek uit Magister ───────────────────────────────────────────────── */
  function logboekBlok(l) {
    var items = l.logboek || [];
    var geen = '<div class="lb-leeg">Nog geen logboek dit schooljaar</div>';
    if (!D.logboekOpgehaald) return '';
    if (!items.length) return geen;
    var rijen = items.map(function (item) {
      var kop = esc(datumKort(item.datum) || item.datum) + ' · ' + esc(item.titel) +
                (item.door ? ' · ' + esc(item.door) : '');
      return '<details class="lb-item"><summary>' + kop + '</summary>' +
        (item.tekst ? '<pre class="lb-tekst">' + esc(item.tekst) + '</pre>'
                    : '<p class="ct-leeg">Tekst niet meegenomen in dit bestand.</p>') +
        '</details>';
    }).join('');
    return '<details class="logboek"><summary class="lb-kop">Logboek (' + items.length + ')' +
      (l.logboekDitJaar ? '' : ' — niets van dit schooljaar') + '</summary>' +
      (l.logboekDitJaar ? '' : geen) + rijen + '</details>';
  }

  /* ── Codeknoppen ────────────────────────────────────────────────────────── */
  function tekenCodebalk() {
    var el = document.getElementById('codebalk');
    if (!el) return;
    if (!AANWEZIGE_CODES.length) { el.innerHTML = ''; return; }

    var knoppen = AANWEZIGE_CODES.map(function (c) {
      var soort = codeSoort(c);
      return '<button class="cbtn ' + soort + (aan(c) ? ' aan' : '') + '" data-code="' + esc(c) + '" ' +
        'aria-pressed="' + aan(c) + '" data-tip="' + esc(codeNaam(c)) + '" ' +
        'title="' + esc(codeNaam(c)) + '">' +
        '<b>' + esc(c) + '</b>' +
        '<span class="cbtn-n">' + codeTelling[c] + '</span></button>';
    }).join('');

    var presets = [
      { k: 'alles', t: 'alles' },
      { k: 'ong',   t: 'ongeoorloofd' },
      { k: 'geo',   t: 'geoorloofd' }
    ].map(function (p) {
      return '<button class="cpreset" data-preset="' + p.k + '">' + p.t + '</button>';
    }).join('');

    el.innerHTML = '<span class="cbalk-kop">Toon</span>' + knoppen +
                   '<span class="cbalk-presets">' + presets + '</span>';
  }

  /* ── Actiebalk (normen — niet beïnvloed door de codeknoppen) ─────────────── */
  function tekenActiebalk() {
    var b = basis();
    var nCrit = b.filter(function (l) { return status(l) === 'crit'; }).length;
    var nWarn = b.filter(function (l) { return status(l) === 'warn'; }).length;
    var nLaat = b.filter(function (l) { return l.laat >= NORM_LAAT; }).length;
    var nContact = b.filter(function (l) { return contacten(l.id).length > 0; }).length;

    var defs = [
      { key: 'crit', cls: 'crit', ico: ICO.crit, n: nCrit, t: 'Meldplicht bereikt',
        s: NORM_CRIT + ' uur of meer ongeoorloofd' },
      { key: 'warn', cls: 'warn', ico: ICO.warn, n: nWarn, t: 'Nadert de grens',
        s: NORM_WARN + ' t/m ' + (NORM_CRIT - 1) + ' uur ongeoorloofd' },
      { key: 'laat', cls: 'late', ico: ICO.late, n: nLaat, t: 'Vaak te laat',
        s: NORM_LAAT + ' keer of vaker deze periode' },
      { key: 'ct', cls: 'ct', ico: ICO.bel, n: nContact, t: 'Contact gelegd',
        s: 'door jou vastgelegd in deze browser' }
    ];

    document.getElementById('actiebalk').innerHTML = defs.map(function (d) {
      return '<button class="signal ' + d.cls + '" data-signal="' + d.key + '" ' +
        'aria-pressed="' + (state.filter === d.key) + '">' + d.ico +
        '<span class="n">' + d.n + '</span>' +
        '<span class="lbl"><b>' + d.t + '</b>' + d.s + '</span></button>';
    }).join('');
  }

  /* ── Kerncijfers (volgen de codeknoppen) ────────────────────────────────── */
  function tekenTiles() {
    var b = basis();
    var alleZichtbaar = [];
    b.forEach(function (l) { alleZichtbaar = alleZichtbaar.concat(zichtbaar(l)); });

    var ong  = tel(alleZichtbaar, 'ong');
    var laat = tel(alleZichtbaar, 'laat');
    var geo  = tel(alleZichtbaar, 'geo');
    var ziek = alleZichtbaar.filter(function (e) { return e.code === 'ZI'; }).length;
    var raak = b.filter(function (l) { return zichtbaar(l).length > 0; }).length;
    var gem  = b.length ? (ong / b.length).toFixed(1).replace('.', ',') : '0,0';

    var tiles = [
      { k: 'Leerlingen', v: b.length, d: raak + ' met een getoonde registratie' },
      { k: 'Ongeoorloofde uren', v: ong, u: 'u', d: gem + ' uur per leerling gemiddeld' },
      { k: 'Keer te laat', v: laat,
        d: b.filter(function (l) { return l.laat >= NORM_LAAT; }).length +
           ' leerlingen ' + NORM_LAAT + '× of vaker' },
      { k: 'Geoorloofde uren', v: geo, u: 'u',
        d: ziek ? ziek + ' daarvan ziek' : 'telt niet mee in de norm' }
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
    var lijst = lijstLeerlingen();
    var el = document.getElementById('lijst');
    document.getElementById('lijst-telling').textContent =
      lijst.length + ' van ' + basis().length + ' leerlingen';

    if (!lijst.length) {
      el.innerHTML = '<div class="leeg">Geen leerlingen die aan dit filter voldoen. ' +
        'Staan de juiste codes aan?</div>';
      return;
    }

    el.innerHTML = lijst.map(function (l, i) {
      var st = status(l);
      var pct = Math.min(100, l.ong / NORM_CRIT * 100);
      var label = st === 'crit' ? 'Meldplicht'
                : st === 'warn' ? 'Nadert grens'
                : l.ong === 0 ? 'Alleen geoorloofd of te laat' : 'In beeld';
      var ico = st === 'crit' ? ICO.crit : st === 'warn' ? ICO.warn
              : l.ong === 0 ? ICO.late : '';

      var zicht = zichtbaar(l);
      var perDag = {}, volgorde = [];
      zicht.forEach(function (e) {
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

      var ct = contacten(l.id);
      var ctBadge = ct.length
        ? '<span class="ct-badge" data-tip="Laatste contact: ' + esc(ct[0].soort || '') + '">' +
          ICO.bel + esc(datumKort(ct[0].datum)) + '</span>'
        : '';

      var sub = l.klas
        + (l.mentorgroep ? ' · ' + l.mentorgroep : '')
        + (l.mentor ? ' · mentor ' + l.mentor : '');

      var telUit = zicht.length + ' van ' + (l.entries || []).length + ' registraties getoond';

      return '<details class="rij"' + (i === 0 ? ' open' : '') + '>' +
        '<summary class="rij-hd">' +
          '<span class="stripe ' + st + '"></span>' +
          '<span class="wie"><span class="naam">' + esc(l.naam) + ctBadge + '</span>' +
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
        '<div class="detail">' +
          contactBlok(l) +
          logboekBlok(l) +
          '<div class="detail-telling">' + telUit + '</div>' +
          (dagen || '<p class="leeg">Geen registraties in deze selectie.</p>') +
        '</div>' +
      '</details>';
    }).join('');
  }

  /* ── Weektrend ──────────────────────────────────────────────────────────── */
  function tekenWeken() {
    var perWeek = WEKEN.map(function () { return { ong: 0, laat: 0, geo: 0 }; });
    basis().forEach(function (l) {
      zichtbaar(l).forEach(function (e) {
        var w = perWeek[e.week];
        if (w && w[e.soort] !== undefined) w[e.soort]++;
      });
    });
    var max = Math.max.apply(null, perWeek.map(function (w) {
      return w.ong + w.laat + w.geo;
    })) || 1;

    var segment = function (n, kleur, naam) {
      return n ? '<span class="seg" style="flex:' + n + ';background:' + kleur + '" ' +
                 'data-tip="' + naam + ': ' + n + ' uur"></span>' : '';
    };

    document.getElementById('weken').innerHTML = perWeek.map(function (w, i) {
      var tot = w.ong + w.laat + w.geo;
      return '<div class="bar-row">' +
        '<span class="bar-lbl"><b>' + esc(WEKEN[i].label) + '</b><br>' + esc(WEKEN[i].sub) + '</span>' +
        '<span class="bar-track">' +
          '<span class="bar-stack" style="max-width:' + (tot / max * 100).toFixed(1) + '%">' +
            segment(w.ong, 'var(--s-ongeoorloofd)', 'Ongeoorloofd') +
            segment(w.laat, 'var(--s-telaat)', 'Te laat') +
            segment(w.geo, 'var(--s-geoorloofd)', 'Geoorloofd') +
          '</span>' +
          '<span class="bar-val">' + tot + '</span>' +
        '</span></div>';
    }).join('');
  }

  /* ── Per mentorgroep ────────────────────────────────────────────────────── */
  function tekenGroepen() {
    var perGroep = {};
    basis().forEach(function (l) {
      var sleutel = l.mentorgroep || l.klas;
      var g = perGroep[sleutel] ||
        (perGroep[sleutel] = { naam: sleutel, mentor: l.mentor, n: 0, uren: 0 });
      g.uren += zichtbaar(l).length;
      g.n++;
      if (!g.mentor && l.mentor) g.mentor = l.mentor;
    });
    var rijen = Object.keys(perGroep).map(function (k) { return perGroep[k]; })
      .sort(function (a, b) { return b.uren - a.uren; }).slice(0, 10);
    var max = rijen.length ? (rijen[0].uren || 1) : 1;

    document.getElementById('klassen').innerHTML = rijen.map(function (g) {
      return '<div class="klas-row">' +
        '<span class="klas-top"><span class="kn">' + esc(g.naam) + '</span>' +
          '<span class="km">' + esc(g.mentor || '') + '</span></span>' +
        '<span class="klas-val">' + g.uren + ' u</span>' +
        '<span class="klas-bar" data-tip="' + esc(g.naam) + ': ' + g.uren + ' uur over ' + g.n + ' leerlingen">' +
          '<i style="width:' + (g.uren / max * 100).toFixed(1) + '%"></i></span>' +
      '</div>';
    }).join('') || '<div class="leeg">Geen registraties in deze selectie.</div>';
  }

  /* ── Codeverdeling (altijd alle codes, als overzicht) ───────────────────── */
  function tekenCodes() {
    var telling = {};
    basis().forEach(function (l) {
      (l.entries || []).forEach(function (e) { telling[e.code] = (telling[e.code] || 0) + 1; });
    });
    var rijen = Object.keys(telling).map(function (c) { return { code: c, n: telling[c] }; })
      .sort(function (a, b) { return b.n - a.n; });
    var max = rijen.length ? rijen[0].n : 1;

    document.getElementById('codes').innerHTML = rijen.map(function (r) {
      return '<div class="code-row' + (aan(r.code) ? '' : ' uit') + '">' +
        '<span class="cn"><b>' + esc(r.code) + '</b> ' + esc(codeNaam(r.code)) + '</span>' +
        '<span class="ct"><i style="width:' + (r.n / max * 100).toFixed(1) + '%"></i></span>' +
        '<span class="cv">' + r.n + '</span></div>';
    }).join('') || '<div class="leeg">Geen registraties.</div>';
  }

  /* ── Contactenoverzicht boven de lijst ──────────────────────────────────── */
  function tekenContactknop() {
    var el = document.getElementById('contact-export');
    if (!el) return;
    var n = aantalContacten();
    el.innerHTML = n
      ? '<button id="ct-toon" class="ct-export">' +
        n + (n === 1 ? ' contactmoment' : ' contactmomenten') + ' vastgelegd — bekijken</button>'
      : '<span class="ct-leeg">Nog geen contactmomenten vastgelegd</span>';
  }

  function exportTekst() {
    var alles = alleContacten();
    var naamVan = {};
    LEERLINGEN.forEach(function (l) { naamVan[l.id] = l.naam + ' (' + l.klas + ')'; });
    var uit = [];
    Object.keys(alles).forEach(function (id) {
      (alles[id] || []).forEach(function (c) {
        uit.push({
          leerling: naamVan[id] || ('id ' + id),
          leerling_id: id,
          datum: c.datum, soort: c.soort, notitie: c.notitie
        });
      });
    });
    uit.sort(function (a, b) { return (b.datum || '').localeCompare(a.datum || ''); });
    return JSON.stringify(uit, null, 1);
  }

  function toonExport() {
    var tekst = exportTekst();
    var vak = document.getElementById('ct-export-vak');
    vak.innerHTML =
      '<p class="ct-uitleg">Deze contactmomenten staan alleen in deze browser. ' +
      'Bewaar ze zelf als je ze wilt houden — bij een andere computer of een ' +
      'geleegde browser zijn ze weg.</p>' +
      '<textarea class="ct-json" readonly rows="8"></textarea>' +
      '<div class="ct-knoppen"><button id="ct-dl">Download als JSON</button>' +
      '<button id="ct-dicht">Sluiten</button></div>';
    vak.querySelector('.ct-json').value = tekst;
    vak.hidden = false;
    vak.querySelector('.ct-json').select();

    document.getElementById('ct-dl').addEventListener('click', function () {
      var blob = new Blob([tekst], { type: 'application/json' });
      var url = URL.createObjectURL(blob);
      var a = document.createElement('a');
      a.href = url;
      a.download = 'contactmomenten_' + vandaag() + '.json';
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(url);
    });
    document.getElementById('ct-dicht').addEventListener('click', function () {
      vak.hidden = true;
    });
  }

  function tekenAlles() {
    tekenCodebalk(); tekenActiebalk(); tekenTiles(); tekenTabs();
    tekenLijst(); tekenWeken(); tekenGroepen(); tekenCodes(); tekenContactknop();
  }

  /* ── Bediening ──────────────────────────────────────────────────────────── */
  document.addEventListener('click', function (ev) {
    var tab = ev.target.closest('[data-groep]');
    if (tab) { state.groep = tab.dataset.groep; tekenAlles(); return; }

    var code = ev.target.closest('[data-code]');
    if (code) {
      var c = code.dataset.code;
      if (aan(c)) delete state.codes[c]; else state.codes[c] = true;
      tekenAlles();
      return;
    }

    var preset = ev.target.closest('[data-preset]');
    if (preset) {
      var welke = preset.dataset.preset;
      state.codes = {};
      AANWEZIGE_CODES.forEach(function (c) {
        var s = codeSoort(c);
        if (welke === 'alles' ||
            (welke === 'ong' && s !== 'geo') ||
            (welke === 'geo' && s === 'geo')) state.codes[c] = true;
      });
      tekenAlles();
      return;
    }

    var sig = ev.target.closest('[data-signal]');
    if (sig) {
      state.filter = state.filter === sig.dataset.signal ? null : sig.dataset.signal;
      tekenActiebalk(); tekenLijst();
      return;
    }

    var opslaan = ev.target.closest('[data-opslaan]');
    if (opslaan) {
      var blok = opslaan.closest('.contact');
      var gelukt = voegContactToe(opslaan.dataset.opslaan, {
        datum:   blok.querySelector('.ct-in-datum').value || vandaag(),
        soort:   blok.querySelector('.ct-in-soort').value,
        notitie: blok.querySelector('.ct-in-notitie').value.trim(),
        gemaakt: Date.now()
      });
      if (!gelukt) {
        alert('Opslaan lukte niet. Staat opslag van websitegegevens uit in deze browser?');
        return;
      }
      tekenActiebalk(); tekenLijst(); tekenContactknop();
      return;
    }

    var weg = ev.target.closest('[data-weg]');
    if (weg) {
      var delen = weg.dataset.weg.split('|');
      verwijderContact(delen[0], delen[1]);
      tekenActiebalk(); tekenLijst(); tekenContactknop();
      return;
    }

    if (ev.target.closest('#ct-toon')) { toonExport(); return; }
  });

  document.getElementById('sort').addEventListener('change', function (ev) {
    state.sort = ev.target.value;
    tekenLijst();
  });

  /* Details openhouden terwijl je typt: klik in het formulier niet doorgeven. */
  document.addEventListener('click', function (ev) {
    if (ev.target.closest('.contact') && ev.target.closest('summary')) ev.stopPropagation();
  }, true);

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
