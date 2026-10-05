"""
app.py — Verzuimsignalering voor teamleiders en coördinatoren.

Flow:
0. De gebruiker komt binnen via het portaal, met een SSO-token in de URL.
1. Hier sleept hij eenmalig een bladwijzer naar de bladwijzerbalk.
2. In het ingelogde Magister-tabblad klikt hij die aan. Er opent een
   rapportvenster; daarin kiest hij periode en selectie.
3. De bladwijzer haalt het verzuim op met zijn eigen Magister-sessie en geeft
   het door aan dat venster. Het venster rekent en tekent het dashboard.

Het verzuim komt dus **niet op de server**: niet in deze app, niet in de
ontvanger, niet tijdelijk in het geheugen. De app beheert alleen instellingen
(codes, mentornamen, grenzen), de leerlingnummers van de coördinator en
klaargezette logboeknotities. Zie README.md.

Start met:  streamlit run app.py
"""

import os
import json
import hmac
import hashlib
import secrets
from pathlib import Path

import jwt
import streamlit as st

# Het pakket `jwt` (1.x) heet net zo als PyJWT en verdringt het. Dan zou de app
# pas bij het inloggen omvallen met een onbegrijpelijke AttributeError.
if not hasattr(jwt, 'decode'):
    raise SystemExit(
        'Verkeerde jwt-module: dit is het pakket `jwt`, niet PyJWT.\n'
        'Herstellen met:  pip uninstall -y jwt && pip install --force-reinstall PyJWT')

import ingest
import rapport
import bookmarklet
import dashboard
import coordinator

HIER          = Path(__file__).parent
MENTOREN_PAD  = HIER / 'mentoren.json'
SECRET_PAD    = HIER / '.secret'
VOORBEELD_PAD = HIER / 'voorbeeld_school.json'
LIJSTEN_PAD   = HIER / 'lijsten.json'

# Zelfde SSO-token als de andere apps van het portaal.
JWT_SECRET    = os.environ.get('JWT_SECRET', '').strip()
JWT_ALGORITHM = 'HS256'
PORTAAL_URL   = os.environ.get('PORTAAL_URL', 'https://bovenbouwsucces.nl')
TOEGESTANE_ROLLEN = ('docent', 'beheerder')

# Eigen naam, zodat de knop niet te verwarren is met de bookmarklet van de
# mentoruur-app (die heet '📋 Verzuim ophalen' en pakt één mentorgroep).
KNOP_NAAM      = 'Verzuim teamleider'
KNOP           = f'📋 {KNOP_NAAM}'
KNOP_COORD     = '📋 Mijn leerlingen ophalen'

# Logboektypen zoals Magister ze kent. Welke je mag aanmaken hangt af van je rol
# bij die leerling; de bookmarklet gebruikt gewoon wat jij hier kiest en meldt
# het als Magister het weigert.
LOGBOEK_TYPEN = {
    'Mentoraat': 42,
    'Notitie': 7,
    'Afspraak': 4,
    'Incident': 6,
}

st.set_page_config(page_title='Verzuimsignalering', page_icon='📋', layout='wide',
                   initial_sidebar_state='collapsed')   # rust in de pagina


# ── Instellingen ──────────────────────────────────────────────────────────────
def _secret():
    """Stabiel geheim, zodat het bookmarklet-token na herstart nog klopt."""
    uit_env = os.environ.get('VERZUIM_TL_SECRET', '').strip()
    if uit_env:
        return uit_env
    if not SECRET_PAD.exists():
        SECRET_PAD.write_text(secrets.token_hex(32), encoding='utf-8')
    return SECRET_PAD.read_text(encoding='utf-8').strip()


def _token():
    """Token van de bookmarklet — per gebruiker.

    Het eckid zit erin, zodat de lijst en de schrijfwachtrij van de één niet
    bij de ander terechtkomen.
    """
    wie = st.session_state.get('eckid') or 'lokaal'
    return hmac.new(_secret().encode(),
                    f'verzuimsignalering-teamleider:{wie}'.encode(),
                    hashlib.sha256).hexdigest()[:16]


# ── Inloggen via het portaal ──────────────────────────────────────────────────
def _verwerk_sso_token():
    """Leest ?token=<JWT> uit de URL, zoals het portaal die meegeeft."""
    if st.session_state.get('eckid'):
        return

    token = st.query_params.get('token')
    if not token:
        return

    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        st.query_params.clear()
        st.warning('Je sessie is verlopen. Ga terug naar het portaal en klik de '
                   'tegel opnieuw aan.')
        return
    except jwt.InvalidTokenError:
        st.query_params.clear()
        st.error('Ongeldig token.')
        return

    eckid = payload.get('eckid')
    rol   = payload.get('rol', '')
    if not eckid or rol not in TOEGESTANE_ROLLEN:
        st.query_params.clear()
        st.warning('Geen toegang: deze app is voor mentoren en teamleiders.')
        return

    st.session_state.eckid   = eckid
    st.session_state.naam    = payload.get('naam', '')
    st.session_state.rol     = rol
    st.session_state.app_rol = (payload.get('app_rollen') or {}).get('verzuim', '')
    st.query_params.clear()
    st.rerun()


def inloggen():
    """Laat de app alleen door voor wie via het portaal binnenkomt.

    Voor lokaal ontwikkelen: VERZUIM_TL_ZONDER_LOGIN=1 slaat dit over. Zet dat
    nooit op een server — dan kan iedereen die de URL kent meekijken.
    """
    if os.environ.get('VERZUIM_TL_ZONDER_LOGIN') == '1':
        st.session_state.setdefault('eckid', 'lokaal')
        st.session_state.setdefault('naam', 'Lokale test')
        return

    if not JWT_SECRET:
        st.error('Configuratiefout: JWT_SECRET is niet gezet. Zonder gedeeld geheim '
                 'met het portaal kan niemand inloggen.')
        st.stop()

    _verwerk_sso_token()
    if st.session_state.get('eckid'):
        return

    st.title('📋 Verzuimsignalering')
    st.warning(f'Log in via [het portaal]({PORTAAL_URL}) en klik daar de tegel '
               'van deze app aan.')
    st.stop()


def _ingest_config():
    """(url, poort) van de ontvanger. Leeg zetten schakelt de bladwijzer uit.

    Eigen namen en een eigen poort (8766), want de mentoruur-app gebruikt
    VERZUIM_INGEST_URL/PORT en poort 8765.

    Lokaal werkt http://localhost:8766 gewoon vanaf de https-pagina van
    Magister: browsers behandelen localhost als een veilige origin.
    """
    url  = os.environ.get('VERZUIM_TL_INGEST_URL', 'http://localhost:8766').strip()
    port = int(os.environ.get('VERZUIM_TL_INGEST_PORT', '8766'))
    return (url or None), port


def _rapport_url(ingest_url):
    """Publieke URL van het rapportvenster; standaard levert de ontvanger het."""
    eigen = os.environ.get('VERZUIM_TL_RAPPORT_URL', '').strip()
    return eigen or ingest_url.rstrip('/') + '/rapport.html'


def laad_mentoren():
    if MENTOREN_PAD.exists():
        try:
            return json.loads(MENTOREN_PAD.read_text(encoding='utf-8'))
        except Exception:
            return {}
    return {}


def bewaar_mentoren(mapping):
    MENTOREN_PAD.write_text(
        json.dumps(mapping, ensure_ascii=False, indent=2), encoding='utf-8')


def laad_lijst(eckid):
    """De leerlingnummers van deze coördinator."""
    if not LIJSTEN_PAD.exists():
        return []
    try:
        return json.loads(LIJSTEN_PAD.read_text(encoding='utf-8')).get(eckid, [])
    except Exception:
        return []


def bewaar_lijst(eckid, ids):
    alles = {}
    if LIJSTEN_PAD.exists():
        try:
            alles = json.loads(LIJSTEN_PAD.read_text(encoding='utf-8'))
        except Exception:
            alles = {}
    alles[eckid] = ids
    LIJSTEN_PAD.write_text(json.dumps(alles, ensure_ascii=False, indent=2), encoding='utf-8')


def _gedeelde_instellingen():
    """Wat voor iedereen geldt; de ontvanger vraagt dit bij elke klik opnieuw op."""
    try:
        codes = dashboard.laad_codes()
    except Exception:
        codes = {}
    return {'codes': codes, 'mentoren': laad_mentoren(),
            **dashboard.STANDAARD_CONFIG, 'patroon': dashboard.MENTORGROEP_PATROON}


# ── Sidebar ───────────────────────────────────────────────────────────────────
def sidebar():
    """Instellingen die het rapportvenster via de bladwijzer meekrijgt."""
    st.sidebar.header('Instellingen')
    naam = st.session_state.get('naam')
    if naam:
        st.sidebar.caption(f'Ingelogd als {naam}')
    st.sidebar.caption('Deze instellingen gelden bij je volgende klik op de bladwijzer.')

    st.sidebar.subheader('Grenzen')
    config = {
        'normCrit': st.sidebar.number_input(
            "Label 'melden' vanaf (uren ongeoorloofd)", 1, 100,
            dashboard.STANDAARD_CONFIG['normCrit'], key='normCrit'),
        'normLaat': st.sidebar.number_input(
            "Signaal 'vaak te laat' vanaf (keer)", 1, 100,
            dashboard.STANDAARD_CONFIG['normLaat'], key='normLaat'),
    }

    st.sidebar.subheader('Standaard selectie')
    config['scope'] = st.sidebar.text_input(
        'Klassen of leerjaren', key='scope',
        help="Wordt voorgesteld in het rapportvenster, bijvoorbeeld 'H4,H5'. "
             'Leeg = alles wat je in Magister mag zien.')

    st.sidebar.subheader('Mentorgroepen')
    config['patroon'] = st.sidebar.text_input(
        'Mentorgroep herkennen aan', dashboard.MENTORGROEP_PATROON, key='patroon',
        help="De mentorgroep is een lesgroep, niet de klas: h4mtu1 t/m h4mtu8. "
             "Dit stukje tekst moet in de lesgroepnaam zitten.")

    st.sidebar.subheader('Logboek')
    config['logboekInDownload'] = st.sidebar.checkbox(
        'Logboektekst in de download', value=False, key='logboek_in_download',
        help='In het rapportvenster zie je het logboek altijd. Het losse HTML-bestand '
             'komt daarbuiten terecht; daar laten we die teksten standaard uit.')

    huidig = laad_mentoren()
    tekst = st.sidebar.text_area(
        'Eén per regel: mentorgroep = mentor',
        '\n'.join(f'{g} = {n}' for g, n in sorted(huidig.items())), height=160,
        help='Magister geeft de mentor niet mee bij het zoeken naar leerlingen. '
             'Wat je hier invult verschijnt bij de leerling en in het overzicht per '
             'mentorgroep. Het rapportvenster toont welke mentorgroepen nog geen naam '
             'hebben; die lijst kun je hier plakken.')
    if st.sidebar.button('Mentoren opslaan', width='stretch'):
        mapping = {}
        for regel in tekst.splitlines():
            if '=' in regel:
                groep, naam = regel.split('=', 1)
                if groep.strip() and naam.strip():
                    mapping[groep.strip()] = naam.strip()
        bewaar_mentoren(mapping)
        st.sidebar.success(f'{len(mapping)} mentorgroepen opgeslagen.')
        st.rerun()

    return config


def codes_editor(codes):
    """Codes indelen als ongeoorloofd / te laat / geoorloofd."""
    with st.expander('Verzuimcodes indelen'):
        st.caption('Magister geeft per registratie zelf door wat een code betekent en of '
                   'hij geoorloofd is; die informatie wint. Deze lijst is de terugval, '
                   'voor oudere bestanden en codes die Magister niet duidt. Het '
                   'rapportvenster meldt welke codes nog onbekend zijn.')
        rijen = [{'code': c, 'naam': v.get('naam', c), 'soort': v.get('soort', 'geo')}
                 for c, v in codes.items()]
        rijen.sort(key=lambda r: r['code'])

        bewerkt = st.data_editor(
            rijen, hide_index=True, width='stretch', key='codes_editor', num_rows='dynamic',
            column_config={
                'code': st.column_config.TextColumn('Code', width='small'),
                'naam': st.column_config.TextColumn('Betekenis'),
                'soort': st.column_config.SelectboxColumn(
                    'Telt als', options=['ong', 'laat', 'vergeten', 'geo'], required=True,
                    help='ong = ongeoorloofd (telt in de norm), laat = te laat, '
                         'vergeten = huiswerk of materiaal vergeten (geen verzuim), '
                         'geo = geoorloofd'),
            })
        if st.button('Codes opslaan'):
            nieuw = {str(r['code']).strip(): {'naam': r.get('naam') or r['code'],
                                               'soort': r.get('soort') or 'geo'}
                     for r in bewerkt if r.get('code') and str(r['code']).strip()}
            dashboard.bewaar_codes(nieuw)
            st.success('Codes opgeslagen.')
            st.rerun()


# ── Koppeling met de bladwijzer ───────────────────────────────────────────────
def _ontvanger_aan(port):
    """Start de ontvanger; False (met melding) als dat niet lukt."""
    try:
        ingest.ensure_server(port)
        return True
    except OSError as ex:
        st.error(f'De ontvanger kan niet starten op poort {port} ({ex}). Draait er al '
                 'een andere app op die poort? Kies een andere via VERZUIM_TL_INGEST_PORT.')
        return False


def koppeling(config):
    """Zet klaar wat de bladwijzer bij de app ophaalt. Geeft (rapport_url,
    ingest_url) terug, of (None, None) als de ontvanger niet draait."""
    ingest_url, port = _ingest_config()
    if not ingest_url or not _ontvanger_aan(port):
        return None, None
    token = _token()
    ingest.zet_standaard(_gedeelde_instellingen)
    ingest.config_zet(token, config)
    ingest.lijst_zet(token, laad_lijst(st.session_state.get('eckid', 'lokaal')))
    return _rapport_url(ingest_url), ingest_url


def _knop_html(href, label, rechts=False):
    return f'''<div style="font-family:-apple-system,Segoe UI,Roboto,sans-serif{';text-align:right' if rechts else ''}">
        <a href="{href}"
           style="display:inline-block;padding:9px 18px;background:#1d3f8f;color:#fff;
                  border-radius:9px;text-decoration:none;font-weight:700;font-size:14px;
                  cursor:grab">{label}</a></div>'''


def _installatieblok(href, label, naam):
    st.caption('Sleep deze knop naar je bladwijzerbalk (Ctrl+Shift+B toont hem).')
    st.iframe(_knop_html(href, label), height=62)
    with st.expander('Lukt slepen niet? Maak de bladwijzer handmatig'):
        st.markdown(
            '1. Druk op **Ctrl+Shift+O** (bladwijzerbeheer) → **Nieuwe bladwijzer**.\n'
            f'2. Naam: `{naam}`.\n'
            '3. Plak hieronder gekopieerde tekst in het veld **URL**.')
        st.code(href, language=None)


PRIVACY = ('Het verzuim wordt in **jouw eigen browser** uit Magister gehaald, met jouw '
           'login, en blijft daar: het dashboard wordt in het rapportvenster gemaakt. '
           'Er komt geen verzuim en geen Magister-wachtwoord op de server.')


# ── Teamleider ────────────────────────────────────────────────────────────────
def teamleider_pagina(config):
    st.title('📋 Verzuimsignalering')
    st.info(PRIVACY)

    rapport_url, ingest_url = koppeling(config)
    if not rapport_url:
        st.error('De koppeling met de bladwijzer staat uit (VERZUIM_TL_INGEST_URL is leeg). '
                 'Zonder die koppeling werkt de bladwijzer niet.')
    else:
        st.subheader('Stap 1 — installeer de knop (eenmalig)')
        _installatieblok(bookmarklet.href(rapport_url, ingest_url, _token(), 'tl'),
                         KNOP, KNOP_NAAM)
        st.caption('Had je de knop al van vóór oktober 2026? Vervang hem door deze; de '
                   'oude stuurde het verzuim naar de server en werkt niet meer.')

        st.subheader('Stap 2 — haal het verzuim op')
        st.markdown(
            '1. Ga naar **Magister** en log in.\n'
            f'2. Klik in dat tabblad op de bladwijzer **{KNOP}**. Er opent een nieuw venster.\n'
            '3. Kies daar de periode (standaard de laatste 4 weken) en de klassen of '
            'leerjaren, en klik **Ophalen**.\n'
            '4. Het dashboard verschijnt in dat venster. Daar kun je het ook als '
            'HTML-bestand downloaden.')
        st.caption('Opent er geen venster? Dan houdt de pop-upblokker het tegen: sta '
                   'pop-ups toe voor Magister en klik opnieuw.')

    codes_editor(dashboard.laad_codes())

    if VOORBEELD_PAD.exists():
        st.divider()
        if st.session_state.get('demo'):
            if st.button('Voorbeeld sluiten'):
                st.session_state.pop('demo', None)
                st.rerun()
            voorbeeld = {
                'modus': 'tl',
                'payload': json.loads(VOORBEELD_PAD.read_text(encoding='utf-8')),
                'opties': {'codes': dashboard.laad_codes(), 'mentoren': laad_mentoren(),
                           'config': {'normCrit': config['normCrit'],
                                      'normLaat': config['normLaat']},
                           'patroon': config['patroon'],
                           'logboekInDownload': config['logboekInDownload']},
            }
            st.iframe(rapport.bouw(voorbeeld=voorbeeld), height=1600)
        elif st.button('Voorbeelddata bekijken (verzonnen leerlingen)'):
            st.session_state.demo = True
            st.rerun()


# ── Coördinator: eigen lijst leerlingen ───────────────────────────────────────
def coordinator_pagina(config):
    eckid = st.session_state.get('eckid', 'lokaal')
    rapport_url, ingest_url = koppeling(config)
    ids = laad_lijst(eckid)

    kop, knop = st.columns([3, 1])
    with kop:
        st.title('📋 Mijn leerlingen')
        st.caption(f'{len(ids)} leerlingnummers ingesteld' if ids
                   else 'Nog geen leerlingnummers ingesteld')
    href = (bookmarklet.href(rapport_url, ingest_url, _token(), 'coord')
            if rapport_url else None)
    with knop:
        if href:
            st.iframe(_knop_html(href, KNOP_COORD, rechts=True), height=52)
        else:
            st.caption('Zet VERZUIM_TL_INGEST_URL om de knop te gebruiken.')

    st.info(PRIVACY)

    with st.expander('Hoe je de knop installeert en gebruikt', expanded=not ids):
        st.markdown(
            "1. Zet je bladwijzerbalk aan met **Ctrl+Shift+B**.\n"
            f"2. Sleep de knop **{KNOP_COORD}** hierboven naar die balk.\n"
            "3. Ga naar **Magister** en log in.\n"
            "4. Klik in de balk op die knop. Er opent een venster; klik daar **Ophalen**. "
            "De periode is deze week plus de drie ervoor, en je leerlingnummers haalt hij "
            "hier op.\n"
            "5. Het weekbeeld verschijnt in dat venster.")
        st.caption('Eenmalig. Verandert je lijst hieronder, dan blijft de knop werken — '
                   'die haalt de nummers elke keer opnieuw op.')
        if href:
            with st.expander('Lukt slepen niet? Maak de bladwijzer handmatig'):
                st.markdown(
                    "1. Druk op **Ctrl+Shift+O** → **Nieuwe bladwijzer toevoegen**.\n"
                    f"2. Naam: `{KNOP_COORD}`.\n"
                    "3. Plak de regel hieronder bij **URL**.")
                st.code(href, language=None)

    with st.expander('Leerlingnummers', expanded=not ids):
        tekst = st.text_area(
            'Plak of typ de nummers — komma, spatie of nieuwe regel maakt niet uit',
            '\n'.join(str(i) for i in ids), height=140, key='coord_ids')
        kol1, kol2 = st.columns([1, 4])
        with kol1:
            if st.button('Opslaan', type='primary'):
                nieuw = coordinator.lees_ids(tekst)
                bewaar_lijst(eckid, nieuw)
                if rapport_url:
                    ingest.lijst_zet(_token(), nieuw)
                st.success(f'{len(nieuw)} leerlingnummers opgeslagen.')
                st.rerun()
        with kol2:
            st.caption('Het leerlingnummer staat in de Magister-URL van de leerling: '
                       '…/leerling/**17884**/…')

    if rapport_url:
        _schrijfblok(ids)


def _schrijfblok(ids):
    """Een notitie klaarzetten voor het logboek in Magister.

    De app schrijft zelf niet: ze zet de opdracht klaar en de bladwijzer voert
    hem uit in jouw eigen Magister-sessie, na een bevestiging in het
    rapportvenster. Daar staan ook de namen bij; hier alleen nummers, want de
    namen komen uit Magister en blijven in je browser.
    """
    token = _token()

    # De ontvanger is de enige waarheid over de wachtrij: het token is per
    # gebruiker en overleeft een nieuwe browsersessie, de sessie-state niet.
    wachtrij = ingest.schrijf_lees(token)
    # De uitslag komt één keer uit de ontvanger; in de sessie bewaren tot hij
    # echt getoond is, want een st.rerun() verderop zou hem anders opslokken.
    nieuw = ingest.schrijf_uitslag(token)
    if nieuw:
        st.session_state.schrijf_uitslag = nieuw
    uitslag = st.session_state.get('schrijf_uitslag')
    if not ids and not wachtrij and not uitslag:
        return

    if uitslag:
        gelukt = sum(1 for g in uitslag if g.get('ok'))
        if gelukt:
            st.success(f'{gelukt} notitie(s) in Magister gezet.')
        for g in uitslag:
            if not g.get('ok'):
                st.error(f"Niet gelukt: {g.get('fout') or 'onbekende fout'}")

    with st.expander('Logboeknotitie schrijven in Magister'
                     + (f' — {len(wachtrij)} klaargezet' if wachtrij else '')):
        st.caption('Wat je hier klaarzet, kun je in het rapportvenster in Magister zetten — '
                   'op jouw naam, in het logboek van die leerling. Klik daarvoor de knop '
                   'rechtsboven aan in je Magister-tabblad; het venster laat de namen zien '
                   'en vraagt eerst om bevestiging.')
        melding = st.session_state.pop('schrijf_melding', None)
        if melding:
            st.success(melding)

        if ids:
            kol1, kol2 = st.columns([2, 1])
            with kol1:
                wie = st.selectbox('Leerlingnummer', ids, key='schrijf_wie')
            with kol2:
                soort = st.selectbox('Type', list(LOGBOEK_TYPEN), key='schrijf_type')

            titel = st.text_input('Titel', value=soort, key='schrijf_titel',
                                  help='Bij sommige typen (zoals Mentoraat) bepaalt Magister '
                                       'de titel zelf; dan wordt dit genegeerd.')
            tekst = st.text_area('Tekst', key='schrijf_tekst', height=120,
                                 placeholder='Bijvoorbeeld: 9 sep telefonisch contact met '
                                             'moeder over het verzuim in de eerste lesuren. '
                                             'Afspraak: komende twee weken elke dag om 8.15 '
                                             'melden bij de coördinator.')

            if tekst.strip():
                st.markdown('**Zo komt het in Magister te staan:**')
                st.info(f'**Leerling {wie}** · {soort} · titel "{titel}"\n\n{tekst.strip()}')

            if st.button('Klaarzetten voor Magister', type='primary',
                         disabled=not tekst.strip()):
                regels = ''.join(f'<p>{_veilig(r)}</p>'
                                 for r in tekst.strip().splitlines() if r.strip())
                wachtrij.append({
                    'sleutel': secrets.token_hex(8),
                    'leerlingId': int(wie),
                    'leerlingNaam': f'Leerling {wie}',
                    'typeId': LOGBOEK_TYPEN[soort],
                    'typeNaam': soort,
                    'titel': titel or soort,
                    'inhoud': regels,
                })
                ingest.schrijf_zet(token, wachtrij)
                st.session_state.schrijf_melding = ('Klaargezet. Klik de knop rechtsboven aan '
                                                    'in je Magister-tabblad en bevestig in het '
                                                    'venster dat opent.')
                st.rerun()

        for i, o in enumerate(list(wachtrij)):
            rij, weg = st.columns([6, 1])
            with rij:
                st.write(f"• **{o['leerlingNaam']}** — {o['typeNaam']}: {o['titel']}"
                         + (f"  \n:red[Niet gelukt: {o['fout']}]" if o.get('fout') else ''))
            with weg:
                if st.button('Weg', key=f"weg_{o['sleutel']}"):
                    wachtrij.pop(i)
                    ingest.schrijf_zet(token, wachtrij)
                    st.rerun()

    st.session_state.pop('schrijf_uitslag', None)   # getoond, zonder rerun ertussen


def _veilig(tekst):
    """Tekst geschikt maken voor het HTML-inhoudsveld van Magister."""
    return (tekst.replace('&', '&amp;').replace('<', '&lt;')
                 .replace('>', '&gt;').replace('"', '&quot;'))


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    inloggen()                       # zonder portaal-token komt niemand verder
    config = sidebar()

    pagina = st.radio('Pagina', ['Teamleider', 'Coördinator'],
                      horizontal=True, label_visibility='collapsed', key='pagina')

    if pagina == 'Coördinator':
        coordinator_pagina(config)
    else:
        teamleider_pagina(config)


main()
