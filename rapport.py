"""
rapport.py — zet het rapportvenster (rapport.html) in elkaar.

Het venster rekent en tekent het dashboard in de browser van de gebruiker; de
server levert alleen de code. Bron is `rapport_bron.html`; daarin komen
verwerk.js en de bestanden van het dashboard (template.html, render.js,
coordinator.js, coordinator.css). Zo is er één plek voor elk stuk en loopt het
venster nooit achter op de rest.

De ontvanger (ingest.py) serveert het resultaat op <VERZUIM_TL_INGEST_URL>/rapport.html.
"""

import re
import json
from pathlib import Path

HIER = Path(__file__).parent


def _lees(naam):
    return (HIER / naam).read_text(encoding='utf-8')


def _js_waarde(obj):
    """JSON die veilig in een <script>-blok staat: geen '</script>' of '<!--'."""
    return (json.dumps(obj, ensure_ascii=False)
            .replace('<', '\\u003c')
            .replace('\u2028', '\\u2028').replace('\u2029', '\\u2029'))


def bouw(voorbeeld=None):
    """De pagina als tekst.

    `voorbeeld` = {'payload': ..., 'opties': {codes, mentoren, config, patroon},
    'modus': 'tl'} toont meteen een dashboard met verzonnen data, zonder
    Magister. Dat gebruikt de app voor de knop Voorbeelddata bekijken.
    """
    # Geen Google Fonts: de CSP blokkeert ze toch, en zo doet het venster (en
    # het gedownloade bestand) ook geen poging om iets van buiten te laden.
    template = re.sub(r'^<link [^>]*fonts\.(googleapis|gstatic)\.com[^>]*>\n', '',
                      _lees('template.html'), flags=re.M)
    bronnen = {
        'template':       template,
        'renderJs':       _lees('render.js'),
        'coordinatorJs':  _lees('coordinator.js'),
        'coordinatorCss': _lees('coordinator.css'),
    }
    vervang = {
        '/*__BRONNEN__*/':    _js_waarde(bronnen),
        '/*__VOORBEELD__*/':  _js_waarde(voorbeeld),
        # verwerk.js is code, geen data; het mag alleen geen </script> bevatten.
        '/*__VERWERK_JS__*/': _lees('verwerk.js').replace('</script', '<\\/script'),
    }
    pagina = _lees('rapport_bron.html')
    for plek, waarde in vervang.items():
        if pagina.count(plek) != 1:
            raise RuntimeError(f'Plekhouder {plek} niet precies één keer in rapport_bron.html')
        pagina = pagina.replace(plek, waarde)
    return pagina


if __name__ == '__main__':
    # Lokaal bekijken: python rapport.py > rapport.html
    print(bouw())
