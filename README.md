# Verzuimsignalering

Streamlit-app voor teamleiders: haalt het verzuim van een hele afdeling uit
Magister en maakt daar een signaleringsdashboard van — wie zit tegen de
meldgrens aan, wie komt structureel te laat, en met welke mentor moet dat
besproken worden.

De mentorvariant (één mentorgroep) zit in de mentoruur-app; deze app is de
teamleiderskant en draait los. Het dashboard is de uitgewerkte versie van
`mentoruur/demo_teamleider_dashboard.html`, nu met echte data.

## Hoe het werkt

1. Je sleept eenmalig een **bookmarklet** naar je bladwijzerbalk.
2. Je klikt die aan in je eigen, ingelogde Magister-tabblad. Daar worden de
   leerlingen van je afdeling en hun verzuim opgehaald — met jouw sessie,
   same-origin, dus zonder CORS-gedoe.
3. De data komt in de app binnen (direct, of als bestand dat je uploadt).
4. De app rendert het dashboard en kan het als los HTML-bestand meegeven, om te
   printen of mee te nemen naar een overleg.

Er draait dus **geen browser op de server** en er komt **geen Magister-wachtwoord
op de server**; alleen het opgehaalde resultaat, en dat wordt niet opgeslagen.

## Starten

```bash
pip install -r requirements.txt
streamlit run app.py
```

De app draait op <http://localhost:8501>, de ontvanger van de bookmarklet op
poort **8766** (de mentoruur-app gebruikt 8765). Vanaf de https-pagina van
Magister posten naar `http://localhost` mag: browsers zien localhost als een
veilige origin.

Zonder Magister kijken? Klik onderaan op **Voorbeelddata bekijken** — dat is
`voorbeeld_school.json` met 90 verzonnen leerlingen (opnieuw te maken met
`python maak_voorbeeld.py`).

## De bookmarklet

### Installeren (eenmalig)

**Slepen** — de makkelijke manier: zet je bladwijzerbalk aan met **Ctrl+Shift+B**
en sleep de blauwe knop **📋 Verzuim teamleider** uit de app erheen.

> De knop heet bewust anders dan de **📋 Verzuim ophalen** uit de mentoruur-app.
> Die twee kunnen naast elkaar in de balk staan: de mentorknop haalt één
> mentorgroep op, deze een hele afdeling. Ook de voortgang in de tabbladtitel
> verschilt (`Verzuim TL 60/99…`).

**Handmatig** — als slepen niet lukt (of de balk uitstaat):

1. Klap in de app **Lukt slepen niet? Maak de bladwijzer handmatig** open en
   kopieer de hele regel code (die begint met `javascript:`).
2. Druk op **Ctrl+Shift+O** → **Nieuwe bladwijzer toevoegen**.
3. Naam: `Verzuim teamleider`. Plak bij **URL** de gekopieerde regel.
4. Opslaan in de map **Bladwijzerbalk**.

> Firefox en Safari knippen een geplakte `javascript:`-URL soms weg. Plak dan
> eerst in Kladblok, kopieer opnieuw, en plak dat in het URL-veld.

De bladwijzer bevat je persoonlijke token en blijft geldig zolang `.secret`
blijft staan. Verwijder je dat bestand, dan moet de knop opnieuw geïnstalleerd
worden.

### Gebruiken

1. Ga naar Magister en log in.
2. Klik in de bladwijzerbalk op **📋 Verzuim teamleider**.
3. Vul **begindatum** en **einddatum** in (standaard de laatste 4 weken, vanaf
   een maandag).
4. Vul in welke **klassen of leerjaren** je wilt: `H4,H5` pakt alle klassen die
   daarmee beginnen, `H4A` alleen die klas. Leeg laten = alles wat je in
   Magister mag zien — dat kan bij een grote school lang duren.
5. De titel van het tabblad toont de voortgang (`Verzuim TL 120/240...`). Bij meer
   dan 150 leerlingen vraagt de bookmarklet eerst om bevestiging.
6. Als het klaar is: terug naar het tabblad van de app. Daar staat het
   dashboard (of, bij de downloadvariant, upload je het bestand).

Het ophalen kost één verzoek per leerling, twintig tegelijk; reken op ongeveer
een halve seconde per twintig leerlingen. Daarom wordt er eerst gefilterd en pas
daarna verzuim opgehaald.

## Het dashboard lezen

- **Meldplicht bereikt** — vanaf 16 uur ongeoorloofd binnen de gekozen periode.
- **Nadert de grens** — 10 t/m 15 uur.
- **Vaak te laat** — 6 keer of vaker; telt niet mee in de urennorm.
- Ziek, arts en bijzonder verlof zijn geoorloofd en staan er als context bij.

Die grenzen stel je links in de zijbalk in; ze gelden meteen voor het dashboard
en voor de gedownloade HTML.

De tabs zijn afdeling + leerjaar (`Havo 4`, `Vwo 5`), afgeleid van de
mentorgroep (`h4mtu1` → Havo 4) en anders van de klas. Klik op een signaal om de lijst daarop te filteren; klik nog eens
om het filter uit te zetten.

## Eerst controleren: de verzuimcodes

De urentelling staat of valt met de vraag welke code als ongeoorloofd telt.
`codes.json` bevat een eerste indeling: **A** en **SP** tellen als
ongeoorloofd, **TA** als te laat, de rest als geoorloofd. Codes waarvan de
betekenis bij ons niet vaststaat (`L`, `SI`, `BO`, `BR`, `SA`) staan bewust op
geoorloofd, zodat ze de cijfers niet opblazen — de app waarschuwt als zo'n code
in je data voorkomt.

Loop dat één keer na in **Verzuimcodes indelen**: vul de betekenis in, zet de
juiste soort, en klik op **Codes opslaan**. Dat schrijft `codes.json` en geldt
daarna voor iedereen die de app gebruikt.

## Mentorgroepen en mentoren

De mentor hangt niet aan de klas maar aan een **lesgroep**: `h4mtu1` t/m
`h4mtu8`. De app zoekt die lesgroep op bij elke leerling — herkend aan het
stukje tekst dat links in de zijbalk staat (standaard `mtu`). Heten de
mentorgroepen bij jullie anders, pas dat daar aan; het dashboard rekent meteen
opnieuw.

De mentorgroep bepaalt drie dingen:

- het paneel **Ongeoorloofd per mentorgroep** (welke mentor moet je spreken);
- de tab waar een leerling onder valt (`h4mtu1` → Havo 4);
- de regel onder de naam van de leerling: `H4A · h4mtu1 · mentor T. Vermeer`.

Magister geeft de mentornaam niet mee. Vul die in de zijbalk in als
`h4mtu1 = T. Vermeer` — zodra er data geladen is, staan de gevonden
mentorgroepen daar al klaar en hoef je alleen de namen te typen. **Mentoren
opslaan** schrijft `mentoren.json` (niet in git).

Zit een leerling in geen enkele mentorgroep, dan valt die terug op zijn klas;
de app meldt hoeveel dat er zijn.

## Bestanden

| Bestand | Wat het doet |
|---|---|
| `app.py` | de Streamlit-app: instellingen, bookmarklet-installatie, dashboard |
| `bookmarklet.py` | genereert de bookmarklet (downloadvariant en directe variant) |
| `ingest.py` | ontvanger op poort 8766 waar de bookmarklet naartoe post |
| `dashboard.py` | rekent de payload om en bouwt het HTML-dashboard |
| `template.html` | de opmaak van het dashboard (styling + lege panelen) |
| `render.js` | tekent de panelen uit de data; draait in de pagina zelf |
| `codes.json` | verzuimcodes → betekenis + soort (ongeoorloofd/te laat/geoorloofd) |
| `maak_voorbeeld.py` | schrijft `voorbeeld_school.json` met verzonnen data |

Alles wat geteld wordt, gebeurt in `dashboard.py`; `render.js` tekent alleen.
Zo geven de app en het gedownloade HTML-bestand altijd dezelfde cijfers.

## Op een server draaien

De directe flow heeft een adres nodig dat vanaf magister.net bereikbaar is:

```bash
export VERZUIM_TL_INGEST_URL="https://verzuim-tl.example.nl/ingest"  # reverse proxy → poort 8766
export VERZUIM_TL_INGEST_PORT=8766
export VERZUIM_TL_SECRET="een-lang-geheim"                           # anders wordt .secret gebruikt
```

Zet `VERZUIM_TL_INGEST_URL` leeg om alleen de download/upload-variant aan te
bieden; die werkt altijd en heeft geen extra route nodig.

### Naast de mentoruur-app op dezelfde server

Alle namen zijn bewust anders dan die van de mentoruur-app, want die zou er
anders overheen lopen:

| | mentoruur-app | deze app |
|---|---|---|
| Ontvanger-URL | `VERZUIM_INGEST_URL` | `VERZUIM_TL_INGEST_URL` |
| Poort | `VERZUIM_INGEST_PORT` (8765) | `VERZUIM_TL_INGEST_PORT` (8766) |
| Geheim | `JWT_SECRET` (ook voor SSO) | `VERZUIM_TL_SECRET`, anders `.secret` |
| Bookmarklet | 📋 Verzuim ophalen — één mentorgroep | 📋 Verzuim teamleider — hele afdeling |
| Token | per gebruiker, uit het eckid | één per installatie van deze app |

Deel je toch één EnvironmentFile of docker-compose `environment:` tussen beide
apps, gebruik dan de bovenstaande namen naast elkaar. Zetten ze allebei
`VERZUIM_INGEST_PORT=8765`, dan krijgt de tweede die start een
`address already in use` en start de ontvanger niet op.

Een gedeeld geheim is geen probleem: de tokens worden met een andere boodschap
berekend (`verzuim:<eckid>` versus `verzuimsignalering-teamleider`), dus ze
verschillen sowieso. En omdat elke app zijn data in het geheugen van zijn eigen
proces houdt, kan de ene de payload van de andere niet oppikken.

Let op: de ontvanger houdt de data in het geheugen van hetzelfde proces als
Streamlit (15 minuten). Draai je meerdere workers of replica's, dan moet dat
een gedeelde store worden (Redis of een database).

## Privacy

- Het ophalen gebeurt in de browser van de teamleider, met diens eigen
  Magister-sessie en rechten. De app kan niet meer zien dan die persoon zelf.
- De opgehaalde data staat maximaal 15 minuten in het geheugen en wordt nergens
  weggeschreven. Het gedownloade HTML-bestand bevat wél leerlinggegevens —
  behandel dat als een verzuimlijst en zet het niet op een gedeelde schijf.
- `mentoren.json` en `.secret` blijven lokaal (staan in `.gitignore`).

## Bekende beperkingen

- De leerlingen komen uit `/api/leerlingen/zoeken?q=**`; wat dat teruggeeft,
  hangt af van je rechten in Magister. Krijg je niets, dan meldt de bookmarklet
  dat expliciet.
- De klasnaam bepaalt de afdelingstab. Klassen die niet met M/H/V/A/G + een
  cijfer beginnen, belanden onder **Overig**.
- Een leerling met meerdere klassen wordt bij de eerste geteld.
