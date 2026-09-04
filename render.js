/* render.js — tekent het verzuimdashboard uit window.DATA.
   De cijfers komen uit dashboard.py; hier wordt alleen opgeteld per selectie:
   de tab (afdeling/leerjaar), de codeknoppen en de signaalfilters.

   De pagina is een werklijst, geen verantwoording: wie moet ik spreken, waarover,
   en wat is er al gedaan.

   - De signalen zijn gespreksredenen (loopt op, nog geen contact, eerste uur,
     één vak, opgeknapt). Ze rekenen over ongeoorloofd verzuim en te laat komen,
     ongeacht welke codes je toont — anders zou wegklikken van een code iemand
     uit beeld halen.
   - De codeknoppen bepalen wél wat je aan registraties ziet: tegels, grafieken
     en de dagregels. Geoorloofd staat standaard uit.
   - De meldgrens blijft bestaan, maar als klein label; het is een wettelijk
     feit, geen stuurmiddel.
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
    sort: 'urgentie',
    codes: standaardSelectie()
  };

  function aan(code) { return !!state.codes[code]; }
  function zichtbaar(l) {
    return (l.entries || []).filter(function (e) { return aan(e.code); });
  }
  function tel(entries, soort) {
    return entries.filter(function (e) { return e.soort === soort; }).length;
  }

  /* ── Gespreksredenen ────────────────────────────────────────────────────
     Berekend over ongeoorloofd verzuim en te laat komen; die maken het gesprek.
     Ziek en verlof blijven context. */
  var REDENEN = [
    { key: 'oploop',  label: 'Loopt op',        uitleg: 'meer dan in de weken ervoor' },
    { key: 'geencontact', label: 'Nog geen contact', uitleg: 'verzuim, niets vastgelegd' },
    { key: 'telaat',  label: 'Vaak te laat',    uitleg: NORM_LAAT + '× of vaker' },
    { key: 'eersteuur', label: 'Eerste uur',    uitleg: 'valt vooral vroeg uit' },
    { key: 'eenvak',  label: 'Eén vak',         uitleg: 'zit bij één docent' },
    { key: 'opgeknapt', label: 'Opgeknapt',     uitleg: 'minder dan ervoor' }
  ];

  var _cache = {};
  function feiten(l) {
    if (_cache[l.id]) return _cache[l.id];
    var acties = (l.entries || []).filter(function (e) {
      return e.soort === 'ong' || e.soort === 'laat';
    });
    var n = Math.max(1, WEKEN.length);
    var perWeek = [];
    for (var w = 0; w < n; w++) perWeek.push(0);
    acties.forEach(function (e) { if (perWeek[e.week] !== undefined) perWeek[e.week]++; });

    var helft  = Math.max(1, Math.round(n / 2));
    var recent = perWeek.slice(n - helft).reduce(function (a, b) { return a + b; }, 0);
    var eerder = perWeek.slice(0, n - helft).reduce(function (a, b) { return a + b; }, 0);
    var recentGem = recent / helft;
    var eerderGem = eerder / Math.max(1, n - helft);

    var vroeg = acties.filter(function (e) { return e.uur === 1 || e.uur === 2; }).length;
    var perVak = {}, topVak = '', topVakN = 0;
    acties.forEach(function (e) {
      if (!e.vak) return;
      perVak[e.vak] = (perVak[e.vak] || 0) + 1;
      if (perVak[e.vak] > topVakN) { topVakN = perVak[e.vak]; topVak = e.vak; }
    });

    var f = {
      acties: acties.length,
      recent: recent,
      topVak: topVak,
      oploop:      recent >= 4 && recentGem >= eerderGem * 1.75,
      opgeknapt:   eerder >= 4 && recentGem < eerderGem * 0.5,
      telaat:      l.laat >= NORM_LAAT,
      eersteuur:   acties.length >= 3 && vroeg >= acties.length * 0.5,
      eenvak:      topVakN >= 3 && topVakN >= acties.length * 0.5,
      geencontact: acties.length > 0 && contacten(l.id).length === 0,
      melden:      l.ong >= NORM_CRIT
    };
    f.lijst = REDENEN.filter(function (r) { return f[r.key]; });
    /* Volgorde van de werklijst: wat vraagt het eerst om een gesprek. */
    f.urgentie = (f.oploop ? 40 : 0) + (f.geencontact ? 25 : 0) + (f.telaat ? 15 : 0)
               + (f.eersteuur ? 8 : 0) + (f.eenvak ? 8 : 0) + (f.melden ? 20 : 0)
               + Math.min(recent, 20);
    _cache[l.id] = f;
    return f;
  }

  function wisCache() { _cache = {}; }

  function inGroep(l) { return state.groep === 'Alle' || l.groep === state.groep; }
  function basis() { return LEERLINGEN.filter(inGroep); }

  function lijstLeerlingen() {
    var lijst = basis().filter(function (l) { return zichtbaar(l).length > 0; });
    if (state.filter) {
      lijst = lijst.filter(function (l) { return feiten(l)[state.filter]; });
    }
    var s = state.sort;
    return lijst.slice().sort(function (a, b) {
      if (s === 'naam')    return a.naam.localeCompare(b.naam, 'nl');
      if (s === 'laat')    return b.laat - a.laat || b.ong - a.ong;
      if (s === 'ong')     return b.ong - a.ong || b.laat - a.laat;
      if (s === 'getoond') return zichtbaar(b).length - zichtbaar(a).length;
      return feiten(b).urgentie - feiten(a).urgentie || b.ong - a.ong;
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
  /* Datum van dag d (0=maandag) in week wi, afgeleid van de weeklabels. */
  var _weekStart = (D.weekStarts || []);
  function datumVan(wi, d) {
    var start = _weekStart[wi];
    if (!start) return '';
    var dt = new Date(start + 'T00:00:00');
    dt.setDate(dt.getDate() + d);
    var p = function (n) { return String(n).padStart(2, '0'); };
    return dt.getFullYear() + '-' + p(dt.getMonth() + 1) + '-' + p(dt.getDate());
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
        'aria-pressed="' + aan(c) + '" data-tip="' + esc(codeNaam(c)) +
        (aan(c) ? ' — klik om te verbergen' : ' — klik om te tonen') + '" ' +
        'title="' + esc(codeNaam(c)) + '">' +
        '<span class="cvink" aria-hidden="true"></span>' +
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

  /* ── Actiebalk: redenen voor een gesprek ────────────────────────────────── */
  function tekenActiebalk() {
    var b = basis().filter(function (l) { return zichtbaar(l).length > 0; });
    var knoppen = REDENEN.map(function (r) {
      var n = b.filter(function (l) { return feiten(l)[r.key]; }).length;
      return '<button class="signal ' + r.key + '" data-signal="' + r.key + '" ' +
        'data-tip="' + esc(r.uitleg) + '" aria-pressed="' + (state.filter === r.key) + '">' +
        '<span class="punt" aria-hidden="true"></span>' +
        '<span class="n">' + n + '</span>' + esc(r.label) + '</button>';
    }).join('');
    document.getElementById('actiebalk').innerHTML =
      '<span class="sbalk-kop">Bespreken</span>' + knoppen +
      (state.filter ? '<button class="sreset" data-signal="' + state.filter +
                      '">toon alles</button>' : '');
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
      var f = feiten(l);
      var zicht = zichtbaar(l);

      /* Patroonstrook: per week vijf lesdagen, gekleurd naar het zwaarste
         wat er die dag speelde. Zo zie je 'elke maandag' of 'één ziekweek'. */
      var perDatum = {};
      zicht.forEach(function (e) { (perDatum[e.datum] = perDatum[e.datum] || []).push(e); });
      var weken = WEKEN.map(function (w, wi) {
        var dagen = '';
        for (var d = 0; d < 5; d++) {
          var iso = datumVan(wi, d);
          var es = perDatum[iso] || [];
          var soort = es.some(function (e) { return e.soort === 'ong'; }) ? 'ong'
                    : es.some(function (e) { return e.soort === 'laat'; }) ? 'laat'
                    : es.length ? 'geo' : 'niks';
          var tip = es.length
            ? (es[0].daglabel + ' · ' + es.map(function (e) { return e.code; }).join(' '))
            : '';
          dagen += '<i class="pdag ' + soort + (es.length > 2 ? ' veel' : '') + '"' +
                   (tip ? ' data-tip="' + esc(tip) + '"' : '') + '></i>';
        }
        return '<span class="pweek" data-tip="' + esc(w.label + ' · ' + w.sub) + '">' + dagen + '</span>';
      }).join('');

      var ct = contacten(l.id);
      var ctTekst = ct.length
        ? '<span class="ct-status heeft">' + ICO.bel + esc(datumKort(ct[0].datum)) +
          ' · ' + esc(ct[0].soort || '') + '</span>'
        : '<span class="ct-status geen">nog geen contact</span>';

      var tags = f.lijst.filter(function (r) { return r.key !== 'geencontact'; })
                        .slice(0, 2).map(function (r) {
        return '<span class="rtag ' + r.key + '">' + r.label + '</span>';
      }).join('');
      if (f.melden) tags += '<span class="rtag melden" data-tip="' + NORM_CRIT +
                            ' uur of meer ongeoorloofd">melden</span>';

      var dagen = Object.keys(perDatum).sort().reverse().map(function (dt) {
        var es = perDatum[dt].slice().sort(function (a, b) { return (a.uur || 0) - (b.uur || 0); });
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
          '<span class="stripe' + (f.oploop ? ' oploop' : f.geencontact ? ' geencontact' : '') + '"></span>' +
          '<span class="wie"><span class="naam">' + esc(l.naam) + '</span>' +
            '<span class="sub">' + esc(sub) + '</span></span>' +
          '<span class="patroon">' + weken +
            '<span class="pcijfer"><b>' + l.ong + ' u</b> ongeoorloofd · ' +
              l.laat + '× te laat</span>' +
          '</span>' +
          '<span class="rij-eind">' +
            '<span class="rij-stapel"><span class="redenen">' + tags + '</span>' +
              ctTekst + '</span>' +
            '<svg class="chev" width="11" height="11" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6 3l5 5-5 5"/></svg>' +
          '</span>' +
        '</summary>' +
        '<div class="detail">' +
          contactBlok(l) +
          logboekBlok(l) +
          '<div class="detail-telling">' + zicht.length + ' van ' +
            (l.entries || []).length + ' registraties getoond' +
            (f.topVak && f.eenvak ? ' · vooral bij ' + esc(f.topVak) : '') + '</div>' +
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

  /* ── Uitval per lesuur ──────────────────────────────────────────────────
     Wanneer op de dag gaat het mis? Dat stuurt de interventie meer dan een
     verdeling over codes. */
  function tekenUren() {
    var perUur = {}, maxUur = 8;
    basis().forEach(function (l) {
      zichtbaar(l).forEach(function (e) {
        var u = e.uur || 0;
        if (u > maxUur) maxUur = u;
        perUur[u] = perUur[u] || { ong: 0, laat: 0, geo: 0 };
        perUur[u][e.soort]++;
      });
    });
    var uren = [];
    for (var u = 1; u <= maxUur; u++) uren.push(u);
    if (perUur[0]) uren.push(0);                       // lesuur onbekend
    var max = 1;
    uren.forEach(function (u) {
      var w = perUur[u]; if (w) max = Math.max(max, w.ong + w.laat + w.geo);
    });

    var segment = function (n, kleur, naam) {
      return n ? '<span class="seg" style="flex:' + n + ';background:' + kleur + '" ' +
                 'data-tip="' + naam + ': ' + n + '"></span>' : '';
    };
    document.getElementById('uren').innerHTML = uren.map(function (u) {
      var w = perUur[u] || { ong: 0, laat: 0, geo: 0 };
      var tot = w.ong + w.laat + w.geo;
      return '<div class="bar-row">' +
        '<span class="bar-lbl"><b>' + (u ? u + 'e uur' : 'onbekend') + '</b></span>' +
        '<span class="bar-track">' +
          '<span class="bar-stack" style="max-width:' + (tot / max * 100).toFixed(1) + '%">' +
            segment(w.ong, 'var(--s-ongeoorloofd)', 'Ongeoorloofd') +
            segment(w.laat, 'var(--s-telaat)', 'Te laat') +
            segment(w.geo, 'var(--s-geoorloofd)', 'Geoorloofd') +
          '</span>' +
          '<span class="bar-val">' + tot + '</span>' +
        '</span></div>';
    }).join('') || '<div class="leeg">Geen registraties in deze selectie.</div>';
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
    tekenLijst(); tekenWeken(); tekenGroepen(); tekenUren(); tekenContactknop();
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
      wisCache(); tekenActiebalk(); tekenLijst(); tekenContactknop();
      return;
    }

    var weg = ev.target.closest('[data-weg]');
    if (weg) {
      var delen = weg.dataset.weg.split('|');
      verwijderContact(delen[0], delen[1]);
      wisCache(); tekenActiebalk(); tekenLijst(); tekenContactknop();
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
