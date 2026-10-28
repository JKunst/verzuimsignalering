"""
dashboard.py — de codetabel en standaardinstellingen van het dashboard.

Het dashboard zelf wordt niet meer op de server gemaakt: dat doet `verwerk.js`
in het rapportvenster (zie rapport.py), zodat het verzuim de browser van de
gebruiker niet verlaat. Hier staat alleen nog wat de app beheert en via de
bladwijzer aan het venster meegeeft.
"""

import json
from pathlib import Path

HIER = Path(__file__).parent

# Waaraan je de mentorgroep herkent in de lesgroepnamen: h4mtu1 … h4mtu8.
# Moet gelijk zijn aan MENTORGROEP_PATROON in verwerk.js.
MENTORGROEP_PATROON = 'mtu'

STANDAARD_CONFIG = {
    'normCrit': 16,   # uren ongeoorloofd → het label 'melden' (leerplicht)
    'normLaat': 6,    # keer te laat → het signaal 'vaak te laat'
}


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
