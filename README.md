# Verzuimsignalering

Streamlit-app voor teamleiders: haalt het verzuim van een hele afdeling uit
Magister en maakt daar een signaleringsdashboard van — wie zit tegen de
meldgrens aan, wie komt structureel te laat, en met welke mentor moet dat
besproken worden.

De mentorvariant (één mentorgroep) zit in de mentoruur-app; deze app is de
teamleiderskant en draait los. Het dashboard is de uitgewerkte versie van
`mentoruur/demo_teamleider_dashboard.html`, nu met echte data.

## Inloggen

De app hangt achter het portaal, net als de mentoruur-app: je komt binnen via
de tegel op [bovenbouwsucces.nl](https://bovenbouwsucces.nl), die een SSO-token
(JWT) in de URL meegeeft. De app controleert dat token met `JWT_SECRET` — hetzelfde
geheim als het portaal — en laat alleen `docent` en `beheerder` door. Het token
wordt daarna meteen uit de adresbalk gehaald.

Wat je in Magister mag ophalen bepaalt Magister zelf: de bookmarklet draait met
jouw eigen sessie en rechten.

Ververs je de pagina (F5), dan ben je uitgelogd en ga je opnieuw via het
portaal — dat werkt in de andere apps net zo.

Voor lokaal ontwikkelen kun je de inlogpoort overslaan:

```bash
VERZUIM_TL_ZONDER_LOGIN=1 streamlit run app.py
```

Doe dat nooit op een server: dan kan iedereen die de URL kent binnenlopen én
een binnengekomen verzuimbestand oppikken.

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
VERZUIM_TL_ZONDER_LOGIN=1 streamlit run app.py     # lokaal, zonder portaal
```

De app draait op <http://localhost:8501>, de ontvanger van de bookmarklet op
poort **8766** (in te stellen met `VERZUIM_TL_INGEST_PORT`; de mentoruur-app
gebruikt 8765). Vanaf de https-pagina van Magister posten naar
`http://localhost` mag: browsers zien localhost als een veilige origin.

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

De bladwijzer bevat een token dat aan **jouw** account hangt (afgeleid van je
eckid). Daardoor komt jouw opgehaalde verzuim alleen in jouw eigen sessie
terecht, ook als een collega tegelijk bezig is. Het token blijft geldig zolang
`VERZUIM_TL_SECRET` (of anders `.secret`) niet verandert; daarna moet iedereen
de knop opnieuw slepen.

### Gebruiken

1. Ga naar Magister en log in.
2. Klik in de bladwijzerbalk op **📋 Verzuim teamleider**.
3. Vul **begindatum** en **einddatum** in (standaard de laatste 4 weken, vanaf
   een maandag).
4. Vul in welke **klassen of leerjaren** je wilt: `H4,H5` pakt alle klassen die
   daarmee beginnen, `H4A` alleen die klas. Leeg laten = alles wat je in
   Magister mag zien — dat kan bij een grote school lang duren.
5. Hij vraagt of hij ook de **logboekformulieren** moet ophalen. Dat kost
   ongeveer evenveel tijd als het verzuim zelf; zeg nee als je ze niet nodig hebt.
6. De titel van het tabblad toont de voortgang (`Verzuim TL 120/240...`). Bij meer
   dan 150 leerlingen vraagt de bookmarklet eerst om bevestiging.
7. Als het klaar is: terug naar het tabblad van de app. Daar staat het
   dashboard (of, bij de downloadvariant, upload je het bestand).

Het logboek komt van:

    /api/leerlingen/<id>/lvs/logboekformulieren?begin=2026-08-01&einde=2027-07-31

Die URL vraagt om een periode; de bookmarklet vult daar het **hele schooljaar**
in (afgeleid van je einddatum), want een notitie uit juli hoort in september nog
steeds bij de leerling. Doet een andere Magister-omgeving het anders, dan
probeert hij nog vier varianten op de eerste leerlingen; welke werkte meldt de
app boven het dashboard. Staat daar dat er niets gevonden is, dan moet die URL in
`bookmarklet.py` bij `kandidaten` worden bijgezet.

Het ophalen kost één verzoek per leerling. Daarom wordt er eerst gefilterd en
pas daarna verzuim opgehaald.

**Magister knijpt bij veel verzoeken** (HTTP 429). Bij een selectie van drie
klassen over een heel schooljaar gebeurde dat 40 keer. De bookmarklet begint
daarom met blokjes van acht en een korte pauze, en wordt vanzelf rustiger zodra
een 429 langskomt: blokjes van vier en een pauze die oploopt tot 2,5 seconde.
Wie dan nog mislukt, krijgt een tweede, tragere ronde. In de meting kwamen zo
alle 83 leerlingen binnen (80 seconden voor een heel schooljaar); een periode
van vier weken is veel sneller.

Lukt het daarna nog steeds niet voor iedereen, dan vraagt de bookmarklet of je
wilt doorgaan en meldt de app hoeveel leerlingen ontbreken. Ga daar niet
overheen: die leerlingen staan dan ten onrechte op nul uur.

De leerlingenlijst zelf komt in pagina's binnen (Magister geeft er ongeveer 50
per keer). De bookmarklet pagineert door tot hij er evenveel heeft als
`totalCount` aangeeft. Lukt dat niet — bijvoorbeeld omdat de omgeving `skip`
negeert — dan meldt hij dat expliciet (*"Magister gaf 50 van de 1800 leerlingen
terug"*) en kun je kiezen of je met die onvolledige lijst doorgaat. Zie je maar
één klas terwijl je een heel leerjaar verwacht, dan is dit de plek om te kijken.

## Het dashboard lezen

De pagina is een **werklijst**, geen verantwoording: wie moet ik spreken,
waarover, en wat is er al gedaan. De urennorm staat er wel, maar niet centraal.

Bovenaan staan zes **redenen voor een gesprek**; klik erop om de lijst te
filteren:

| Signaal | Wanneer |
|---|---|
| **Loopt op** | de laatste weken duidelijk meer dan de weken ervoor (minstens 4 registraties) |
| **Nog geen contact** | er is verzuim, maar jij hebt niets vastgelegd — je werkvoorraad |
| **Vaak te laat** | 6 keer of vaker (in te stellen) |
| **Eerste uur** | de helft of meer valt in lesuur 1 en 2 — ander gesprek dan spijbelen overdag |
| **Eén vak** | meer dan de helft bij dezelfde docent — dan moet je daar zijn |
| **Opgeknapt** | duidelijk minder dan de periode ervoor; ook dat is een gesprek waard |

Die redenen rekenen over **ongeoorloofd verzuim en te laat komen**, ongeacht
welke codes je toont. Ziek en verlof zijn context, geen gespreksreden.

Per leerling zie je een **patroonstrook**: vier weken lesdagen als blokjes,
gekleurd naar het zwaarste wat er die dag speelde. Zo onderscheid je in één
oogopslag één ziekweek van elke-maandag-afwezig. Daaronder staan de uren als
klein cijfer, en rechts wat je al deed (*3 sep · telefoon ouders*) of dat er nog
niets ligt.

De lijst staat standaard op **wie het eerst spreken**: wat oploopt en nog geen
contact heeft, staat bovenaan. Leg je contact vast, dan zakt die leerling
vanzelf. Sorteren op uren of naam kan nog steeds.

Vanaf 16 uur ongeoorloofd verschijnt het label **melden** — een wettelijk
feit, geen stuurmiddel. Die grens en de andere stel je in de zijbalk in (die
staat standaard dicht, open hem met de **»** linksboven).

Rechts staan drie panelen: verzuim per week, **uitval per lesuur** (wanneer op de
dag gaat het mis — dat stuurt je interventie) en getoonde uren per mentorgroep
(met wie bespreek je het).

### Codeknoppen: wat je in beeld hebt

Boven de kerncijfers staat per verzuimcode een knop met alleen de afkorting en
het aantal registraties (`A 25`, `ZI 24`); wat de code betekent zie je door er
met de muis op te gaan staan. Die knoppen bepalen wat je ziet: de tegels, de
weekgrafiek, de uitval per lesuur, het overzicht per mentorgroep, de
leerlingenlijst en de dagregels daarin.

Standaard staan **ongeoorloofd en te laat** aan en **geoorloofd** uit — dat is
het signaleringsbeeld. Zet `ZI` aan en het ziekteverzuim komt erbij, inclusief de
leerlingen die alléén ziek gemeld waren; met de snelknop *geoorloofd* zie je
uitsluitend dat. De knoppen *alles*, *ongeoorloofd* en *geoorloofd* rechts zetten
alles in één klik.

De drie signalen bovenaan (meldplicht, nadert de grens, vaak te laat) rekenen
altijd over **alle** registraties, ongeacht welke codes je toont. Dat is een norm
en geen weergave: anders zou het wegklikken van een code iemand ten onrechte
groen maken.

### Contact vastleggen

Klap een leerling open en leg onder **Contact** vast wat je hebt gedaan: datum,
soort (telefoon ouders, gesprek leerling, mail, mentor ingelicht, leerplicht
gemeld, anders) en een korte notitie. Achter de naam verschijnt dan de datum van
het laatste contact, en met het vierde signaal *Contact gelegd* filter je op
leerlingen waar je al iets mee gedaan hebt.

**Dit staat alleen in jouw browser** (`localStorage` van de app), niet op de
server. Dus: niet zichtbaar voor collega's, weg bij een andere computer, een
ander browserprofiel of het legen van je browsergegevens, en niet aanwezig in het
gedownloade HTML-bestand. Bewaar wat je wilt houden via *contactmomenten
vastgelegd — bekijken* boven de lijst; daar zit **Download als JSON**. Zodra
vastleggen op de server mag, kan die JSON zo ingelezen worden.

### Logboek uit Magister

Haalt de bookmarklet ook logboekformulieren op, dan staat per leerling een
inklapbaar **Logboek (n)** met de **laatste drie** formulieren: datum, titel, wie
het schreef en de tekst. De opmaak uit Magister wordt omgezet naar platte tekst;
er komt bewust geen HTML van derden in de pagina.

Het ophalen gaat over alle jaren, want de warme overdracht van vorig jaar (juli)
is juist bruikbaar. Staat er niets van dit schooljaar, dan zegt het blok dat:
*niets van dit schooljaar*. Alleen leerlingen mét verzuim worden bevraagd.

Logboektekst is gevoelig (thuissituatie, diagnoses). Daarom zit die **niet** in
het bestand dat je downloadt, tenzij je in de zijbalk *Logboektekst in de
download* aanzet. In de app zie je hem altijd.

## Coördinator: een eigen lijst leerlingen

Bovenin de app staat naast **Teamleider** ook **Coördinator**. Die pagina is voor
wie een vaste groep van een stuk of twintig leerlingen volgt, dwars door de
afdelingen heen.

1. Zet onder **Leerlingnummers** de nummers neer — komma's, spaties of nieuwe
   regels maken niet uit, en plakken uit Excel of een mail werkt. Het nummer
   staat in de Magister-URL van de leerling: `…/leerling/17884/…`.
2. Sleep de knop **📋 Mijn leerlingen ophalen** rechtsboven eenmalig naar je
   bladwijzerbalk.
3. Klik hem in je Magister-tabblad aan. Hij vraagt niets: de periode is deze week
   plus de drie ervoor, en de leerlingnummers haalt hij op bij de app. Verandert
   je lijst, dan hoeft de knop dus **niet** opnieuw geïnstalleerd te worden.

Per leerling worden drie dingen opgehaald — `/api/leerlingen/<id>` voor de naam,
`/aanmeldingen` voor de klas, en de `mentoren`-link daaruit voor de mentor. De
**mentor komt dus rechtstreeks uit Magister**; op deze pagina hoef je niets in te
vullen. Bestaat die route in een andere omgeving niet, dan valt de bookmarklet
terug op de zoeklijst (trager, en zonder mentor).

Het overzicht toont per leerling de **huidige week** als vijf lesdagen met de
codes die er staan, daaronder de weken ervoor als streepjes (één blokje per
lesdag) en de laatste drie logboekformulieren. Bovenaan staat wie deze week het
meest had; wie niets had, staat onderaan en wat lichter.

Nummers die Magister niet kent worden apart gemeld, zodat een typefout niet stil
verdwijnt.

De lijst wordt bewaard in `lijsten.json`, per gebruiker (op eckid). Dat zijn
alleen nummers, geen namen.

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
| `app.py` | de Streamlit-app: portaal-login, instellingen, bookmarklet-installatie, dashboard |
| `bookmarklet.py` | genereert de bookmarklet (downloadvariant en directe variant) |
| `ingest.py` | ontvanger (localhost, poort uit `VERZUIM_TL_INGEST_PORT`) waar de bookmarklet naartoe post |
| `dashboard.py` | rekent de payload om en bouwt het HTML-dashboard |
| `coordinator.py` / `coordinator.js` | de weekpagina voor een eigen lijst leerlingen |
| `template.html` | de opmaak van het dashboard (styling + lege panelen) |
| `render.js` | tekent de panelen uit de data; draait in de pagina zelf |
| `codes.json` | verzuimcodes → betekenis + soort (ongeoorloofd/te laat/geoorloofd) |
| `maak_voorbeeld.py` | schrijft `voorbeeld_school.json` met verzonnen data |

Alles wat geteld wordt, gebeurt in `dashboard.py`; `render.js` tekent alleen.
Zo geven de app en het gedownloade HTML-bestand altijd dezelfde cijfers.

## Op een server draaien

Voorbeeld met de poorten zoals ze hier draaien: de app op **8507**, de
ontvanger op **8767** (8765 is van de mentoruur-app, 8766 van de inhaaltool).

### 1. Omgevingsvariabelen

```bash
JWT_SECRET=<zelfde-geheim-als-het-portaal>                      # voor het inloggen
VERZUIM_TL_INGEST_URL=https://<jouw-domein>/verzuim-tl-ingest   # publiek pad, niet de poort
VERZUIM_TL_INGEST_PORT=8767                                     # interne poort achter nginx
VERZUIM_TL_SECRET=<een-ander-lang-geheim>                       # anders wordt .secret gebruikt
PORTAAL_URL=https://bovenbouwsucces.nl                          # waar de inlogmelding heen wijst
```

`JWT_SECRET` moet exact gelijk zijn aan dat van het portaal, anders wordt geen
enkel token geaccepteerd. `VERZUIM_TL_SECRET` is iets anders: dat bepaalt alleen
de ontvangsttokens van de bookmarklet en hoeft niets met het portaal te maken te
hebben — neem daar dus een eigen waarde voor.

`VERZUIM_TL_INGEST_URL` is het adres dat **in de bookmarklet** terechtkomt, dus
het publieke pad. Wijzigt dat pad later, dan moet iedereen de knop opnieuw
installeren.

### 2. systemd

```ini
[Unit]
Description=Verzuimsignalering (teamleider)
After=network.target

[Service]
User=www-data
WorkingDirectory=/opt/verzuimsignalering
Environment=JWT_SECRET=<zelfde-geheim-als-het-portaal>
Environment=VERZUIM_TL_INGEST_URL=https://<jouw-domein>/verzuim-tl-ingest
Environment=VERZUIM_TL_INGEST_PORT=8767
Environment=VERZUIM_TL_SECRET=<een-ander-lang-geheim>
ExecStart=/opt/verzuimsignalering/env/bin/streamlit run app.py           --server.port 8507 --server.headless true --browser.gatherUsageStats false
Restart=always

[Install]
WantedBy=multi-user.target
```

De service-gebruiker moet in de projectmap mogen **schrijven**: `codes.json`,
`mentoren.json` en `lijsten.json` worden vanuit de app opgeslagen, en zonder
`VERZUIM_TL_SECRET` wordt `.secret` aangemaakt.

### 3. nginx

```nginx
# De app zelf (Streamlit heeft websockets nodig)
location /verzuim-tl/ {
    proxy_pass http://127.0.0.1:8507/;
    proxy_http_version 1.1;
    proxy_set_header Upgrade    $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host       $host;
    proxy_read_timeout 3600s;
}

# Ontvanger voor de teamleider-bookmarklet
location /verzuim-tl-ingest {
    proxy_pass http://127.0.0.1:8767/ingest;
    proxy_set_header Host $host;
    client_max_body_size 20m;      # anders HTTP 413 bij een lange periode
}
```

Draai je de app op een **subpad** (`/verzuim-tl/`) in plaats van een eigen
(sub)domein, start Streamlit dan met `--server.baseUrlPath verzuim-tl`; anders
laden de statische bestanden niet.

Het pad achter `proxy_pass` (`/ingest`) maakt de ontvanger niet uit — die kijkt
alleen naar de `?token=`. De querystring stuurt nginx vanzelf mee.

`client_max_body_size` is de enige echte valkuil: nginx staat standaard 1 MB
toe. Een afdeling van 250 leerlingen over 4 weken is ongeveer 0,2 MB, dus dat
past meestal wel, maar over een heel jaar niet. Loopt het mis, dan meldt de
bookmarklet "De app antwoordde met HTTP 413".

### 4. Controleren

```bash
sudo ss -lntp | grep -E '8507|8767'     # 8767 hoort op 127.0.0.1 te staan, niet 0.0.0.0
curl -si -X POST 'https://<jouw-domein>/verzuim-tl-ingest' --data 'x'   # 400 = nginx komt aan
```

Let ook op de jwt-module: het pakket **`jwt`** (1.x) heet net zo als **PyJWT**
en verdringt het, waarna inloggen stukloopt. De app weigert dan te starten met
een uitleg. Herstellen:

```bash
venv/bin/pip uninstall -y jwt && venv/bin/pip install --force-reinstall PyJWT
```

Een `{"ok": false, "error": "bad request"}` is hier het goede antwoord: de
ontvanger is bereikbaar en wijst het verzoek af omdat het token ontbreekt.
Krijg je 502, dan draait de app niet; 404 betekent dat de `location` niet
matcht.

### Naast de mentoruur-app op dezelfde server

Alle namen zijn bewust anders dan die van de mentoruur-app, want die zou er
anders overheen lopen:

| | mentoruur-app | deze app |
|---|---|---|
| Ontvanger-URL | `VERZUIM_INGEST_URL` | `VERZUIM_TL_INGEST_URL` |
| Poort | `VERZUIM_INGEST_PORT` (8765) | `VERZUIM_TL_INGEST_PORT` (8767 hier) |
| Geheim | `JWT_SECRET` (ook voor SSO) | `VERZUIM_TL_SECRET`, anders `.secret` |
| Bookmarklet | 📋 Verzuim ophalen — één mentorgroep | 📋 Verzuim teamleider — hele afdeling |
| Token | per gebruiker, uit het eckid | één per installatie van deze app |

Deel je één EnvironmentFile tussen beide apps, gebruik dan de bovenstaande
namen naast elkaar. Zetten ze allebei `VERZUIM_INGEST_PORT=8765`, dan krijgt de
tweede die start een `address already in use` en heeft die geen ontvanger.

Een gedeeld geheim is geen probleem: de tokens worden met een andere boodschap
berekend (`verzuim:<eckid>` versus `verzuimsignalering-teamleider`), dus ze
verschillen sowieso. En omdat elke app zijn data in het geheugen van zijn eigen
proces houdt, kan de ene de payload van de andere niet oppikken.

De ontvanger luistert standaard alleen op `127.0.0.1`; nginx staat ervoor, dus
de poort hoeft niet van buiten bereikbaar te zijn.

## Privacy

- Het ophalen gebeurt in de browser van de teamleider, met diens eigen
  Magister-sessie en rechten. De app kan niet meer zien dan die persoon zelf.
- De opgehaalde data staat maximaal 15 minuten in het geheugen en wordt nergens
  weggeschreven. Het gedownloade HTML-bestand bevat wél leerlinggegevens —
  behandel dat als een verzuimlijst en zet het niet op een gedeelde schijf.
- `mentoren.json` en `.secret` blijven lokaal (staan in `.gitignore`).
- Inloggen gaat via het portaal; alleen `docent` en `beheerder` komen binnen. Het
  ontvangsttoken van de bookmarklet is per gebruiker, dus een binnengekomen
  bestand kan niet in de sessie van een ander belanden.
- Contactmomenten staan in `localStorage` van de browser van de teamleider — niet
  op de server, niet in het downloadbestand, niet zichtbaar voor anderen.
- Logboekteksten blijven standaard uit het downloadbestand; in de app zijn ze
  zichtbaar voor wie is ingelogd.

## Bekende beperkingen

- De leerlingen komen uit `/api/leerlingen/zoeken?q=**`; wat dat teruggeeft,
  hangt af van je rechten in Magister. Krijg je niets, dan meldt de bookmarklet
  dat expliciet.
- De klasnaam bepaalt de afdelingstab. Klassen die niet met M/H/V/A/G + een
  cijfer beginnen, belanden onder **Overig**.
- Een leerling met meerdere klassen wordt bij de eerste geteld.
