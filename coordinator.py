"""
coordinator.py — weekbeeld voor een coördinator met een eigen lijst leerlingen.

Zelfde data als het teamleider-dashboard (zie dashboard.verwerk), maar een
andere vraag: niet "wie springt eruit in deze afdeling", maar "hoe ging deze
week bij mijn twintig". Daarom staat de huidige week uitgeschreven per lesdag
en staan de weken ervoor als streepjes.

De opmaak leunt op template.html: daar staan de kleuren en de basisstijlen, en
die willen we niet twee keer onderhouden.
"""

import re
import json
from pathlib import Path

import dashboard

HIER = Path(__file__).parent


def _basis_stijl():
    """Alles tot en met </head> uit het teamleider-sjabloon: tokens en basis."""
    sjabloon = (HIER / 'template.html').read_text(encoding='utf-8')
    return sjabloon[:sjabloon.index('</head>')]


EIGEN_STIJL = """
<style>
.kop-rij { display: flex; align-items: flex-start; justify-content: space-between;
  gap: 16px; flex-wrap: wrap; }
#weeklabel { font-weight: 600; color: var(--ink); }

.kaarten { display: flex; flex-direction: column; gap: 10px; }
.kaart { background: var(--card); border: 1px solid var(--lijn); border-radius: var(--radius);
  padding: 12px 14px; box-shadow: var(--shadow); }
.kaart.rustig { opacity: .72; }
.kaart-kop { display: flex; align-items: baseline; justify-content: space-between;
  gap: 12px; flex-wrap: wrap; margin-bottom: 9px; }
.kaart .wie { padding: 0; }
.kaart .naam { display: block; font-weight: 600; font-size: .92rem; }
.kaart .sub { display: block; font-size: .74rem; color: var(--muted); margin-top: 1px; }
.wcijfers { font-size: .78rem; color: var(--ink-2); white-space: nowrap; }
.wcijfers b { color: var(--ink); }
.wrust { font-size: .78rem; color: var(--muted); font-style: italic; }

/* De week zelf: vijf lesdagen naast elkaar */
.week { display: grid; grid-template-columns: repeat(5, 1fr); gap: 6px; }
.wdag { border: 1px solid var(--lijn); border-radius: 8px; padding: 6px 7px 8px;
  background: var(--card-sunk); min-height: 58px; }
.wdag.ong  { border-color: color-mix(in srgb, var(--s-ongeoorloofd) 55%, transparent);
             background: color-mix(in srgb, var(--s-ongeoorloofd) 8%, var(--card)); }
.wdag.laat { border-color: color-mix(in srgb, var(--s-telaat) 55%, transparent);
             background: color-mix(in srgb, var(--s-telaat) 8%, var(--card)); }
.wdag.geo  { border-color: color-mix(in srgb, var(--s-geoorloofd) 45%, transparent);
             background: color-mix(in srgb, var(--s-geoorloofd) 7%, var(--card)); }
.wdag-kop { display: block; font-size: .68rem; font-weight: 600; color: var(--muted);
  text-transform: uppercase; letter-spacing: .05em; margin-bottom: 4px; }
.wdag-body { display: flex; flex-wrap: wrap; gap: 3px; }
.wchip { font-size: .7rem; font-weight: 700; padding: 1px 5px; border-radius: 5px;
  background: var(--card); box-shadow: inset 0 0 0 1px var(--lijn); color: var(--ink-2); }
.wchip.ong  { background: color-mix(in srgb, var(--s-ongeoorloofd) 22%, var(--card));
              color: var(--s-ongeoorloofd); box-shadow: none; }
.wchip.laat { background: color-mix(in srgb, var(--s-telaat) 24%, var(--card));
              color: #8a6100; box-shadow: none; }
.wchip.geo  { background: color-mix(in srgb, var(--s-geoorloofd) 18%, var(--card));
              color: var(--s-geoorloofd); box-shadow: none; }
.wleeg { color: var(--line-soft); }

.kaart-voet { display: flex; align-items: center; justify-content: space-between;
  gap: 12px; flex-wrap: wrap; margin-top: 9px; }
.eerder { display: inline-flex; align-items: center; gap: 6px; }
.eerder-kop { font-size: .68rem; color: var(--muted); text-transform: uppercase;
  letter-spacing: .05em; }
.totaal { font-size: .72rem; color: var(--muted); font-variant-numeric: tabular-nums; }
.kaart .logboek { margin: 8px 0 0; }
@media (max-width: 760px) { .week { grid-template-columns: repeat(3, 1fr); } }
</style>
</head>
<body>
"""


def bouw_html(payload, codes=None, config=None, mentoren=None,
              patroon=dashboard.MENTORGROEP_PATROON, met_logboek=True, bron=''):
    """Weekoverzicht als zelfstandig HTML-bestand."""
    codes = codes if codes is not None else dashboard.laad_codes()
    data, info = dashboard.verwerk(payload, codes, config, mentoren, patroon, met_logboek)

    periode = data['periode']
    lichaam = f"""
<div class="wrap">
  <div class="masthead kop-rij">
    <div>
      <h1>Mijn leerlingen</h1>
      <p>Hoe ging deze week, en wat liep er in de weken ervoor?</p>
    </div>
    <div class="meta">
      <b id="weeklabel"></b>
      {info['aantal_leerlingen']} leerlingen · {periode['label']}
    </div>
  </div>

  <div class="tiles" id="tiles"></div>

  <div class="kaarten" id="kaarten"></div>

  <footer>
    <b>Hoe je dit leest.</b> Bovenaan staat de leerling waar deze week het meest
    speelde. De vijf vakken zijn de lesdagen van deze week met de codes die er
    staan; de streepjes daaronder zijn de weken ervoor, één blokje per lesdag.
    Ziek en verlof staan er als context bij en tellen niet als ongeoorloofd.
    {bron}
  </footer>
</div>

<div id="tip" role="status" aria-live="polite"></div>

<script>window.DATA = {json.dumps(data, ensure_ascii=False).replace('<', chr(92) + 'u003c')};</script>
<script>
{(HIER / 'coordinator.js').read_text(encoding='utf-8')}
</script>
</body>
</html>
"""
    return _basis_stijl() + EIGEN_STIJL + lichaam, info


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
