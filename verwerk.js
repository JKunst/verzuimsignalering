/* verwerk.js — rekent een Magister-payload om tot het verzuimdashboard.

   Draait in het rapportvenster (rapport.html), in de browser van de gebruiker.
   Het verzuim komt daardoor nooit op de server: de bladwijzer haalt het op in
   het Magister-tabblad en geeft het met postMessage door aan dit venster.

   De payload ziet er zo uit:

     {
       "period":   {"begin": "2026-09-01", "einde": "2026-09-26"},
       "scope":    "H4,H5",
       "students": [{"id": 1, "roepnaam": ..., "achternaam": ...,
                     "klassen": ["H4A"], "studies": ["H4"], "lesgroepen": [...]}],
       "entries":  {"1": [{"date": "2026-09-03", "time": "08:30", "code": "A",
                           "period": 2, "subject": "Nederlands",
                           "naam": "...", "type": "...", "geoorloofd": false}]},
       "logboek":  {"1": [{"aangemaaktOp": ..., "omschrijving": ..., "inhoud": ...}]}
     }

   Alles wat geteld wordt gebeurt hier; render.js en coordinator.js tekenen
   alleen. Zo geven het venster en het gedownloade HTML-bestand dezelfde cijfers. */
(function (root) {
  'use strict';

  var NL_DAG   = ['ma', 'di', 'wo', 'do', 'vr', 'za', 'zo'];
  var NL_MAAND = ['', 'jan', 'feb', 'mrt', 'apr', 'mei', 'jun',
                  'jul', 'aug', 'sep', 'okt', 'nov', 'dec'];

  var AFDELING_NAAM = { H: 'Havo', M: 'Mavo', V: 'Vwo', A: 'Atheneum', G: 'Gymnasium' };

  // Waaraan je de mentorgroep herkent in de lesgroepnamen: h4mtu1 … h4mtu8.
  var MENTORGROEP_PATROON = 'mtu';

  var STANDAARD_CONFIG = {
    normCrit: 16,   // uren ongeoorloofd → het label 'melden' (leerplicht)
    normLaat: 6     // keer te laat → het signaal 'vaak te laat'
  };

  var LOGBOEK_MAX = 3;          // meer dan drie is in dit overzicht niet nuttig

  function heeft(o, k) { return Object.prototype.hasOwnProperty.call(o, k); }
  function cmp(a, b) { return a < b ? -1 : a > b ? 1 : 0; }

  // ── Codes ─────────────────────────────────────────────────────────────────
  // Magister levert per registratie mee wat de code betekent, van welk type hij
  // is en of hij geoorloofd is. Dat is betrouwbaarder dan een lijst die wij
  // bijhouden: 'TA' bleek bij ons "Teamleider afgehandeld" te betekenen.
  var TYPE_NAAR_SOORT = {
    telaat: 'laat',
    huiswerkvergeten: 'vergeten',
    materiaalvergeten: 'vergeten'
  };

  /* ong | laat | vergeten | geo, bij voorkeur op wat Magister zelf zegt. */
  function soortVanRegistratie(e, codes) {
    var type = String(e.type == null ? '' : e.type).toLowerCase();
    if (heeft(TYPE_NAAR_SOORT, type)) return TYPE_NAAR_SOORT[type];
    if (heeft(e, 'geoorloofd')) return e.geoorloofd ? 'geo' : 'ong';
    return ((codes[e.code] || {}).soort) || 'geo';
  }

  // ── Datum-hulpjes (in UTC, zodat zomertijd niet meetelt) ─────────────────
  function datum(iso) {
    var p = String(iso).slice(0, 10).split('-');
    return new Date(Date.UTC(+p[0], +p[1] - 1, +p[2]));
  }
  function iso(dt) { return dt.toISOString().slice(0, 10); }
  function plusDagen(dt, n) { return new Date(dt.getTime() + n * 864e5); }
  function weekdag(dt) { return (dt.getUTCDay() + 6) % 7; }          // ma = 0
  function maandag(dt) { return plusDagen(dt, -weekdag(dt)); }
  function isoWeek(dt) {
    var donderdag = plusDagen(dt, 3 - weekdag(dt));
    var jan1 = Date.UTC(donderdag.getUTCFullYear(), 0, 1);
    return Math.ceil(((donderdag - jan1) / 864e5 + 1) / 7);
  }
  function vandaagIso() {
    var d = new Date(), p = function (n) { return String(n).padStart(2, '0'); };
    return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate());
  }

  function dagLabel(dt) {
    return NL_DAG[weekdag(dt)] + ' ' + dt.getUTCDate() + ' ' + NL_MAAND[dt.getUTCMonth() + 1];
  }

  function periodeLabel(begin, einde) {
    var b = datum(begin), e = datum(einde);
    var bm = b.getUTCMonth() + 1, em = e.getUTCMonth() + 1;
    if (bm === em && b.getUTCFullYear() === e.getUTCFullYear()) {
      return NL_DAG[weekdag(b)] + ' ' + b.getUTCDate() + ' – ' + NL_DAG[weekdag(e)] + ' ' +
             e.getUTCDate() + ' ' + NL_MAAND[em] + ' ' + e.getUTCFullYear();
    }
    return NL_DAG[weekdag(b)] + ' ' + b.getUTCDate() + ' ' + NL_MAAND[bm] + ' – ' +
           NL_DAG[weekdag(e)] + ' ' + e.getUTCDate() + ' ' + NL_MAAND[em] + ' ' + e.getUTCFullYear();
  }

  /* Maandagen van begin t/m einde (minstens één week). */
  function maakWeken(begin, einde) {
    var start = maandag(datum(begin)), stop = maandag(datum(einde));
    if (stop < start) stop = start;
    var weken = [];
    for (var cur = start; cur <= stop; cur = plusDagen(cur, 7)) weken.push(cur);
    return weken;
  }

  function weekLabel(ma) {
    var vr = plusDagen(ma, 4);
    var sub = ma.getUTCMonth() === vr.getUTCMonth()
      ? ma.getUTCDate() + '–' + vr.getUTCDate() + ' ' + NL_MAAND[vr.getUTCMonth() + 1]
      : ma.getUTCDate() + ' ' + NL_MAAND[ma.getUTCMonth() + 1] + '–' +
        vr.getUTCDate() + ' ' + NL_MAAND[vr.getUTCMonth() + 1];
    return { label: 'wk ' + isoWeek(ma), sub: sub };
  }

  // ── Leerling-hulpjes ──────────────────────────────────────────────────────
  function naamVan(s) {
    return [s.roepnaam, s.tussenvoegsel, s.achternaam].filter(Boolean).join(' ') ||
           String(s.id == null ? '' : s.id);
  }

  function klasVan(s) {
    var bronnen = [s.klassen || [], s.studies || []];
    for (var i = 0; i < bronnen.length; i++) {
      for (var j = 0; j < bronnen[i].length; j++) if (bronnen[i][j]) return bronnen[i][j];
    }
    return '—';
  }

  /* De mentorgroep is een lesgroep, niet de klas: 'h4mtu1' t/m 'h4mtu8'. */
  function mentorgroepVan(s, patroon) {
    patroon = String(patroon || '').toLowerCase();
    if (!patroon) return '';
    var groepen = s.lesgroepen || [];
    for (var i = 0; i < groepen.length; i++) {
      if (groepen[i] && String(groepen[i]).toLowerCase().indexOf(patroon) !== -1) return groepen[i];
    }
    return '';
  }

  /* Afdeling + leerjaar, bijvoorbeeld 'Havo 4' — de tab van de teamleider.
     De mentorgroep gaat voor; die volgt de indeling preciezer dan de klas. */
  function groepVan(s, mentorgroep) {
    var bronnen = [[mentorgroep || ''], s.klassen || [], s.studies || []];
    for (var i = 0; i < bronnen.length; i++) {
      for (var j = 0; j < bronnen[i].length; j++) {
        var waarde = String(bronnen[i][j] || '');
        if (!waarde) continue;
        var letter = waarde[0].toUpperCase();
        var cijfer = (waarde.slice(1).match(/[0-9]/) || [null])[0];
        if (heeft(AFDELING_NAAM, letter) && cijfer) return AFDELING_NAAM[letter] + ' ' + cijfer;
      }
    }
    return 'Overig';
  }

  function entriesVoor(map, sid) {
    return map[String(sid)] || [];
  }

  /* Magister-logboek is opgemaakte HTML. Die halen we eruit: het is tekst van
     derden en hij komt in een pagina die ook gedownload kan worden. */
  var ENTITEITEN = [['&nbsp;', ' '], ['&amp;', '&'], ['&lt;', '<'], ['&gt;', '>'],
                    ['&quot;', '"'], ['&#39;', "'"], ['&rsquo;', '’'],
                    ['&lsquo;', '‘'], ['&hellip;', '…']];
  var RAND = /^[ \t·• ]+|[ \t·• ]+$/g;
  function htmlNaarTekst(rauw) {
    if (!rauw) return '';
    var tekst = String(rauw).replace(/<\/(p|div|li|tr|h[1-6])>|<br\s*\/?>/gi, '\n')
                            .replace(/<[^>]+>/g, '');
    ENTITEITEN.forEach(function (p) { tekst = tekst.split(p[0]).join(p[1]); });
    return tekst.split('\n').map(function (r) { return r.replace(RAND, ''); })
                .filter(Boolean).join('\n');
  }

  /* De laatste paar logboekformulieren van één leerling, opgeschoond. */
  function logboekVoor(payload, sid, metTekst) {
    var items = (payload.logboek || {})[String(sid)] || [];
    var uit = items.map(function (item) {
      var e = item.eigenaar || {};
      return {
        datum: String(item.aangemaaktOp || '').slice(0, 10),
        titel: item.omschrijving || 'Logboekformulier',
        door:  [e.roepnaam, e.tussenvoegsel, e.achternaam].filter(Boolean).join(' '),
        tekst: metTekst ? htmlNaarTekst(item.inhoud) : ''
      };
    });
    uit.sort(function (a, b) { return cmp(b.datum, a.datum); });
    return uit.slice(0, LOGBOEK_MAX);
  }

  function uurLabel(e) {
    if (e.period) return e.period + 'e uur';
    return e.time || '—';
  }

  // ── Payload → dashboarddata ───────────────────────────────────────────────
  /* Geeft {data, info}; `info` bevat tellingen en de codes die nog ingedeeld
     moeten worden, zodat het venster daarover kan waarschuwen.
     `mentoren` is mentorgroep → mentornaam ('h4mtu1' → 'T. Vermeer'); een
     klasnaam als sleutel werkt ook. */
  function verwerk(payload, codes, config, mentoren, patroon, metLogboek) {
    codes      = codes || {};
    config     = Object.assign({}, STANDAARD_CONFIG, config || {});
    mentoren   = mentoren || {};
    patroon    = patroon == null ? MENTORGROEP_PATROON : patroon;
    metLogboek = metLogboek !== false;

    var students   = payload.students || [];
    var entriesMap = payload.entries || {};
    var period     = payload.period || {};
    var begin = period.begin || vandaagIso();
    var einde = period.einde || vandaagIso();

    // Weekindeling: de opgegeven periode, verbreed met registraties die er
    // (door een ruimere Magister-respons) buiten vallen.
    var datums = [];
    Object.keys(entriesMap).forEach(function (k) {
      (entriesMap[k] || []).forEach(function (e) { if (e.date) datums.push(e.date); });
    });
    var wekenStart = [begin].concat(datums).reduce(function (a, b) { return b < a ? b : a; });
    var wekenEind  = [einde].concat(datums).reduce(function (a, b) { return b > a ? b : a; });
    var weken      = maakWeken(wekenStart, wekenEind);
    var weekIndex  = {};
    weken.forEach(function (m, i) { weekIndex[iso(m)] = i; });

    // Begin van het huidige schooljaar, om te zeggen of er dit jaar al iets
    // in het logboek staat.
    var eindeDt = datum(einde);
    var sjJaar  = eindeDt.getUTCMonth() + 1 >= 8 ? eindeDt.getUTCFullYear() : eindeDt.getUTCFullYear() - 1;
    var schooljaarStart = sjJaar + '-08-01';

    var leerlingen = [], codeTelling = {}, codeNamen = {};

    students.forEach(function (s) {
      var rijEntries = [], ong = 0, laat = 0, ziek = 0, geo = 0;

      entriesVoor(entriesMap, s.id).forEach(function (e) {
        var code = e.code || '?';
        if (!e.date) return;
        var dt = datum(e.date);
        var soort = soortVanRegistratie(e, codes);
        codeTelling[code] = (codeTelling[code] || 0) + 1;
        if (e.naam && !heeft(codeNamen, code)) codeNamen[code] = e.naam;

        if (soort === 'ong') ong++;
        else if (soort === 'laat') laat++;
        else if (soort === 'geo') {
          geo++;
          if (String(e.type == null ? '' : e.type).toLowerCase() === 'ziek' || code === 'ZI') ziek++;
        }

        var wk = weekIndex[iso(maandag(dt))];
        rijEntries.push({
          datum:    iso(dt),
          daglabel: dagLabel(dt),
          week:     wk === undefined ? 0 : wk,
          uur:      e.period || 0,
          uurlabel: uurLabel(e),
          code:     code,
          vak:      e.subject || '',
          soort:    soort
        });
      });

      var klas         = klasVan(s);
      var mentorgroep  = mentorgroepVan(s, patroon);
      var logboekItems = logboekVoor(payload, s.id, metLogboek);
      leerlingen.push({
        id:          String(s.id == null ? '' : s.id),     // sleutel voor contactnotities
        naam:        naamVan(s),
        klas:        klas,
        mentorgroep: mentorgroep,
        groep:       groepVan(s, mentorgroep),
        // Volgorde: wat Magister zelf meegeeft, anders de ingevulde lijst.
        mentor:      s.mentor || (mentorgroep && mentoren[mentorgroep]) || mentoren[klas] || '',
        ong: ong, laat: laat, ziek: ziek, geo: geo,
        entries:     rijEntries,
        logboek:     logboekItems,
        logboekDitJaar: logboekItems.some(function (x) { return x.datum >= schooljaarStart; })
      });
    });

    var groepen = Object.keys(leerlingen.reduce(function (o, l) { o[l.groep] = 1; return o; }, {}))
                        .sort(cmp);
    if (groepen.indexOf('Overig') !== -1) {                // 'Overig' altijd achteraan
      groepen = groepen.filter(function (g) { return g !== 'Overig'; }).concat(['Overig']);
    }

    // Wat Magister meegaf wint van onze eigen lijst; die blijft de terugval.
    var codesUit = {};
    Object.keys(codes).forEach(function (c) { codesUit[c] = Object.assign({}, codes[c]); });
    Object.keys(codeNamen).forEach(function (c) {
      codesUit[c] = Object.assign({}, codesUit[c] || {}, { naam: codeNamen[c] });
    });
    leerlingen.forEach(function (l) {
      l.entries.forEach(function (e) {
        codesUit[e.code] = heeft(codesUit, e.code)
          ? Object.assign({}, codesUit[e.code], { soort: e.soort })
          : { naam: e.code, soort: e.soort };
      });
    });

    var data = {
      periode:    { begin: begin, einde: einde, label: periodeLabel(begin, einde) },
      config:     config,
      codes:      codesUit,
      weken:      weken.map(weekLabel),
      // Maandag van elke week, zodat de patroonstrook per lesdag kan tekenen.
      weekStarts: weken.map(iso),
      groepen:    ['Alle'].concat(groepen),
      logboekOpgehaald: !!payload.logboek_bron,
      leerlingen: leerlingen
    };

    var gebruikt = Object.keys(codeTelling);
    var mentorgroepen = Object.keys(leerlingen.reduce(function (o, l) {
      if (l.mentorgroep) o[l.mentorgroep] = 1; return o; }, {})).sort(cmp);
    var info = {
      aantalLeerlingen:   leerlingen.length,
      aantalRegistraties: gebruikt.reduce(function (n, c) { return n + codeTelling[c]; }, 0),
      weken:              weken.length,
      codeTelling:        gebruikt.slice().sort(function (a, b) { return codeTelling[b] - codeTelling[a]; })
                                  .map(function (c) { return [c, codeTelling[c]]; }),
      onbekendeCodes:     gebruikt.filter(function (c) {
                            return !heeft(codes, c) && !heeft(codeNamen, c); }).sort(cmp),
      teControlerenCodes: gebruikt.filter(function (c) {
                            return (codes[c] || {}).controleren; }).sort(cmp),
      scope:              payload.scope || '',
      mentorgroepen:      mentorgroepen,
      mentorgroepenZonderNaam: mentorgroepen.filter(function (g) { return !mentoren[g]; }),
      zonderMentorgroep:  leerlingen.filter(function (l) { return !l.mentorgroep; }).length,
      logboekAantal:      leerlingen.reduce(function (n, l) { return n + l.logboek.length; }, 0),
      logboekBron:        payload.logboek_bron || '',
      logboekDiag:        payload.logboek_diag || [],
      verzuimFouten:      payload.verzuim_fouten || 0
    };
    return { data: data, info: info };
  }

  // ── HTML ──────────────────────────────────────────────────────────────────
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#x27;' })[c];
    });
  }

  /* '<' escapen zodat een vak- of leerlingnaam het <script>-blok niet kan sluiten. */
  function dataJson(data) {
    return JSON.stringify(data).replace(/</g, '\\u003c')
               .replace(/\u2028/g, '\\u2028').replace(/\u2029/g, '\\u2029');
  }

  function demoBanner(tekst) {
    tekst = tekst || 'Alle namen, klassen en cijfers op deze pagina zijn <b>verzonnen</b>. ' +
                     'Er staat geen enkel gegeven van een echte leerling in.';
    return '<div class="demo-flag"><strong>Demo</strong><span>' + tekst + '</span></div>';
  }

  /* `opties`: codes, config, mentoren, patroon, metLogboek, banner, bron.
     `bronnen`: de tekst van template.html, render.js, coordinator.js en
     coordinator.css. Geeft {html, info}. */
  function bouwTeamleider(payload, opties, bronnen) {
    opties = opties || {};
    var r = verwerk(payload, opties.codes, opties.config, opties.mentoren,
                    opties.patroon, opties.metLogboek);
    var data = r.data, info = r.info, cfg = data.config;

    var wekenTxt = info.weken + ' lesweken';
    if (info.scope) wekenTxt += ' · selectie ' + esc(info.scope);
    wekenTxt += ' · ' + info.aantalLeerlingen + ' leerlingen';

    var vervang = {
      '{{BANNER}}':      opties.banner || '',
      '{{PERIODE}}':     data.periode.label,
      '{{PERIODE_SUB}}': wekenTxt,
      '{{NORM_CRIT}}':   String(cfg.normCrit),
      '{{NORM_LAAT}}':   String(cfg.normLaat),
      '{{BRON}}':        opties.bron || '',
      '{{DATA_JSON}}':   dataJson(data),
      '{{RENDER_JS}}':   bronnen.renderJs
    };
    // In één keer vervangen: data die toevallig op een placeholder lijkt blijft data.
    var html = bronnen.template.replace(/\{\{[A-Z_0-9]+\}\}/g, function (m) {
      return heeft(vervang, m) ? vervang[m] : m;
    });
    return { html: html, info: info };
  }

  /* Weekbeeld voor een coördinator met een eigen lijst leerlingen. De opmaak
     leunt op template.html: daar staan de kleuren en de basisstijlen. */
  function bouwCoordinator(payload, opties, bronnen) {
    opties = opties || {};
    var r = verwerk(payload, opties.codes, opties.config, opties.mentoren,
                    opties.patroon, opties.metLogboek);
    var data = r.data, info = r.info;
    var basis = bronnen.template.slice(0, bronnen.template.indexOf('</head>'));
    var html = basis +
      '<style>\n' + bronnen.coordinatorCss + '</style>\n</head>\n<body>\n' +
      '<div class="wrap">\n' + (opties.banner || '') +
      '  <div class="masthead kop-rij">\n' +
      '    <div>\n      <h1>Mijn leerlingen</h1>\n' +
      '      <p>Hoe ging deze week, en wat liep er in de weken ervoor?</p>\n    </div>\n' +
      '    <div class="meta">\n      <b id="weeklabel"></b>\n      ' +
      info.aantalLeerlingen + ' leerlingen · ' + data.periode.label + '\n    </div>\n  </div>\n\n' +
      '  <div class="tiles" id="tiles"></div>\n\n  <div class="kaarten" id="kaarten"></div>\n\n' +
      '  <footer>\n    <b>Hoe je dit leest.</b> Bovenaan staat de leerling waar deze week het meest\n' +
      '    speelde. De vijf vakken zijn de lesdagen van deze week met de codes die er\n' +
      '    staan; de streepjes daaronder zijn de weken ervoor, één blokje per lesdag.\n' +
      '    Ziek en verlof staan er als context bij en tellen niet als ongeoorloofd.\n    ' +
      (opties.bron || '') + '\n  </footer>\n</div>\n\n' +
      '<div id="tip" role="status" aria-live="polite"></div>\n\n' +
      '<script>window.DATA = ' + dataJson(data) + ';</script>\n' +
      '<script>\n' + bronnen.coordinatorJs + '\n</script>\n</body>\n</html>\n';
    return { html: html, info: info };
  }

  root.VZS = {
    MENTORGROEP_PATROON: MENTORGROEP_PATROON,
    STANDAARD_CONFIG: STANDAARD_CONFIG,
    verwerk: verwerk,
    bouwTeamleider: bouwTeamleider,
    bouwCoordinator: bouwCoordinator,
    demoBanner: demoBanner,
    htmlNaarTekst: htmlNaarTekst,
    esc: esc
  };
})(typeof window !== 'undefined' ? window : globalThis);
