"""
maak_voorbeeld.py — schrijft `voorbeeld_school.json`: een verzonnen payload in
precies het formaat dat de bookmarklet oplevert.

Handig om de app te bekijken zonder Magister, en om na een wijziging te
controleren of het dashboard nog klopt. Deterministisch (vaste seed), dus het
bestand verandert alleen als je dit script aanpast.

    python maak_voorbeeld.py
"""

import json
import random
from pathlib import Path
from datetime import date, timedelta

UIT = Path(__file__).parent / 'voorbeeld_school.json'

VOORNAMEN = ['Sem', 'Lotte', 'Daan', 'Julia', 'Levi', 'Sara', 'Noud', 'Fenna', 'Tijn',
             'Nora', 'Bram', 'Evi', 'Luuk', 'Mila', 'Jesse', 'Sanne', 'Thijs', 'Anouk',
             'Mees', 'Roos', 'Jort', 'Fleur', 'Cas', 'Isa', 'Stijn', 'Lieke', 'Ruben',
             'Maud', 'Teun', 'Nina', 'Joep', 'Elin', 'Guus', 'Yara', 'Sven', 'Merel']
ACHTERNAMEN = ['de Vries', 'Jansen', 'van den Berg', 'Bakker', 'Visser', 'Smit',
               'Meijer', 'de Boer', 'Mulder', 'de Groot', 'Bos', 'Vos', 'Peters',
               'Hendriks', 'van Leeuwen', 'Dekker', 'Brouwer', 'de Wit', 'Dijkstra',
               'Smits', 'de Graaf', 'van der Meer', 'Kok', 'Vermeulen', 'van Dijk']
VAKKEN = ['Nederlands', 'Engels', 'Wiskunde B', 'Biologie', 'Scheikunde', 'Economie',
          'Geschiedenis', 'Aardrijkskunde', 'Duits', 'Frans', 'Natuurkunde',
          'Maatschappijleer', 'Bedrijfseconomie', 'Filosofie', 'LO', 'Mentoruur']
# Klas → mentorgroep: de mentor hangt aan een lesgroep (h4mtu1 … h4mtu8),
# niet aan de klas.
KLASSEN = {'H4A': 'h4mtu1', 'H4B': 'h4mtu2', 'H4C': 'h4mtu3',
           'H5A': 'h5mtu1', 'H5B': 'h5mtu2',
           'V4A': 'v4mtu1', 'V4B': 'v4mtu2',
           'V5A': 'v5mtu1', 'V5B': 'v5mtu2', 'V6A': 'v6mtu1'}

BEGIN = date(2026, 8, 31)      # maandag
WEKEN = 4


def lesdagen():
    dagen, d = [], BEGIN
    for _ in range(WEKEN):
        for _ in range(5):
            dagen.append(d)
            d += timedelta(days=1)
        d += timedelta(days=2)
    return dagen


def maak():
    r = random.Random(20260902)
    dagen = lesdagen()
    students, entries, sid = [], {}, 1

    for klas, mentorgroep in KLASSEN.items():
        for _ in range(r.randint(7, 11)):
            profiel = r.choices(['hoog', 'midden', 'laag'], [0.07, 0.18, 0.75])[0]
            kans_ong  = {'hoog': 0.34, 'midden': 0.10, 'laag': 0.02}[profiel]
            kans_laat = {'hoog': 0.24, 'midden': 0.14, 'laag': 0.05}[profiel]

            rijen = []
            for dag in dagen:
                if r.random() < kans_ong:
                    start = r.randint(1, 6)
                    for u in range(r.randint(1, 3)):
                        rijen.append(_entry(r, dag, start + u,
                                            'A' if r.random() < 0.6 else 'SP'))
                if r.random() < kans_laat:
                    rijen.append(_entry(r, dag, r.randint(1, 3), 'TA'))
                if r.random() < 0.035:                      # ziekmelding, hele dag
                    for u in range(r.randint(4, 7)):
                        rijen.append(_entry(r, dag, u + 1, 'ZI'))
                if r.random() < 0.02:
                    rijen.append(_entry(r, dag, r.randint(1, 8),
                                        'AO' if r.random() < 0.7 else 'BV'))

            students.append({
                'id': sid,
                'roepnaam': r.choice(VOORNAMEN),
                'achternaam': r.choice(ACHTERNAMEN),
                'lesgroepen': [mentorgroep, klas.lower() + 'ne1'],
                'studies': [klas[:2]],
                'klassen': [klas],
            })
            entries[str(sid)] = rijen
            sid += 1

    return {
        'period': {'begin': BEGIN.isoformat(),
                   'einde': (BEGIN + timedelta(days=WEKEN * 7 - 3)).isoformat()},
        'scope': 'H4,H5,V4,V5,V6',
        'students': students,
        'own_ids': [s['id'] for s in students],
        'entries': entries,
    }


def _entry(r, dag, uur, code):
    return {
        'date': dag.isoformat(),
        'time': f'{7 + uur:02d}:30',
        'code': code,
        'period': uur,
        'subject': r.choice(VAKKEN),
    }


if __name__ == '__main__':
    payload = maak()
    UIT.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding='utf-8')
    n = sum(len(v) for v in payload['entries'].values())
    print(f'{UIT.name}: {len(payload["students"])} leerlingen, {n} registraties')
