"""
app.py — Verzuimsignalering voor teamleiders.

Flow:
0. De gebruiker komt binnen via het portaal, met een SSO-token in de URL.
1. De teamleider sleept hier eenmalig een bookmarklet naar de bladwijzerbalk.
2. In het ingelogde Magister-tabblad klikt hij die aan: de leerlingen van zijn
   afdeling + hun verzuim worden daar opgehaald (met zijn eigen sessie).
3. De data komt hier binnen — direct via de ontvanger, of als geüpload bestand.
4. De app rendert het dashboard en kan het als los HTML-bestand meegeven.

Er staat geen Magister-wachtwoord op de server en er draait geen browser op de
server. Zie README.md voor de bookmarklet-instructies.

Start met:  streamlit run app.py
"""

import os
import json
import time
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
import bookmarklet
import dashboard

HIER          = Path(__file__).parent
MENTOREN_PAD  = HIER / 'mentoren.json'
SECRET_PAD    = HIER / '.secret'
VOORBEELD_PAD = HIER / 'voorbeeld_school.json'

# Zelfde SSO-token als de andere apps van het portaal.
JWT_SECRET    = os.environ.get('JWT_SECRET', 'verander-dit-naar-een-lang-geheim')
JWT_ALGORITHM = 'HS256'
PORTAAL_URL   = os.environ.get('PORTAAL_URL', 'https://bovenbouwsucces.nl')
TOEGESTANE_ROLLEN = ('docent', 'beheerder')

# Eigen naam, zodat de knop niet te verwarren is met de bookmarklet van de
# mentoruur-app (die heet '📋 Verzuim ophalen' en pakt één mentorgroep).
KNOP_NAAM      = 'Verzuim teamleider'
KNOP           = f'📋 {KNOP_NAAM}'
KNOP_DOWNLOAD  = f'📋 {KNOP_NAAM} (bestand)'

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
    """Ontvangsttoken van de bookmarklet — per gebruiker.

    Het eckid zit erin, zodat de payload van de één niet in de sessie van de
    ander kan belanden: de ontvanger geeft een binnengekomen bestand alleen aan
    wie hetzelfde token gebruikt.
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

    _verwerk_sso_token()
    if st.session_state.get('eckid'):
        return

    st.title('📋 Verzuimsignalering')
    st.warning(f'Log in via [het portaal]({PORTAAL_URL}) en klik daar de tegel '
               'van deze app aan.')
    st.stop()


def _ingest_config():
    """(url, poort) van de ontvanger. Leeg zetten schakelt de directe flow uit.

    Eigen namen en een eigen poort (8766), want de mentoruur-app gebruikt
    VERZUIM_INGEST_URL/PORT en poort 8765. Draaien ze op dezelfde server, dan
    zouden ze elkaars ontvanger overnemen.

    Lokaal werkt http://localhost:8766 gewoon vanaf de https-pagina van
    Magister: browsers behandelen localhost als een veilige origin.
    """
    url  = os.environ.get('VERZUIM_TL_INGEST_URL', 'http://localhost:8766').strip()
    port = int(os.environ.get('VERZUIM_TL_INGEST_PORT', '8766'))
    return (url or None), port


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


def _valideer(payload):
    if not isinstance(payload, dict):
        raise ValueError('Onverwacht bestandsformaat.')
    if 'students' not in payload or 'entries' not in payload:
        raise ValueError('Dit lijkt geen verzuimbestand (velden ontbreken).')


# ── Sidebar ───────────────────────────────────────────────────────────────────
def sidebar():
    st.sidebar.header('Instellingen')
    naam = st.session_state.get('naam')
    if naam:
        st.sidebar.caption(f'Ingelogd als {naam}')

    st.sidebar.subheader('Signaalgrenzen')
    config = {
        'normCrit': st.sidebar.number_input(
            'Meldplicht vanaf (uren ongeoorloofd)', 1, 100, 16, key='normCrit'),
        'normWarn': st.sidebar.number_input(
            'Nadert de grens vanaf (uren)', 1, 100, 10, key='normWarn'),
        'normLaat': st.sidebar.number_input(
            'Vaak te laat vanaf (keer)', 1, 100, 6, key='normLaat'),
    }

    st.sidebar.subheader('Standaard selectie')
    st.sidebar.text_input(
        'Klassen of leerjaren', key='scope',
        help="Wordt voorgesteld in de bookmarklet, bijvoorbeeld 'H4,H5'. "
             'Leeg = alles wat je in Magister mag zien.')

    st.sidebar.subheader('Mentorgroepen')
    config['patroon'] = st.sidebar.text_input(
        'Mentorgroep herkennen aan', dashboard.MENTORGROEP_PATROON, key='patroon',
        help="De mentorgroep is een lesgroep, niet de klas: h4mtu1 t/m h4mtu8. "
             "Dit stukje tekst moet in de lesgroepnaam zitten.")

    st.sidebar.subheader('Logboek')
    st.sidebar.checkbox(
        'Logboektekst in de download', value=False, key='logboek_in_download',
        help='In de app zie je het logboek altijd. Het losse HTML-bestand komt '
             'buiten de app terecht; daar laten we die teksten standaard uit.')

    huidig = laad_mentoren()
    # Groepen uit de geladen data erbij, zodat je alleen de namen hoeft te typen.
    gevonden = (dashboard.mentorgroepen_van(st.session_state.payload, config['patroon'])
                if 'payload' in st.session_state else [])
    regels = [f'{g} = {huidig.get(g, "")}'.rstrip()
              for g in sorted(set(gevonden) | set(huidig))]
    tekst = st.sidebar.text_area(
        'Eén per regel: mentorgroep = mentor', '\n'.join(regels), height=160,
        help='Magister geeft de mentor niet mee bij het zoeken naar leerlingen. '
             'Wat je hier invult verschijnt bij de leerling en in het overzicht '
             'per mentorgroep.')
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


def codes_editor(codes, gebruikt=None, openen=False):
    """Codes indelen als ongeoorloofd / te laat / geoorloofd."""
    with st.expander('Verzuimcodes indelen', expanded=openen):
        st.caption('De indeling bepaalt de urentelling. Codes die je nog niet hebt '
                   'nagelopen staan op geoorloofd, zodat ze de norm niet opblazen.')
        rijen = [{'code': c, 'naam': v.get('naam', c), 'soort': v.get('soort', 'geo'),
                  'komt voor': (gebruikt or {}).get(c, 0)}
                 for c, v in codes.items()]
        for c, n in (gebruikt or {}).items():
            if c not in codes:
                rijen.append({'code': c, 'naam': c, 'soort': 'geo', 'komt voor': n})
        rijen.sort(key=lambda r: (-r['komt voor'], r['code']))   # gebruikte codes eerst

        bewerkt = st.data_editor(
            rijen, hide_index=True, width='stretch', key='codes_editor',
            column_config={
                'code': st.column_config.TextColumn('Code', disabled=True, width='small'),
                'naam': st.column_config.TextColumn('Betekenis'),
                'soort': st.column_config.SelectboxColumn(
                    'Telt als', options=['ong', 'laat', 'geo'], required=True,
                    help='ong = ongeoorloofd (telt in de norm), laat = te laat, '
                         'geo = geoorloofd'),
                'komt voor': st.column_config.NumberColumn(
                    'In deze data', disabled=True, width='small'),
            })
        if st.button('Codes opslaan'):
            nieuw = {r['code']: {'naam': r['naam'], 'soort': r['soort']}
                     for r in bewerkt if r.get('code')}
            dashboard.bewaar_codes(nieuw)
            st.success('Codes opgeslagen.')
            st.rerun()


# ── Intake ────────────────────────────────────────────────────────────────────
def _installatieblok(href, label):
    st.caption('Sleep deze knop naar je bladwijzerbalk (Ctrl+Shift+B toont hem).')
    st.iframe(
        f'''<div style="font-family:-apple-system,Segoe UI,Roboto,sans-serif">
        <a href="{href}"
           style="display:inline-block;padding:9px 18px;background:#1d3f8f;color:#fff;
                  border-radius:9px;text-decoration:none;font-weight:700;font-size:14px;
                  cursor:grab">{label}</a>
        </div>''',
        height=62,
    )
    with st.expander('Lukt slepen niet? Maak de bladwijzer handmatig'):
        st.markdown(
            '1. Druk op **Ctrl+Shift+O** (bladwijzerbeheer) → **Nieuwe bladwijzer**.\n'
            f'2. Naam: `{KNOP_NAAM}`.\n'
            '3. Plak hieronder gekopieerde tekst in het veld **URL**.')
        st.code(href, language=None)


def _uploadblok():
    key = f"upload_{st.session_state.get('upload_nonce', 0)}"
    up = st.file_uploader('Verzuimbestand (JSON)', type=['json'], key=key)
    if up is not None and st.button('Dashboard maken', type='primary'):
        try:
            payload = json.loads(up.getvalue().decode('utf-8'))
            _valideer(payload)
        except Exception as ex:
            st.error(f'Kon het bestand niet verwerken: {ex}')
        else:
            st.session_state.payload = payload
            st.rerun()


def _stappen(scope):
    selectie = f'**{scope}**' if scope else 'de klassen die je invult'
    st.markdown(
        '1. Ga naar **Magister** en log in (in hetzelfde tabblad).\n'
        f'2. Klik in je bladwijzerbalk op **{KNOP}**.\n'
        '3. Vul begin- en einddatum in (standaard de laatste 4 weken).\n'
        f'4. Vul bij de selectie {selectie} in.\n'
        '5. Wacht tot de melding komt — de titel van het tabblad toont de voortgang.')


def intake():
    scope = st.session_state.get('scope', '')
    ingest_url, port = _ingest_config()

    st.info('Het verzuim wordt in **jouw eigen browser** uit Magister gehaald, met jouw '
            'login. Er komt geen Magister-wachtwoord op de server; alleen het resultaat '
            'komt hier binnen en wordt niet opgeslagen.')

    if ingest_url:
        ingest.ensure_server(port)
        token = _token()

        # Al iets binnengekomen?
        payload = ingest.take(token)
        if payload:
            try:
                _valideer(payload)
            except Exception as ex:
                st.error(f'Ontvangen data ongeldig: {ex}')
            else:
                st.session_state.payload = payload
                st.session_state.pop('wachten', None)
                st.rerun()

        st.subheader('Stap 1 — installeer de knop (eenmalig)')
        _installatieblok(bookmarklet.post_href(ingest_url, token, scope),
                         KNOP)

        st.subheader('Stap 2 — haal het verzuim op')
        _stappen(scope)

        if st.session_state.get('wachten'):
            st.info('⏳ Wachten op je verzuim uit Magister…')
            if st.button('Stoppen met wachten'):
                st.session_state.pop('wachten', None)
                st.rerun()
            time.sleep(2)
            st.rerun()
        elif st.button('Ik heb geklikt — wacht op de data', type='primary'):
            st.session_state.wachten = True
            st.rerun()

        with st.expander('Liever via een bestand? (download → upload)'):
            st.caption('Gebruik deze knop in plaats van de bovenste; die downloadt een bestand.')
            _installatieblok(bookmarklet.download_href(scope), KNOP_DOWNLOAD)
            _uploadblok()
    else:
        st.subheader('Stap 1 — installeer de knop (eenmalig)')
        _installatieblok(bookmarklet.download_href(scope), KNOP_DOWNLOAD)
        st.subheader('Stap 2 — haal het verzuim op')
        _stappen(scope)
        st.subheader('Stap 3 — upload het bestand')
        _uploadblok()

    if VOORBEELD_PAD.exists():
        st.divider()
        if st.button('Voorbeelddata bekijken (verzonnen leerlingen)'):
            st.session_state.payload = json.loads(
                VOORBEELD_PAD.read_text(encoding='utf-8'))
            st.session_state.demo = True
            st.rerun()


# ── Dashboard ─────────────────────────────────────────────────────────────────
def rapport(payload, config):
    codes    = dashboard.laad_codes()
    mentoren = laad_mentoren()
    demo     = st.session_state.get('demo', False)

    config  = dict(config)
    patroon = config.pop('patroon', dashboard.MENTORGROEP_PATROON)

    html, info = dashboard.bouw_html(
        payload, codes=codes, config=config, mentoren=mentoren, patroon=patroon,
        banner=dashboard.demo_banner() if demo else '')

    # Het downloadbestand kan zonder de logboekteksten; die zijn gevoelig en
    # verlaten met dat bestand de app.
    if st.session_state.get('logboek_in_download') or not info['logboek_aantal']:
        download_html = html
    else:
        download_html, _ = dashboard.bouw_html(
            payload, codes=codes, config=config, mentoren=mentoren, patroon=patroon,
            banner=dashboard.demo_banner() if demo else '', met_logboek=False)

    kop, knop1, knop2 = st.columns([4, 1, 1])
    with kop:
        st.success(f"{info['aantal_leerlingen']} leerlingen · "
                   f"{info['aantal_registraties']} registraties · "
                   f"{info['weken']} weken"
                   + (f" · selectie {info['scope']}" if info['scope'] else ''))
    with knop1:
        st.download_button('Download HTML', data=download_html,
                           file_name=f"verzuimsignalering_{payload.get('period', {}).get('einde', '')}.html",
                           mime='text/html', width='stretch')
    with knop2:
        if st.button('Nieuwe data', width='stretch'):
            for sleutel in ('payload', 'demo', 'wachten'):
                st.session_state.pop(sleutel, None)
            st.session_state.upload_nonce = st.session_state.get('upload_nonce', 0) + 1
            st.rerun()

    if info['verzuim_fouten']:
        st.error(f"Van {info['verzuim_fouten']} leerlingen is het verzuim niet "
                 'opgehaald: Magister beperkte het aantal verzoeken. Die staan hier '
                 'dus ten onrechte op nul. Haal opnieuw op met een kortere periode '
                 'of een kleinere selectie.')

    if info['logboek_aantal']:
        extra = ('' if st.session_state.get('logboek_in_download')
                 else ' De teksten blijven uit het downloadbestand.')
        st.caption(f"📓 {info['logboek_aantal']} logboekformulieren opgehaald "
                   f"(bron: {info['logboek_bron'] or 'onbekend'}).{extra}")
    elif info['logboek_bron'] == 'niet gevonden':
        st.warning('De bookmarklet kon geen lijst-URL voor logboekformulieren vinden.')
        if info['logboek_diag']:
            with st.expander('Wat de geprobeerde URLs teruggaven'):
                st.code('\n'.join(info['logboek_diag']), language=None)
                st.caption('Stuur dit door, dan weten we welke URL het wel moet zijn.')

    if not info['mentorgroepen']:
        st.warning(f"Geen mentorgroepen gevonden met '{patroon}' in de lesgroepnaam — "
                   'het overzicht valt terug op de klas. Pas de herkenning links aan '
                   'als de mentorgroepen bij jullie anders heten.')
    elif info['zonder_mentorgroep']:
        st.info(f"{info['zonder_mentorgroep']} leerlingen zitten in geen enkele "
                f"mentorgroep met '{patroon}'; die staan onder hun klas.")

    if info['onbekende_codes']:
        st.warning('Onbekende verzuimcodes in deze data: **'
                   + ', '.join(info['onbekende_codes'])
                   + '** — die tellen nu als geoorloofd. Deel ze hieronder in.')
    elif info['te_controleren_codes']:
        st.warning('Nog niet nagelopen codes in deze data: **'
                   + ', '.join(info['te_controleren_codes'])
                   + '** — die tellen nu als geoorloofd.')

    codes_editor(codes, info['code_telling'],
                 openen=bool(info['onbekende_codes'] or info['te_controleren_codes']))

    st.iframe(html, height=1500)


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    inloggen()                       # zonder portaal-token komt niemand verder
    config = sidebar()
    st.title('📋 Verzuimsignalering')

    if 'payload' in st.session_state:
        rapport(st.session_state.payload, config)
    else:
        intake()


main()
