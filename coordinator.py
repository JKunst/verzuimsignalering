"""
coordinator.py — hulpjes voor de coördinatorpagina (een eigen lijst leerlingen).

Het weekbeeld zelf maakt het rapportvenster in de browser (verwerk.js +
coordinator.js + coordinator.css); hier staat alleen wat de app nodig heeft.
"""

import re


def lees_ids(tekst):
    """Leerlingnummers uit een vrij ingetypte lijst halen.

    Alles wat geen cijfer is geldt als scheidingsteken, zodat plakken uit
    Excel, een mail of een kommalijst allemaal werkt.
    """
    gezien, uit = set(), []
    for stuk in re.findall(r'\d+', tekst or ''):
        nummer = int(stuk)
        if nummer not in gezien:
            gezien.add(nummer)
            uit.append(nummer)
    return uit
