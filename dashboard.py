"""
dashboard.py — bouwt het verzuimdashboard (HTML) uit een bookmarklet-payload.

De payload komt uit Magister (zie bookmarklet.py) en ziet er zo uit:

    {
      "period":   {"begin": "2026-09-01", "einde": "2026-09-26"},
      "scope":    "H4,H5",                       # wat de gebruiker filterde
      "students": [{"id": 1, "roepnaam": ..., "achternaam": ...,
                    "klassen": ["H4A"], "studies": ["H4"]}, ...],
      "entries":  {"1": [{"date": "2026-09-03", "time": "08:30",
                          "code": "A", "period": 2, "subject": "Nederlands"}]}
    }

Alles wat geteld moet worden (uren per soort, weekindeling, groepen) gebeurt
hier in Python; `render.js` tekent alleen nog. Zo geven de app en het
gedownloade losse HTML-bestand gegarandeerd dezelfde cijfers.
"""

import re
import json
from pathlib import Path
from datetime import date, timedelta
from collections import defaultdict

HIER = Path(__file__).parent

NL_DAG   = ['ma', 'di', 'wo', 'do', 'vr', 'za', 'zo']
NL_MAAND = ['', 'jan', 'feb', 'mrt', 'apr', 'mei', 'jun',
            'jul', 'aug', 'sep', 'okt', 'nov', 'dec']

AFDELING_NAAM = {'H': 'Havo', 'M': 'Mavo', 'V': 'Vwo', 'A': 'Atheneum', 'G': 'Gymnasium'}

# Waaraan je de mentorgroep herkent in de lesgroepnamen: h4mtu1 … h4mtu8.
MENTORGROEP_PATROON = 'mtu'

STANDAARD_CONFIG = {
    'normCrit': 16,   # uren ongeoorloofd → meldplicht leerplicht
    'normWarn': 10,   # uren ongeoorloofd → nadert de grens
    'normLaat': 6,    # keer te laat → eigen signaal
}


# ── Codes ─────────────────────────────────────────────────────────────────────
def laad_codes(pad=None):
    """Codetabel uit codes.json (of de meegegeven plek)."""
    pad = Path(pad) if pad else HIER / 'codes.json'
    with open(pad, encoding='utf-8') as f:
        return json.load(f).get('codes', {})


def bewaar_codes(codes, pad=None):
    """Schrijf de codetabel terug, met de uitleg-regel intact."""
    pad = Path(pad) if pad else HIER / 'codes.json'
    with open(pad, encoding='utf-8') as f:
        bestand = json.load(f)
    bestand['codes'] = codes
    with open(pad, 'w', encoding='utf-8') as f:
        json.dump(bestand, f, ensure_ascii=False, indent=2)


def soort_van(code, codes):
    return (codes.get(code) or {}).get('soort', 'geo')


# ── Datum-hulpjes ─────────────────────────────────────────────────────────────
def _d(iso):
    return date.fromisoformat(iso[:10])


def dag_label(dt):
    return f'{NL_DAG[dt.weekday()]} {dt.day} {NL_MAAND[dt.month]}'


def periode_label(begin, einde):
    b, e = _d(begin), _d(einde)
    if (b.month, b.year) == (e.month, e.year):
        return f'{NL_DAG[b.weekday()]} {b.day} – {NL_DAG[e.weekday()]} {e.day} {NL_MAAND[e.month]} {e.year}'
    return (f'{NL_DAG[b.weekday()]} {b.day} {NL_MAAND[b.month]} – '
            f'{NL_DAG[e.weekday()]} {e.day} {NL_MAAND[e.month]} {e.year}')


def _maandag(dt):
    return dt - timedelta(days=dt.weekday())


def maak_weken(begin, einde):
    """Lijst maandagen van begin t/m einde (minstens één week)."""
    start, stop = _maandag(_d(begin)), _maandag(_d(einde))
    if stop < start:
        stop = start
    weken, cur = [], start
    while cur <= stop:
        weken.append(cur)
        cur += timedelta(days=7)
    return weken


def week_label(maandag):
    vrijdag = maandag + timedelta(days=4)
    if maandag.month == vrijdag.month:
        sub = f'{maandag.day}–{vrijdag.day} {NL_MAAND[vrijdag.month]}'
    else:
        sub = f'{maandag.day} {NL_MAAND[maandag.month]}–{vrijdag.day} {NL_MAAND[vrijdag.month]}'
    return {'label': f'wk {maandag.isocalendar()[1]}', 'sub': sub}


# ── Leerling-hulpjes ──────────────────────────────────────────────────────────
def naam_van(s):
    return ' '.join(filter(None, [
        s.get('roepnaam'), s.get('tussenvoegsel'), s.get('achternaam')
    ])) or str(s.get('id', ''))


def klas_van(s):
    for bron in (s.get('klassen') or [], s.get('studies') or []):
        for waarde in bron:
            if waarde:
                return waarde
    return '—'


def mentorgroep_van(s, patroon=MENTORGROEP_PATROON):
    """De mentorgroep is een lesgroep, niet de klas: 'h4mtu1' t/m 'h4mtu8'.

    Daar hangt de mentor aan vast. Welke lesgroep het is, herkennen we aan een
    stukje tekst in de naam ('mtu').
    """
    patroon = (patroon or '').lower()
    if not patroon:
        return ''
    for lesgroep in s.get('lesgroepen') or []:
        if lesgroep and patroon in lesgroep.lower():
            return lesgroep
    return ''


def groep_van(s, mentorgroep=''):
    """Afdeling + leerjaar, bijvoorbeeld 'Havo 4' — de tab van de teamleider.

    De mentorgroep gaat voor ('h4mtu1' → Havo 4); die volgt de indeling van de
    teamleider preciezer dan de klas van een individuele leerling.
    """
    for bron in ([mentorgroep], s.get('klassen') or [], s.get('studies') or []):
        for waarde in bron:
            if not waarde:
                continue
            letter = waarde[0].upper()
            cijfer = next((c for c in waarde[1:] if c.isdigit()), None)
            if letter in AFDELING_NAAM and cijfer:
                return f'{AFDELING_NAAM[letter]} {cijfer}'
    return 'Overig'


def mentorgroepen_van(payload, patroon=MENTORGROEP_PATROON):
    """Alle mentorgroepen in een payload — om de mentorenlijst voor te vullen."""
    return sorted({mentorgroep_van(s, patroon)
                   for s in payload.get('students', [])} - {''})


def _entries_voor(entries_map, sid):
    """entries-keys zijn strings na een JSON-rondje; id kan int of str zijn."""
    return entries_map.get(str(sid)) or entries_map.get(sid) or []


_BLOK_EIND = re.compile(r'</(p|div|li|tr|h[1-6])>|<br\s*/?>', re.I)
_TAGS      = re.compile(r'<[^>]+>')


def html_naar_tekst(rauw):
    """Magister-logboek is opgemaakte HTML. Die halen we eruit.

    Bewust geen HTML doorlaten naar het dashboard: het is tekst van derden en
    hij komt in een pagina die de teamleider ook kan downloaden.
    """
    if not rauw:
        return ''
    tekst = _BLOK_EIND.sub('\n', rauw)
    tekst = _TAGS.sub('', tekst)
    for entiteit, teken in (('&nbsp;', ' '), ('&amp;', '&'), ('&lt;', '<'),
                            ('&gt;', '>'), ('&quot;', '"'), ('&#39;', "'"),
                            ('&rsquo;', '\u2019'), ('&lsquo;', '\u2018'),
                            ('&hellip;', '\u2026')):
        tekst = tekst.replace(entiteit, teken)
    regels = [r.strip(' \t\u00b7\u2022\xa0') for r in tekst.split('\n')]
    return '\n'.join(r for r in regels if r)


LOGBOEK_MAX = 3          # meer dan drie is in dit overzicht niet nuttig


def _logboek_voor(payload, sid, met_tekst=True):
    """De laatste paar logboekformulieren van één leerling, opgeschoond."""
    bron = payload.get('logboek') or {}
    items = bron.get(str(sid)) or bron.get(sid) or []
    uit = []
    for item in items:
        eigenaar = item.get('eigenaar') or {}
        door = ' '.join(filter(None, [eigenaar.get('roepnaam'),
                                      eigenaar.get('tussenvoegsel'),
                                      eigenaar.get('achternaam')]))
        uit.append({
            'datum':  (item.get('aangemaaktOp') or '')[:10],
            'titel':  item.get('omschrijving') or 'Logboekformulier',
            'door':   door,
            'tekst':  html_naar_tekst(item.get('inhoud')) if met_tekst else '',
        })
    uit.sort(key=lambda x: x['datum'], reverse=True)
    return uit[:LOGBOEK_MAX]


def _uur_label(e):
    uur = e.get('period')
    if uur:
        return f'{uur}e uur'
    return e.get('time') or '—'


# ── Payload → dashboarddata ───────────────────────────────────────────────────
def verwerk(payload, codes, config=None, mentoren=None,
            patroon=MENTORGROEP_PATROON, met_logboek=True):
    """Zet een bookmarklet-payload om in de datastructuur die render.js leest.

    `mentoren` is een mapping mentorgroep → mentornaam ('h4mtu1' → 'T. Vermeer');
    een klasnaam als sleutel werkt ook nog, voor wie het zo heeft ingevuld.

    Geeft (data, info) terug; `info` bevat tellingen en de codes die nog
    ingedeeld moeten worden, zodat de app daarover kan waarschuwen.
    """
    config   = {**STANDAARD_CONFIG, **(config or {})}
    mentoren = mentoren or {}

    students    = payload.get('students', [])
    entries_map = payload.get('entries', {})
    period      = payload.get('period', {})
    begin = period.get('begin') or date.today().isoformat()
    einde = period.get('einde') or date.today().isoformat()

    # Weekindeling: de opgegeven periode, verbreed met registraties die er
    # (door een ruimere Magister-respons) buiten vallen.
    datums = [e['date'] for lijst in entries_map.values() for e in lijst if e.get('date')]
    weken_start = min([begin] + datums)
    weken_eind  = max([einde] + datums)
    weken       = maak_weken(weken_start, weken_eind)
    week_index  = {m: i for i, m in enumerate(weken)}

    # Grens van het huidige schooljaar, om te kunnen zeggen of er dit jaar al
    # iets in het logboek staat.
    einde_dt = _d(einde)
    schooljaar_start = date(einde_dt.year if einde_dt.month >= 8
                            else einde_dt.year - 1, 8, 1).isoformat()

    leerlingen  = []
    code_telling = defaultdict(int)

    for s in students:
        rij_entries = []
        ong = laat = ziek = geo = 0

        for e in _entries_voor(entries_map, s['id']):
            code = e.get('code') or '?'
            if not e.get('date'):
                continue
            dt = _d(e['date'])
            soort = soort_van(code, codes)
            code_telling[code] += 1

            if soort == 'ong':
                ong += 1
            elif soort == 'laat':
                laat += 1
            else:
                geo += 1
                if code == 'ZI':
                    ziek += 1

            rij_entries.append({
                'datum':    dt.isoformat(),
                'daglabel': dag_label(dt),
                'week':     week_index.get(_maandag(dt), 0),
                'uur':      e.get('period') or 0,
                'uurlabel': _uur_label(e),
                'code':     code,
                'vak':      e.get('subject') or '',
                'soort':    soort,
            })

        klas          = klas_van(s)
        mentorgroep   = mentorgroep_van(s, patroon)
        logboek_items = _logboek_voor(payload, s['id'], met_logboek)
        leerlingen.append({
            'id':          str(s.get('id', '')),      # sleutel voor contactnotities
            'naam':        naam_van(s),
            'klas':        klas,
            'mentorgroep': mentorgroep,
            'groep':       groep_van(s, mentorgroep),
            'mentor':      mentoren.get(mentorgroep) or mentoren.get(klas, ''),
            'ong': ong, 'laat': laat, 'ziek': ziek, 'geo': geo,
            'entries': rij_entries,
            'logboek': logboek_items,
            'logboekDitJaar': any(x['datum'] >= schooljaar_start for x in logboek_items),
        })

    groepen = sorted({l['groep'] for l in leerlingen})
    if 'Overig' in groepen:                      # 'Overig' altijd achteraan
        groepen = [g for g in groepen if g != 'Overig'] + ['Overig']

    data = {
        'periode': {'begin': begin, 'einde': einde, 'label': periode_label(begin, einde)},
        'config':  config,
        'codes':   codes,
        'weken':   [week_label(m) for m in weken],
        'groepen': ['Alle'] + groepen,
        'logboekOpgehaald': bool(payload.get('logboek_bron')),
        'leerlingen': leerlingen,
    }

    onbekend = sorted(c for c in code_telling if c not in codes)
    controleren = sorted(c for c in code_telling
                         if (codes.get(c) or {}).get('controleren'))
    info = {
        'aantal_leerlingen': len(leerlingen),
        'aantal_registraties': sum(code_telling.values()),
        'weken': len(weken),
        'code_telling': dict(sorted(code_telling.items(), key=lambda x: -x[1])),
        'onbekende_codes': onbekend,
        'te_controleren_codes': controleren,
        'scope': payload.get('scope', ''),
        'mentorgroepen': sorted({l['mentorgroep'] for l in leerlingen} - {''}),
        'zonder_mentorgroep': sum(1 for l in leerlingen if not l['mentorgroep']),
        'logboek_aantal': sum(len(l['logboek']) for l in leerlingen),
        'logboek_bron': payload.get('logboek_bron', ''),
        'logboek_diag': payload.get('logboek_diag') or [],
    }
    return data, info


# ── HTML ──────────────────────────────────────────────────────────────────────
def bouw_html(payload, codes=None, config=None, mentoren=None,
              patroon=MENTORGROEP_PATROON, banner='', bron='', met_logboek=True):
    """Compleet, zelfstandig HTML-bestand (geen externe scripts).

    met_logboek=False laat de logboekteksten weg — voor het bestand dat de
    teamleider downloadt en dus buiten de app terechtkomt.
    """
    codes = codes if codes is not None else laad_codes()
    data, info = verwerk(payload, codes, config, mentoren, patroon, met_logboek)
    cfg = data['config']

    ong_codes = [f'<b>{c}</b> ({v.get("naam", c).lower()})'
                 for c, v in codes.items() if v.get('soort') == 'ong']
    ong_txt = ' en '.join(ong_codes) if ong_codes else '<b>—</b>'

    weken_txt = f"{info['weken']} lesweken"
    if info['scope']:
        weken_txt += f" · selectie {info['scope']}"
    weken_txt += f" · {info['aantal_leerlingen']} leerlingen"

    sjabloon = (HIER / 'template.html').read_text(encoding='utf-8')
    render_js = (HIER / 'render.js').read_text(encoding='utf-8')

    vervang = {
        '{{BANNER}}':         banner or '',
        '{{PERIODE}}':        data['periode']['label'],
        '{{PERIODE_SUB}}':    weken_txt,
        '{{NORM_CRIT}}':      str(cfg['normCrit']),
        '{{NORM_CRIT_MIN1}}': str(cfg['normCrit'] - 1),
        '{{NORM_WARN}}':      str(cfg['normWarn']),
        '{{NORM_WARN_MIN1}}': str(cfg['normWarn'] - 1),
        '{{NORM_LAAT}}':      str(cfg['normLaat']),
        '{{ONG_CODES}}':      ong_txt,
        '{{BRON}}':           bron or '',
        # '<' escapen zodat een vak- of leerlingnaam het <script>-blok niet kan sluiten
        '{{DATA_JSON}}':      json.dumps(data, ensure_ascii=False).replace('<', '\\u003c'),
        '{{RENDER_JS}}':      render_js,
    }
    # In één keer vervangen: data die toevallig op een placeholder lijkt blijft data.
    html = re.sub(r'\{\{[A-Z_0-9]+\}\}',
                  lambda m: vervang.get(m.group(0), m.group(0)), sjabloon)
    return html, info


def demo_banner(tekst='Alle namen, klassen en cijfers op deze pagina zijn '
                      '<b>verzonnen</b>. Er staat geen enkel gegeven van een echte '
                      'leerling in.'):
    return f'<div class="demo-flag"><strong>Demo</strong><span>{tekst}</span></div>'
