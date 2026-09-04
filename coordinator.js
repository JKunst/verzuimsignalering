/* coordinator.js — weekbeeld voor een coördinator met een eigen lijst leerlingen.

   Andere vraag dan bij de teamleider: niet "wie springt eruit in een afdeling",
   maar "hoe ging deze week bij mijn twintig". Daarom staat de huidige week
   uitgeschreven per lesdag, met de weken ervoor als streepjes erachter. */
(function () {
  'use strict';

  var D          = window.DATA || {};
  var LEERLINGEN = D.leerlingen || [];
  var CODES      = D.codes || {};
  var WEKEN      = D.weken || [];
  var STARTS     = D.weekStarts || [];
  var HUIDIG     = WEKEN.length - 1;          // de laatste week is deze week

  var DAGNAAM = ['ma', 'di', 'wo', 'do', 'vr'];

  function codeNaam(c) { return (CODES[c] && CODES[c].naam) || c; }
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) {
      return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c];
    });
  }
  function datumVan(wi, d) {
    var start = STARTS[wi];
    if (!start) return '';
    var dt = new Date(start + 'T00:00:00');
    dt.setDate(dt.getDate() + d);
    var p = function (n) { return String(n).padStart(2, '0'); };
    return dt.getFullYear() + '-' + p(dt.getMonth() + 1) + '-' + p(dt.getDate());
  }
  function datumKort(iso) {
    if (!iso) return '';
    var d = new Date(iso + 'T00:00:00');
    if (isNaN(d)) return iso;
    var mnd = ['jan','feb','mrt','apr','mei','jun','jul','aug','sep','okt','nov','dec'];
    return d.getDate() + ' ' + mnd[d.getMonth()];
  }

  /* Registraties van één leerling, gegroepeerd op datum. */
  function perDatum(l) {
    var uit = {};
    (l.entries || []).forEach(function (e) { (uit[e.datum] = uit[e.datum] || []).push(e); });
    return uit;
  }
  function tel(entries, soort) {
    return entries.filter(function (e) { return e.soort === soort; }).length;
  }
  function vanWeek(l, wi) {
    return (l.entries || []).filter(function (e) { return e.week === wi; });
  }

  /* ── Kop met de cijfers van deze week ───────────────────────────────────── */
  function tekenKop() {
    var deze = [];
    LEERLINGEN.forEach(function (l) { deze = deze.concat(vanWeek(l, HUIDIG)); });
    var raak = LEERLINGEN.filter(function (l) { return vanWeek(l, HUIDIG).length > 0; }).length;

    var tegels = [
      { k: 'Leerlingen', v: LEERLINGEN.length, d: raak + ' met iets deze week' },
      { k: 'Ongeoorloofd', v: tel(deze, 'ong'), u: 'u', d: 'deze week' },
      { k: 'Te laat', v: tel(deze, 'laat'), d: 'deze week' },
      { k: 'Geoorloofd', v: tel(deze, 'geo'), u: 'u', d: 'ziek, arts, verlof' }
    ];
    document.getElementById('tiles').innerHTML = tegels.map(function (t) {
      return '<div class="tile"><div class="k">' + t.k + '</div>' +
        '<div class="v">' + t.v + (t.u ? '<small>' + t.u + '</small>' : '') + '</div>' +
        '<div class="d">' + t.d + '</div></div>';
    }).join('');

    var w = WEKEN[HUIDIG];
    if (w) {
      document.getElementById('weeklabel').textContent = w.label + ' · ' + w.sub;
    }
  }

  /* ── De kaarten ─────────────────────────────────────────────────────────── */
  function dagCel(l, dm, wi, d) {
    var iso = datumVan(wi, d);
    var es = (dm[iso] || []).slice().sort(function (a, b) { return (a.uur || 0) - (b.uur || 0); });
    var zwaarte = es.some(function (e) { return e.soort === 'ong'; }) ? 'ong'
                : es.some(function (e) { return e.soort === 'laat'; }) ? 'laat'
                : es.length ? 'geo' : 'niks';
    var chips = es.map(function (e) {
      return '<span class="wchip ' + e.soort + '" data-tip="' +
        esc(codeNaam(e.code) + (e.vak ? ' · ' + e.vak : '') + ' · ' + e.uurlabel) + '">' +
        esc(e.code) + '</span>';
    }).join('');
    return '<div class="wdag ' + zwaarte + '">' +
      '<span class="wdag-kop">' + DAGNAAM[d] + '</span>' +
      '<span class="wdag-body">' + (chips || '<span class="wleeg">·</span>') + '</span>' +
    '</div>';
  }

  function streepjes(l) {
    var dm = perDatum(l);
    var uit = '';
    for (var wi = 0; wi < HUIDIG; wi++) {
      var dagen = '';
      for (var d = 0; d < 5; d++) {
        var es = dm[datumVan(wi, d)] || [];
        var soort = es.some(function (e) { return e.soort === 'ong'; }) ? 'ong'
                  : es.some(function (e) { return e.soort === 'laat'; }) ? 'laat'
                  : es.length ? 'geo' : 'niks';
        var tip = es.length ? (es[0].daglabel + ' · ' + es.map(function (e) { return e.code; }).join(' ')) : '';
        dagen += '<i class="pdag ' + soort + (es.length > 2 ? ' veel' : '') + '"' +
                 (tip ? ' data-tip="' + esc(tip) + '"' : '') + '></i>';
      }
      uit += '<span class="pweek" data-tip="' + esc(WEKEN[wi].label + ' · ' + WEKEN[wi].sub) +
             '">' + dagen + '</span>';
    }
    return uit;
  }

  function logboekBlok(l) {
    var items = l.logboek || [];
    if (!D.logboekOpgehaald) return '';
    if (!items.length) return '<div class="lb-leeg">Nog geen logboek dit schooljaar</div>';
    var rijen = items.map(function (item) {
      var kop = esc(datumKort(item.datum) || item.datum) + ' · ' + esc(item.titel) +
                (item.door ? ' · ' + esc(item.door) : '');
      return '<details class="lb-item"><summary>' + kop + '</summary>' +
        (item.tekst ? '<pre class="lb-tekst">' + esc(item.tekst) + '</pre>'
                    : '<p class="ct-leeg">Tekst niet meegenomen in dit bestand.</p>') +
        '</details>';
    }).join('');
    return '<details class="logboek"><summary class="lb-kop">Logboek (' + items.length + ')' +
      (l.logboekDitJaar ? '' : ' — niets van dit schooljaar') + '</summary>' + rijen + '</details>';
  }

  function tekenKaarten() {
    /* Wie deze week het meest had, staat bovenaan. */
    var lijst = LEERLINGEN.slice().sort(function (a, b) {
      var wa = vanWeek(a, HUIDIG), wb = vanWeek(b, HUIDIG);
      var sa = tel(wa, 'ong') * 3 + tel(wa, 'laat') * 2 + tel(wa, 'geo');
      var sb = tel(wb, 'ong') * 3 + tel(wb, 'laat') * 2 + tel(wb, 'geo');
      return sb - sa || a.naam.localeCompare(b.naam, 'nl');
    });

    document.getElementById('kaarten').innerHTML = lijst.map(function (l) {
      var dm = dagenVan(l);
      var deze = vanWeek(l, HUIDIG);
      var rustig = deze.length === 0;
      var sub = l.klas + (l.mentorgroep ? ' · ' + l.mentorgroep : '') +
                (l.mentor ? ' · mentor ' + l.mentor : '');
      var cijfers = rustig
        ? '<span class="wrust">niets deze week</span>'
        : '<span class="wcijfers">' +
          (tel(deze, 'ong') ? '<b>' + tel(deze, 'ong') + ' u</b> ongeoorloofd' : '') +
          (tel(deze, 'laat') ? ' · ' + tel(deze, 'laat') + '× te laat' : '') +
          (tel(deze, 'geo') ? ' · ' + tel(deze, 'geo') + ' u geoorloofd' : '') +
          '</span>';

      var dagen = '';
      for (var d = 0; d < 5; d++) dagen += dagCel(l, dm, HUIDIG, d);

      return '<article class="kaart' + (rustig ? ' rustig' : '') + '">' +
        '<header class="kaart-kop">' +
          '<span class="wie"><span class="naam">' + esc(l.naam) + '</span>' +
            '<span class="sub">' + esc(sub) + '</span></span>' + cijfers +
        '</header>' +
        '<div class="week">' + dagen + '</div>' +
        '<div class="kaart-voet">' +
          '<span class="eerder"><span class="eerder-kop">weken ervoor</span>' + streepjes(l) + '</span>' +
          '<span class="totaal">' + l.ong + ' u ongeoorloofd · ' + l.laat + '× te laat in ' +
            WEKEN.length + ' weken</span>' +
        '</div>' +
        logboekBlok(l) +
      '</article>';
    }).join('') || '<div class="leeg">Nog geen leerlingen opgehaald.</div>';
  }

  function dagenVan(l) { return perDatum(l); }

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

  tekenKop();
  tekenKaarten();
})();
