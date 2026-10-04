# Verzuimsignalering

Signaleringsdashboard voor teamleiders: het verzuim van een hele afdeling uit
Magister — wie zit tegen de meldgrens aan, wie komt structureel te laat, en met
welke mentor moet dat besproken worden. Het verzuim wordt in de browser van de
teamleider opgehaald en verwerkt en komt niet op de server; de Streamlit-app
levert de bladwijzer en beheert de instellingen.

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

Doe dat nooit op een server: dan kan iedereen die de URL kent binnenlopen en
de leerlingnummers en klaargezette notities van een ander zien.

## Hoe het werkt

1. Je sleept eenmalig een **bookmarklet** naar je bladwijzerbalk.
2. Je klikt die aan in je eigen, ingelogde Magister-tabblad. Er opent een
   **rapportvenster**; daarin kies je periode en klassen.
3. De bookmarklet haalt in het Magister-tabblad de leerlingen en hun verzuim
   op — met jouw sessie, same-origin, dus zonder CORS-gedoe — en geeft het via
   `postMessage` door aan het rapportvenster (tabblad naar tabblad).
4. Het rapportvenster rekent het dashboard uit en tekent het. Daar kun je het
   ook als los HTML-bestand downloaden.

Het verzuim komt dus **niet op de server**: niet in de app, niet in de
ontvanger, ook niet tijdelijk in het geheugen. Er draait geen browser op de
server en er komt geen Magister-wachtwoord op de server.

**Waarom de data niet kan weglekken:** het rapportvenster heeft een
Content-Security-Policy met `default-src 'none'` (als header én in de pagina).
De browser blokkeert daardoor elke verbinding vanuit dat venster (fetch, XHR,
WebSocket, sendBeacon, formulieren, ook lettertypen). De bookmarklet stuurt de
data alleen naar de origin van het rapportvenster en reageert alleen op
berichten van die origin; het venster accepteert alleen berichten van het
Magister-tabblad dat het opende.

Van de app haalt de bookmarklet alleen dingen die geen leerlinggegevens zijn:
de instellingen (codes, mentornamen, grenzen, standaardselectie), de
leerlingnummers van de coördinator en klaargezette logboeknotities. Terug naar
de app gaat alleen per notitie of het schrijven gelukt is.

**Vertrouwen in de server blijft nodig voor de code.** Het rapportvenster en de
bookmarklet komen van onze server; wie die beheert, bepaalt wat ze doen. De data
zelf gaat er niet langs.

## Starten

```bash
pip install -r requirements.txt
VERZUIM_TL_ZONDER_LOGIN=1 streamlit run app.py     # lokaal, zonder portaal
```

De app draait op <http://localhost:8501>, de ontvanger op poort **8766** (in te
stellen met `VERZUIM_TL_INGEST_PORT`; de mentoruur-app gebruikt 8765). De
ontvanger levert ook het rapportvenster: <http://localhost:8766/rapport.html>.
Een venster op `http://localhost` openen vanaf de https-pagina van Magister mag:
browsers zien localhost als een veilige origin.

Zonder Magister kijken? Klik onderaan op **Voorbeelddata bekijken** — dat is
`voorbeeld_school.json` met 86 verzonnen leerlingen (opnieuw te maken met
`python maak_voorbeeld.py`). Je kunt dat bestand ook in het rapportvenster
openen via *Een verzuimbestand openen*.

## De bookmarklet

### Installeren (eenmalig)

**Slepen** — de makkelijke manier: zet je bladwijzerbalk aan met **Ctrl+Shift+B**
en sleep de blauwe knop **📋 Verzuim teamleider** uit de app erheen.

> De knop heet bewust anders dan de **📋 Verzuim ophalen** uit de mentoruur-app.
> Die twee kunnen naast elkaar in de balk staan: de mentorknop haalt één
> mentorgroep op, deze een hele afdeling.

**Handmatig** — als slepen niet lukt (of de balk uitstaat):

1. Klap in de app **Lukt slepen niet? Maak de bladwijzer handmatig** open en
   kopieer de hele regel code (die begint met `javascript:`).
2. Druk op **Ctrl+Shift+O** → **Nieuwe bladwijzer toevoegen**.
3. Naam: `Verzuim teamleider`. Plak bij **URL** de gekopieerde regel.
4. Opslaan in de map **Bladwijzerbalk**.

> Firefox en Safari knippen een geplakte `javascript:`-URL soms weg. Plak dan
> eerst in Kladblok, kopieer opnieuw, en plak dat in het URL-veld.

De bladwijzer bevat een token dat aan **jouw** account hangt (afgeleid van je
eckid). Daarmee haalt hij jouw instellingen, leerlingnummers en notities op bij
de app. Het token blijft geldig zolang `VERZUIM_TL_SECRET` (of anders `.secret`)
niet verandert; daarna moet iedereen de knop opnieuw slepen. Dat geldt ook als
`VERZUIM_TL_INGEST_URL` of `VERZUIM_TL_RAPPORT_URL` verandert.

**Had je de knop al van vóór oktober 2026?** Vervang hem. De oude stuurde het
verzuim naar de server; de ontvanger neemt dat niet meer aan.

### Gebruiken

1. Ga naar Magister en log in.
2. Klik in de bladwijzerbalk op **📋 Verzuim teamleider**. Er opent een venster.
   Gebeurt er niets, dan houdt de pop-upblokker het tegen: sta pop-ups toe voor
   Magister en klik opnieuw.
3. Kies in dat venster **begindatum** en **einddatum** (standaard de laatste 4
   weken, vanaf een maandag).
4. Vul in welke **klassen of leerjaren** je wilt: `H4,H5` pakt alle klassen die
   daarmee beginnen, `H4A` alleen die klas. Leeg laten = alles wat je in
   Magister mag zien — dat kan bij een grote school lang duren. De standaard
   stel je in de zijbalk van de app in.
5. **Logboeken ophalen** staat aan; ze worden alleen gehaald voor leerlingen
   met verzuim.
6. Klik **Ophalen**. Het venster toont de voortgang; laat het Magister-tabblad
   open tot het klaar is.
7. Het dashboard verschijnt in het venster, met boven het dashboard eventuele
   meldingen (onvolledige lijst, onbekende codes, mentorgroepen zonder naam).

Is Magister intussen herladen, dan luistert de bladwijzer niet meer: klik hem
opnieuw aan. Het venster meldt dat zelf als er geen antwoord komt.

Het logboek komt van:

    /api/leerlingen/<id>/lvs/logboekformulieren?begin=1980-01-01&einde=2030-01-01

Die URL vraagt om een periode; we nemen hem ruim, want een notitie van vorig
schooljaar (de warme overdracht in juli) is juist bruikbaar. Doet een andere
Magister-omgeving het anders, dan probeert hij nog vier varianten op de eerste
leerlingen; welke werkte meldt het venster. Staat daar dat er niets gevonden is,
dan moet die URL in `bookmarklet.py` bij `kandidaten` worden bijgezet.

### Hoe snel gaat het

Een heel leerjaar (141 leerlingen, vier weken) duurt **ongeveer 25 seconden**.
Dat is niet altijd zo geweest; het zat eerst op drie minuten, met halve
resultaten. Wat we onderweg hebben gemeten, staat hieronder omdat het uitmaakt
als je hier ooit aan sleutelt.

Magister heeft **twee routes** voor verzuim:

| Route | Limiet |
|---|---|
| `/api/m6/leerlingen/{id}/verantwoordingen` | na **29** verzoeken HTTP 429; teller loopt pas na ~30 s leeg |
| `/api/m6/leerlingen/{id}/verantwoordingen/afwezigheidsredenen` | **geen** merkbare limiet (141 achter elkaar, allemaal 200) |

Die tweede is de route die Magisters eigen *Verantwoordingen*-scherm gebruikt —
gevonden door dat scherm te openen en mee te kijken in het netwerkverkeer. Wij
gebruiken hem nu ook. Dat verklaart meteen waarom een selectie van H5 eerder
alleen H5A opleverde: na dertig leerlingen — precies een klas — ging alles op de
weigering, en die kwam binnen als "geen verzuim".

Verder:

- **De leerlingenlijst kost één verzoek.** Zoeken op je selectie (`H5`) geeft in
  één keer alle leerlingen van dat leerjaar (0,6 s). Alleen zonder selectie moet
  de hele school gepagineerd worden. Het antwoord wordt tegen `totalCount`
  gelegd; klopt dat niet, dan gaat hij door en meldt het venster dat de lijst
  onvolledig is.
- **Je ziet de voortgang** in het rapportvenster: welke stap (leerlingen,
  verzuim, herkansing, logboek) en hoeveel er binnen zijn. Het dashboard
  verschijnt pas als alles binnen is, zodat een tussenstand niet voor het
  eindresultaat wordt aangezien.
- **Wat mislukt, wordt gemeld.** Leerlingen waarvan het verzuim ook in de
  tweede ronde niet lukte, staan als foutmelding boven het dashboard: die staan
  daar anders ten onrechte op nul.
- Er is **geen bulkroute**: ook Magisters eigen scherm haalt de leerlingen één
  voor één op. Dat is geprobeerd met allerlei URL-vormen; allemaal 404.

### De codes komen uit Magister zelf

Bij elke registratie levert Magister de betekenis, het type en of de code
geoorloofd is. Daar rekenen we mee. Dat scheelt niet alleen werk, het voorkomt
fouten: onze eigen lijst had **`TA` als "te laat"** staan, terwijl het bij ons
"Teamleider afgehandeld" betekent — een geoorloofde code die we dus ten onrechte
als signaal telden. Te laat is `L`.

Naast ongeoorloofd, te laat en geoorloofd is er een vierde soort: **vergeten**
(`HV` huiswerk, `BV` boeken). Dat is geen verzuim, dus het telt niet in de uren,
maar het staat wel als knop in de balk.

`codes.json` blijft bestaan als terugval voor oudere bestanden en voor codes die
Magister niet duidt; de tabel is bijgewerkt naar wat Magister zelf zegt.

## Het dashboard lezen

De pagina is een **werklijst**, geen verantwoording: wie moet ik spreken,
waarover, en wat is er al gedaan. De urennorm staat er wel, maar niet centraal.

Bovenaan staat één regel met zes **redenen voor een gesprek** en hoeveel
leerlingen eraan voldoen; klik erop om de lijst te filteren, en op *toon alles*
om het filter weer los te laten:

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

Vanaf 16 uur ongeoorloofd verschijnt het label **melden** — een wettelijk feit,
geen stuurmiddel. Die grens en die van *vaak te laat* stel je in de zijbalk van de app in
(standaard dicht, open hem met de **»** linksboven). Meer grenzen zijn er niet:
sinds de pagina op gespreksredenen stuurt, deed *nadert de grens* niets meer en
is die eruit.

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

**Dit staat alleen in jouw browser** (`localStorage` van het rapportvenster),
niet op de server. Dus: niet zichtbaar voor collega's, weg bij een andere computer, een
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
download* aanzet. In het rapportvenster zie je hem altijd.

## Coördinator: een eigen lijst leerlingen

Bovenin de app staat naast **Teamleider** ook **Coördinator**. Die pagina is voor
wie een vaste groep van een stuk of twintig leerlingen volgt, dwars door de
afdelingen heen.

1. Zet onder **Leerlingnummers** de nummers neer — komma's, spaties of nieuwe
   regels maken niet uit, en plakken uit Excel of een mail werkt. Het nummer
   staat in de Magister-URL van de leerling: `…/leerling/17884/…`.
2. Sleep de knop **📋 Mijn leerlingen ophalen** rechtsboven eenmalig naar je
   bladwijzerbalk.
3. Klik hem in je Magister-tabblad aan. Het rapportvenster opent op de pagina
   *Coördinator*; klik daar **Ophalen**. De periode is deze week plus de drie
   ervoor, en de leerlingnummers haalt de bladwijzer op bij de app. Verandert je
   lijst, dan hoeft de knop dus **niet** opnieuw geïnstalleerd te worden.

Het is dezelfde bladwijzer-code als die van de teamleider; alleen de pagina
waarop het venster opent verschilt. In het venster kun je wisselen.

Per leerling worden drie dingen opgehaald — `/api/leerlingen/<id>` voor de naam,
`/aanmeldingen` voor de klas, en de `mentoren`-link daaruit voor de mentor. De
**mentor komt dus rechtstreeks uit Magister**; op deze pagina hoef je niets in te
vullen. Bestaat die route in een andere omgeving niet, dan valt de bookmarklet
terug op de zoeklijst (trager, en zonder mentor).

Het overzicht toont per leerling de **huidige week** als vijf lesdagen met de
codes die er staan, daaronder de weken ervoor als streepjes (één blokje per
lesdag) en de laatste drie logboekformulieren. Bovenaan staat wie deze week het
meest had; wie niets had, staat onderaan en wat lichter.

Nummers die Magister niet kent worden in het venster apart gemeld, zodat een
typefout niet stil verdwijnt.

De lijst wordt bewaard in `lijsten.json`, per gebruiker (op eckid). Dat zijn
alleen nummers, geen namen.

## Een logboeknotitie in Magister schrijven

Op de coördinatorpagina staat **Logboeknotitie schrijven in Magister**. Daarmee
zet je een notitie klaar; hij komt in het logboek van die leerling te staan, op
jouw naam.

Zo werkt het, en waarom zo:

1. Je kiest het leerlingnummer, het type en de tekst, en ziet meteen hoe het
   eruit komt te zien. De app kent alleen nummers: namen komen uit Magister en
   blijven in je browser.
2. **Klaarzetten voor Magister** legt de opdracht in een wachtrij. De app schrijft
   zelf niets — dat kan ook niet, want de server heeft geen Magister-sessie.
3. Klik de bladwijzer aan in Magister. Het rapportvenster toont op de pagina
   *Coördinator* wat er klaarstaat, met de namen erbij zodra je hebt opgehaald.
   **In Magister zetten** vraagt eerst om bevestiging en schrijft daarna één voor
   één weg, vanuit het Magister-tabblad.
4. Wat gelukt is verdwijnt uit de wachtrij; wat niet lukte blijft staan met de
   foutmelding erbij. Elke opdracht heeft een eigen sleutel, dus een tweede
   ronde schrijft nooit iets dubbel. Naar de app gaat alleen per sleutel of het
   gelukt is.

Achter de schermen is dat:

```
POST /api/leerlingen/<id>/lvs/logboekformulieren
{"formuliertypeId": 42, "omschrijving": "Mentoraat", "inhoud": "<p>…</p>",
 "aangemaaktOp": "…Z", "bovenliggendeId": null, "heeftPrioriteit": false,
 "isAfgerond": false, "verlooptOp": null, "waarden": {"bstVeld1": null, "bstVeld2": null}}
```

De typen die je mag aanmaken **verschillen per rol en per leerling**: als docent
bij een leerling zag ik Afspraak (4), Incident (6), Mentoraat (42) en Prognose
en warme overdracht (39); Notitie (7) stond daar niet bij. De app biedt de
gangbare typen aan; weigert Magister er een, dan zie je die melding terug. Bij
Mentoraat bepaalt Magister zelf de titel — alleen typen met de optie
`magOmschrijvingWijzigen` (zoals Notitie) laten die vrij.

Let op: dit is de enige plek waar de tool iets **wijzigt** in Magister. Alles
anders leest alleen. Een notitie die er eenmaal staat, haal je weg in Magister
zelf.

## De verzuimcodes

Hoeft niet meer nagelopen te worden: Magister levert per registratie zelf de
betekenis en of de code geoorloofd is (zie hierboven). Onder **Verzuimcodes
indelen** kun je de terugval-lijst bijstellen voor codes die Magister niet
duidt. Welke dat zijn, meldt het rapportvenster boven het dashboard; voeg ze in
de tabel toe en klik **Codes opslaan**. Bij je volgende ophaalronde tellen ze
mee.

## Mentorgroepen en mentoren

De mentor hangt niet aan de klas maar aan een **lesgroep**: `h4mtu1` t/m
`h4mtu8`. De app zoekt die lesgroep op bij elke leerling — herkend aan het
stukje tekst dat links in de zijbalk staat (standaard `mtu`). Heten de
mentorgroepen bij jullie anders, pas dat daar aan; het geldt bij je volgende
ophaalronde.

De mentorgroep bepaalt drie dingen:

- het paneel **Ongeoorloofd per mentorgroep** (welke mentor moet je spreken);
- de tab waar een leerling onder valt (`h4mtu1` → Havo 4);
- de regel onder de naam van de leerling: `H4A · h4mtu1 · mentor T. Vermeer`.

Magister geeft de mentornaam niet mee. Vul die in de zijbalk in als
`h4mtu1 = T. Vermeer`. Het rapportvenster toont boven het dashboard welke
mentorgroepen nog geen naam hebben, al in die vorm (`h4mtu1 = `): kopieer dat
naar de zijbalk en typ alleen de namen. **Mentoren opslaan** schrijft
`mentoren.json` (niet in git).

Zit een leerling in geen enkele mentorgroep, dan valt die terug op zijn klas;
het venster meldt hoeveel dat er zijn.

## Bestanden

| Bestand | Wat het doet |
|---|---|
| `app.py` | de Streamlit-app: portaal-login, instellingen, bladwijzer-installatie, leerlingnummers, notities klaarzetten |
| `bookmarklet.py` | genereert de bladwijzer (draait in Magister, haalt op, praat met het rapportvenster) |
| `rapport_bron.html` | het rapportvenster: CSP, formulier, verbinding met Magister, meldingen, download |
| `rapport.py` | zet `rapport.html` in elkaar uit `rapport_bron.html` en de bestanden hieronder |
| `verwerk.js` | rekent een payload om tot het dashboard (alles wat geteld wordt) |
| `template.html` | de opmaak van het teamleider-dashboard (styling + lege panelen) |
| `render.js` | tekent de panelen van het teamleider-dashboard; draait in de pagina zelf |
| `coordinator.js` / `coordinator.css` | het weekbeeld voor een eigen lijst leerlingen |
| `ingest.py` | ontvanger (localhost, poort uit `VERZUIM_TL_INGEST_PORT`): levert het rapportvenster, de instellingen, de leerlingnummers en de schrijfwachtrij |
| `dashboard.py` | codetabel lezen en opslaan, standaardgrenzen |
| `coordinator.py` | leerlingnummers uit vrije tekst halen |
| `codes.json` | verzuimcodes → betekenis + soort (ongeoorloofd/te laat/geoorloofd) |
| `maak_voorbeeld.py` | schrijft `voorbeeld_school.json` met verzonnen data |

Alles wat geteld wordt, gebeurt in `verwerk.js`; `render.js` en `coordinator.js`
tekenen alleen. Zo geven het venster en het gedownloade HTML-bestand altijd
dezelfde cijfers. `verwerk.js` is een één-op-één omzetting van de vroegere
Python-versie; bij de omzetting gaf hij op de voorbeelddata exact dezelfde data
en HTML.

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
# VERZUIM_TL_RAPPORT_URL=https://<jouw-domein>/verzuim-tl-ingest/rapport.html   # optioneel, dit is de standaard
```

`JWT_SECRET` moet exact gelijk zijn aan dat van het portaal, anders wordt geen
enkel token geaccepteerd. `VERZUIM_TL_SECRET` is iets anders: dat bepaalt alleen
de ontvangsttokens van de bookmarklet en hoeft niets met het portaal te maken te
hebben — neem daar dus een eigen waarde voor.

`VERZUIM_TL_INGEST_URL` is het adres dat **in de bookmarklet** terechtkomt, dus
het publieke pad. Het rapportvenster staat standaard op hetzelfde pad plus
`/rapport.html`; de ontvanger levert het, dus daarvoor is geen extra nginx-regel
nodig. Wijzigt een van beide adressen later, dan moet iedereen de knop opnieuw
installeren.

Laat het rapportvenster op **hetzelfde domein** staan als de app. De
contactmomenten staan in `localStorage` van het venster; op een ander domein
begint iedereen met een lege lijst.

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

# Ontvanger: rapportvenster, instellingen, leerlingnummers, schrijfwachtrij
location /verzuim-tl-ingest {
    proxy_pass http://127.0.0.1:8767/ingest;
    proxy_set_header Host $host;
}
```

Zet hier **geen** `Cross-Origin-Opener-Policy`: dan verliest het rapportvenster
de koppeling met het Magister-tabblad (`window.opener`).

Draai je de app op een **subpad** (`/verzuim-tl/`) in plaats van een eigen
(sub)domein, start Streamlit dan met `--server.baseUrlPath verzuim-tl`; anders
laden de statische bestanden niet.

Het pad achter `proxy_pass` (`/ingest`) maakt de ontvanger niet uit — die kijkt
alleen of het eindigt op `/rapport.html` en verder naar de `?token=`. De
querystring stuurt nginx vanzelf mee.

De oude `client_max_body_size 20m` mag weg: er komt geen verzuim meer binnen,
alleen kleine schrijfuitslagen (de ontvanger weigert alles boven 64 KB).

### 4. Controleren

```bash
sudo ss -lntp | grep -E '8507|8767'     # 8767 hoort op 127.0.0.1 te staan, niet 0.0.0.0
curl -si -X POST 'https://<jouw-domein>/verzuim-tl-ingest' --data 'x'   # 400 = nginx komt aan
curl -sI 'https://<jouw-domein>/verzuim-tl-ingest/rapport.html'          # 200 + Content-Security-Policy
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
verschillen sowieso.

De ontvanger luistert standaard alleen op `127.0.0.1`; nginx staat ervoor, dus
de poort hoeft niet van buiten bereikbaar te zijn.

## Privacy

- Het ophalen gebeurt in de browser van de teamleider, met diens eigen
  Magister-sessie en rechten. De app kan niet meer zien dan die persoon zelf.
- Het verzuim, de namen en de logboekteksten komen niet op de server. Ze gaan
  van het Magister-tabblad naar het rapportvenster en blijven in die browser;
  het venster kan door zijn CSP zelf niets versturen. Sluit je het venster, dan
  zijn ze weg.
- Op de server staan alleen instellingen (`codes.json`, `mentoren.json`), de
  leerlingnummers van coördinatoren (`lijsten.json`, nummers zonder namen) en,
  in het geheugen, klaargezette logboeknotities tot ze geschreven zijn. Die
  notities typt de coördinator zelf in de app.
- Het gedownloade HTML-bestand bevat wél leerlinggegevens — behandel dat als
  een verzuimlijst en zet het niet op een gedeelde schijf.
- `mentoren.json` en `.secret` blijven lokaal (staan in `.gitignore`).
- Inloggen gaat via het portaal; alleen `docent` en `beheerder` komen binnen. Het
  token van de bookmarklet is per gebruiker, dus niemand kan bij de lijst of de
  schrijfwachtrij van een ander.
- Contactmomenten staan in `localStorage` van de browser van de teamleider — niet
  op de server, niet in het downloadbestand, niet zichtbaar voor anderen.
- Logboekteksten blijven standaard uit het downloadbestand; in het rapportvenster
  zijn ze zichtbaar.

## Bekende beperkingen

- De leerlingen komen uit `/api/leerlingen/zoeken?q=**`; wat dat teruggeeft,
  hangt af van je rechten in Magister. Krijg je niets, dan meldt het venster
  dat expliciet.
- Het rapportvenster moet als pop-up mogen openen vanuit Magister.
- De klasnaam bepaalt de afdelingstab. Klassen die niet met M/H/V/A/G + een
  cijfer beginnen, belanden onder **Overig**.
- Een leerling met meerdere klassen wordt bij de eerste geteld.
