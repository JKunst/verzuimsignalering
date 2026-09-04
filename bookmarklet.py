"""
bookmarklet.py — genereert de bookmarklet die het verzuim uit Magister haalt.

Waarom een bookmarklet: het ophalen gebeurt in het tabblad waar de teamleider
zélf is ingelogd. Same-origin, dus geen CORS, geen Magister-wachtwoord op de
server en geen headless browser op een VPS. De server ziet alleen het resultaat.

Verschil met de mentor-variant in `mentoruur/magister_verzuim.py`: die vraagt
`rol=Mentor` en krijgt de eigen mentorgroep. Een teamleider heeft die rol niet
bij zijn leerlingen, dus hier wordt alles opgehaald wat het account mag zien en
daarna gefilterd op klas of leerjaar ('H4,H5'). Filteren gebeurt vóór het
verzuim opgehaald wordt, want dat kost één request per leerling.

Let op de snelheid: Magister geeft HTTP 429 als er te veel verzoeken tegelijk
binnenkomen. Daarom blokjes van acht met een pauze ertussen, opnieuw proberen bij
429, en een tweede ronde voor wie dan nog mislukt. Zonder dat verdween er stil
een hele klas uit het overzicht.

Optioneel haalt hij ook de logboekformulieren op (LVS):

    /api/leerlingen/<id>/lvs/logboekformulieren?begin=1980-01-01&einde=2030-01-01

Die vraagt om een periode; we nemen hem ruim en houden per leerling de laatste
drie over. Een notitie van vorig schooljaar (de warme overdracht in juli) is
namelijk juist bruikbaar. Alleen leerlingen mét verzuim worden bevraagd — dat
scheelt de helft van de requests. Mocht de URL in een andere omgeving anders
heten, dan probeert de bookmarklet nog vier varianten op de eerste leerlingen;
welke werkte komt in `logboek_bron` terug en toont de app.

Twee varianten:
- download: schrijft een JSON-bestand dat je in de app uploadt (werkt altijd);
- post:     stuurt de data direct naar de draaiende app (geen bestand nodig).
"""

from urllib.parse import quote

# Vervangen bij het bouwen: __TAIL__ (aflevering), en in de POST-variant
# __INGEST__ en __TOKEN__.
_JS = r"""(async()=>{
try{
 var pad=function(n){return String(n).padStart(2,'0')};
 var iso=function(d){return d.getFullYear()+'-'+pad(d.getMonth()+1)+'-'+pad(d.getDate())};
 var vandaag=new Date();
 var start=new Date(); start.setDate(start.getDate()-27);
 start.setDate(start.getDate()-((start.getDay()+6)%7));           // naar maandag
 var b=prompt('Begindatum (JJJJ-MM-DD)',iso(start)); if(!b)return;
 var e=prompt('Einddatum (JJJJ-MM-DD)',iso(vandaag)); if(!e)return;
 var scope=prompt('Welke klassen of leerjaren? Komma-gescheiden, bijv. H4,H5 of H4A.\n\nLeeg laten = alles wat je in Magister mag zien.','__SCOPE__');
 if(scope===null)return;
 scope=scope.trim();
 var filters=scope?scope.split(',').map(function(s){return s.trim().toUpperCase()}).filter(Boolean):[];
 var base=location.origin;
 // Snelheid: begint vlot en wordt vanzelf rustiger zodra Magister knijpt.
 var SZ=8,pauze=150,traag=false;
 var vertraag=function(){
   if(!traag){traag=true;SZ=4;pauze=900;}
   else{pauze=Math.min(pauze+400,2500);}};
 var wacht=function(ms){return new Promise(function(k){setTimeout(k,ms)})};
 var haal=async function(url,pogingen){
   for(var poging=0;poging<(pogingen||3);poging++){
     var r=await fetch(base+url,{signal:AbortSignal.timeout(20000)}).catch(function(){return null});
     if(r&&r.ok)return r;
     if(r&&(r.status===429||r.status>=500)){vertraag();await wacht(1500*(poging+1));continue;}
     return r;                       // andere fout: opnieuw proberen helpt niet
   }
   return null;};
 var jget=async function(u){try{var r=await fetch(u,{signal:AbortSignal.timeout(20000)});
   if(r.status===204)return{};var t=await r.text();return t&&t.trim()?JSON.parse(t):{};}catch(_){return{};}};

 // 1. Leerlingen ophalen. Magister levert dit in pagina's; hoeveel er in totaal
 //    zijn staat in totalCount. Daar pagineren we op door, want alleen stoppen
 //    bij een korte pagina levert soms maar één klas op.
 document.title='Leerlingen ophalen...';
 var alle=[],gezien={},skip=0,TOP=100,totaal=null,paginas=0;
 for(var p=0;p<120;p++){
   var res=await jget(base+'/api/leerlingen/zoeken?q=**&top='+TOP+'&skip='+skip);
   var items=res.items||[];
   if(totaal===null){
     var t=[res.totalCount,res.totaalAantal,res.count,res.total];
     for(var ti=0;ti<t.length;ti++){if(typeof t[ti]==='number'){totaal=t[ti];break;}}
   }
   if(!items.length)break;
   paginas++;
   var nieuw=0;
   items.forEach(function(s){if(!gezien[s.id]){gezien[s.id]=1;alle.push(s);nieuw++;}});
   skip+=items.length;
   document.title='Leerlingen '+alle.length+(totaal?'/'+totaal:'')+'...';
   if(!nieuw)break;                                   // zelfde pagina opnieuw
   if(totaal!==null){if(alle.length>=totaal)break;}
   else if(items.length<TOP)break;
 }
 if(!alle.length){document.title='Magister';
   alert('Geen leerlingen gevonden.\n\nBen je hier ingelogd als docent/teamleider? Open eerst Magister en probeer het opnieuw.');return;}
 if(totaal!==null&&alle.length<totaal&&!confirm('Magister gaf '+alle.length+' van de '+totaal+' leerlingen terug'
   +' ('+paginas+' pagina\'s).\n\nDoorgaan met deze onvolledige lijst?')){document.title='Magister';return;}

 // 2. Filteren op klas of leerjaar (voordat we per leerling verzuim opvragen).
 var past=function(s){
   if(!filters.length)return true;
   var labels=[].concat(s.klassen||[],s.studies||[]).map(function(x){return String(x).toUpperCase()});
   return labels.some(function(l){return filters.some(function(f){return l.indexOf(f)===0})});
 };
 var students=alle.filter(past);
 if(!students.length){document.title='Magister';
   alert('Van de '+alle.length+' leerlingen past er geen op "'+scope+'".\n\nKijk hoe de klassen in Magister heten (bijv. H4A) en probeer een ander filter.');return;}
 var seconden=Math.ceil(students.length/20*0.6);
 if(students.length>150&&!confirm(students.length+' leerlingen gevonden'+(filters.length?' voor '+scope:'')+'.\n\nHet ophalen duurt ongeveer '+seconden+' seconden. Doorgaan?')){
   document.title='Magister';return;}

 var slim=students.map(function(s){return{id:s.id,roepnaam:s.roepnaam,tussenvoegsel:s.tussenvoegsel,
   achternaam:s.achternaam,lesgroepen:s.lesgroepen||[],studies:s.studies||[],klassen:s.klassen||[]}});

 // 3. Verzuim per leerling, in blokjes van 20 tegelijk.
 var parse=function(items){var out=[];(items||[]).forEach(function(item){
   var a=item.afspraak||{},lu=a.lesuur||{},dt=a.begin||'';
   (item.verantwoordingen||[]).forEach(function(v){out.push({
     date:dt?dt.slice(0,10):(v.moment||'').slice(0,10),
     time:dt?dt.slice(11,16):(v.moment||'').slice(11,16),
     code:(v.reden||{}).code||'?',period:lu.begin||null,subject:a.omschrijving||''});});});return out;};
 // Magister beperkt het aantal verzoeken: bij een lange periode of veel
 // leerlingen volgt HTTP 429. Daarom kleine blokjes met een pauze ertussen, en
 // wie toch mislukt komt in een rustiger tweede ronde. Stil verlies van een
 // hele klas is hier het gevaar, niet traagheid.
 var entries={},ids=slim.map(function(s){return s.id});
 var haalVerzuim=async function(lijst,pogingen,label){
   var mis=[];
   for(var i=0;i<lijst.length;i+=SZ){
     document.title=label+' '+Math.min(i+SZ,lijst.length)+'/'+lijst.length+'...';
     var chunk=lijst.slice(i,i+SZ);
     var res2=await Promise.all(chunk.map(function(id){
       return haal('/api/m6/leerlingen/'+id+'/verantwoordingen?begin='+b+'&einde='+e,pogingen)
         .then(function(r){
           if(!r||!r.ok){mis.push(id);return{id:id,items:null};}
           return r.json().then(function(d){return{id:id,items:d.items||[]}});})
         .catch(function(){mis.push(id);return{id:id,items:null};});}));
     res2.forEach(function(r){if(r.items!==null)entries[r.id]=parse(r.items);});
     if(i+SZ<lijst.length)await wacht(pauze);
   }
   return mis;};
 var mislukt=await haalVerzuim(ids,3,'Verzuim TL');
 if(mislukt.length){
   SZ=4;pauze=Math.max(pauze,1200);                   // rustiger tweede ronde
   mislukt=await haalVerzuim(mislukt,4,'Verzuim herkansing');
 }
 if(mislukt.length&&!confirm('Van '+mislukt.length+' van de '+ids.length+' leerlingen'
   +' lukte het verzuim niet op te halen (Magister beperkt het aantal verzoeken).'
   +'\n\nDoorgaan met de rest? Kies anders een kortere periode of een kleinere selectie.')){
   document.title='Magister';return;}


 // 4. Logboekformulieren (optioneel). Welke lijst-URL Magister hiervoor heeft,
 //    verschilt per omgeving; we proberen er een paar en onthouden de winnaar.
 var logboek={},bron='',diag=[];
 // Logboek gaat over het hele schooljaar, niet over de verzuimperiode: een
 // notitie uit juli hoort er in september nog steeds bij.
 // Ruime periode: Magister filtert hierop, en een logboek van vorig schooljaar
 // (warme overdracht in juli) is juist waar je iets aan hebt.
 var lb='1980-01-01',le='2030-01-01';
 var kandidaten=[
   function(id){return '/api/leerlingen/'+id+'/lvs/logboekformulieren?begin='+lb+'&einde='+le},
   function(id){return '/api/leerlingen/'+id+'/lvs/logboekformulieren'},
   function(id){return '/api/leerlingen/lvs/logboekformulieren?leerling='+id+'&begin='+lb+'&einde='+le},
   function(id){return '/api/leerlingen/'+id+'/logboekformulieren?begin='+lb+'&einde='+le},
   function(id){return '/api/lvs/leerlingen/'+id+'/logboekformulieren?begin='+lb+'&einde='+le}
 ];
 var lijstUit=function(d){
   if(!d)return null;
   if(Array.isArray(d))return d;
   if(Array.isArray(d.items))return d.items;
   return null;};
 var slank=function(f){return{id:f.id,omschrijving:f.omschrijving,
   aangemaaktOp:f.aangemaaktOp,eigenaar:f.eigenaar,inhoud:f.inhoud};};
 var lbIds=ids.filter(function(id){return (entries[id]||[]).length>0;});
 if(lbIds.length&&confirm('Ook de logboeken ophalen van de '+lbIds.length+' leerlingen met verzuim?\n\nDat kost ongeveer '+Math.ceil(lbIds.length/20*0.6)+' seconden extra.')){
   document.title='Logboek zoeken...';
   var werkend=null,leegMaarGeldig=null;
   for(var k=0;k<kandidaten.length&&!werkend;k++){
     var statussen=[];
     for(var t=0;t<Math.min(8,lbIds.length);t++){
       var r0=await haal(kandidaten[k](lbIds[t]),2);
       if(!r0){statussen.push('netwerkfout');continue;}
       if(!r0.ok){statussen.push('HTTP '+r0.status);continue;}   // andere leerling kan wel mogen
       var tekst0=await r0.text().catch(function(){return ''});
       var d0=null; try{d0=JSON.parse(tekst0);}catch(_){}
       var l0=lijstUit(d0);
       if(l0===null){statussen.push('200 maar geen lijst: '+(d0?Object.keys(d0).slice(0,4).join('/'):'geen json'));continue;}
       statussen.push('200 ('+l0.length+')');
       if(!leegMaarGeldig)leegMaarGeldig=kandidaten[k];
       if(l0.length){werkend=kandidaten[k];break;}
     }
     diag.push(kandidaten[k]('{id}').split('?')[0]+' → '+statussen.join(', '));
   }
   var maker=werkend||leegMaarGeldig;
   if(!maker){bron='niet gevonden';
     alert('Geen lijst-URL voor logboekformulieren gevonden. Wat de varianten teruggaven:\n\n'
       +diag.join('\n')+'\n\nDeze tekst staat ook in de app, onder het dashboard.');}
   else{
     bron=maker('{id}');
     for(var i2=0;i2<lbIds.length;i2+=SZ){
       document.title='Logboek '+Math.min(i2+SZ,lbIds.length)+'/'+lbIds.length+'...';
       var chunk2=lbIds.slice(i2,i2+SZ);
       var res3=await Promise.all(chunk2.map(function(id){
         return haal(maker(id),2)
           .then(function(r){return (r&&r.ok)?r.json():null})
           .then(function(d){return{id:id,items:lijstUit(d)||[]}})
           .catch(function(){return{id:id,items:[]}});}));
       res3.forEach(function(r){
         if(!r.items.length)return;
         var op=function(f){return (f.aangemaaktOp||f.gewijzigdOp||'')};
         logboek[r.id]=r.items.slice().sort(function(a,b){return op(b).localeCompare(op(a))})
                        .slice(0,3).map(slank);});
     }
   }
 }

 var payload={period:{begin:b,einde:e},scope:scope,students:slim,
   own_ids:ids,entries:entries,verzuim_fouten:mislukt.length,logboek:logboek,logboek_bron:bron,logboek_diag:(typeof diag!=='undefined'?diag:[]),logboek_periode:(bron?{begin:lb,einde:le}:null)};
 __TAIL__
}catch(err){document.title='Magister';alert('Fout bij ophalen: '+err);}
})();"""

_TAIL_DOWNLOAD = (
 "var blob=new Blob([JSON.stringify(payload)],{type:'application/json'});"
 "var url=URL.createObjectURL(blob);var a=document.createElement('a');"
 "a.href=url;a.download='verzuim_teamleider_'+(scope?scope.replace(/[^A-Za-z0-9]+/g,'-')+'_':'')+b+'_'+e+'.json';"
 "document.body.appendChild(a);a.click();a.remove();URL.revokeObjectURL(url);"
 "document.title='Magister';"
 "alert('Bestand gedownload ('+students.length+' leerlingen'+(bron?', logboek: '+bron:'')+'). Upload het in de app Verzuimsignalering.');"
)

# Bewust geen keepalive: de Fetch-spec begrenst een keepalive-body op 64 KB en
# een hele afdeling zit daar ruim boven — de browser meldt dat als een
# nietszeggende "TypeError: Failed to fetch". Het tabblad blijft toch open.
_TAIL_POST = (
 "document.title='Versturen...';"
 "var body=JSON.stringify(payload);"
 "var r=await fetch('__INGEST__?token=__TOKEN__',{method:'POST',"
 "headers:{'Content-Type':'text/plain;charset=UTF-8'},body:body});"
 "document.title='Magister';"
 "if(!r.ok){alert('De app antwoordde met HTTP '+r.status+' ('+Math.round(body.length/1024)"
 "+' KB verstuurd). Gebruik anders de download-variant.');return;}"
 "alert('Verzuim verstuurd ('+students.length+' leerlingen'+(bron?', logboek: '+bron:'')+'). Ga terug naar het tabblad van Verzuimsignalering.');"
)


def _bouw(tail, standaard_scope=''):
    js = _JS.replace('__TAIL__', tail).replace('__SCOPE__', standaard_scope)
    return 'javascript:' + quote(js, safe='')


def download_href(standaard_scope=''):
    """Bookmarklet die het resultaat als JSON-bestand downloadt."""
    return _bouw(_TAIL_DOWNLOAD, standaard_scope)


def post_href(ingest_url, token, standaard_scope=''):
    """Bookmarklet die het resultaat direct naar de app stuurt."""
    tail = _TAIL_POST.replace('__INGEST__', ingest_url).replace('__TOKEN__', token)
    return _bouw(tail, standaard_scope)


# ── Coördinator ───────────────────────────────────────────────────────────────
# Een vaste groep van een stuk of twintig leerlingen uit verschillende
# afdelingen, elke week opnieuw. Daarom geen vragen vooraf: de periode is deze
# week plus de drie ervoor, en de leerlingnummers haalt de bookmarklet zelf op
# bij de app. Zo blijft de knop geldig als de lijst verandert.
_JS_COORD = r"""(async()=>{
try{
 var pad=function(n){return String(n).padStart(2,'0')};
 var iso=function(d){return d.getFullYear()+'-'+pad(d.getMonth()+1)+'-'+pad(d.getDate())};
 var base=location.origin;
 var SZ=8,pauze=150,traag=false;
 var vertraag=function(){
   if(!traag){traag=true;SZ=4;pauze=900;}
   else{pauze=Math.min(pauze+400,2500);}};
 var wacht=function(ms){return new Promise(function(k){setTimeout(k,ms)})};
 var haal=async function(url,pogingen){
   for(var poging=0;poging<(pogingen||3);poging++){
     var r=await fetch(base+url,{signal:AbortSignal.timeout(20000)}).catch(function(){return null});
     if(r&&r.ok)return r;
     if(r&&(r.status===429||r.status>=500)){vertraag();await wacht(1500*(poging+1));continue;}
     return r;
   }
   return null;};
 var lijstUit=function(d){
   if(!d)return null;
   if(Array.isArray(d))return d;
   if(Array.isArray(d.items))return d.items;
   return null;};

 // 1. De leerlingnummers uit de app halen.
 document.title='Lijst ophalen...';
 var lr=await fetch('__LIJST__?token=__TOKEN__').catch(function(){return null});
 if(!lr||!lr.ok){document.title='Magister';
   alert('De app is niet bereikbaar. Staat hij open in een ander tabblad?');return;}
 var ids=((await lr.json())||{}).ids||[];
 if(!ids.length){document.title='Magister';
   alert('Er staan nog geen leerlingnummers in de app. Vul ze daar eerst in.');return;}

 // 2. Periode: deze week plus de drie ervoor.
 var vandaag=new Date();
 var maandag=new Date(vandaag); maandag.setDate(maandag.getDate()-((maandag.getDay()+6)%7));
 var start=new Date(maandag); start.setDate(start.getDate()-21);
 var b=iso(start),e=iso(vandaag);

 // 3. Naam, klas en mentor per leerling. Magister heeft die per leerling:
 //      /api/leerlingen/<id>                 naam
 //      /api/leerlingen/<id>/aanmeldingen    klas (groep.code) en studie
 //      links.mentoren                       de mentor, geen handwerk nodig
 //    Kan die route niet, dan alsnog via de zoeklijst — duurder maar altijd er.
 document.title='Leerlingen ophalen...';
 var slim=[],direct=true;
 var eenLeerling=async function(id){
   var r1=await haal('/api/leerlingen/'+id,2);
   if(!r1||!r1.ok)return null;
   var d1=await r1.json().catch(function(){return null});
   if(!d1)return null;
   var uit={id:d1.id||id,roepnaam:d1.roepnaam,tussenvoegsel:d1.tussenvoegsel,
     achternaam:d1.achternaam,lesgroepen:[],studies:[],klassen:[],mentor:''};
   var r2=await haal('/api/leerlingen/'+id+'/aanmeldingen',2);
   if(r2&&r2.ok){
     var items=((await r2.json().catch(function(){return{}}))||{}).items||[];
     var a=items.filter(function(x){return x.isHoofdAanmelding})[0]||items[0];
     if(a){
       if(a.groep&&a.groep.code)uit.klassen=[a.groep.code];
       if(a.studie&&a.studie.code)uit.studies=[a.studie.code];
       var mNaam=a.persoonlijkeMentor&&(a.persoonlijkeMentor.naam||a.persoonlijkeMentor.achternaam);
       var href=a.links&&a.links.mentoren&&a.links.mentoren.href;
       if(!mNaam&&href){
         var r3=await haal(href,2);
         if(r3&&r3.ok){
           var d3=await r3.json().catch(function(){return{}});
           var lijstM=lijstUit(d3)||[];
           if(lijstM.length)mNaam=lijstM[0].naam||
             [lijstM[0].roepnaam,lijstM[0].tussenvoegsel,lijstM[0].achternaam].filter(Boolean).join(' ');
         }
       }
       uit.mentor=mNaam||'';
     }
   }
   return uit;};
 var proef=await eenLeerling(ids[0]);
 if(!proef){direct=false;}
 else{
   slim.push(proef);
   for(var i=1;i<ids.length;i+=SZ){
     document.title='Leerlingen '+Math.min(i+SZ,ids.length)+'/'+ids.length+'...';
     var res1=await Promise.all(ids.slice(i,i+SZ).map(function(id){
       return eenLeerling(id).catch(function(){return null});}));
     res1.forEach(function(s){if(s)slim.push(s)});
     if(i+SZ<ids.length)await wacht(pauze);
   }
 }
 if(!slim.length){
   direct=false;
   var alle=[],skip=0,totaal=null;
   for(var p=0;p<120;p++){
     var rz=await haal('/api/leerlingen/zoeken?q=**&top=100&skip='+skip,2);
     if(!rz||!rz.ok)break;
     var dz=await rz.json().catch(function(){return{}});
     if(totaal===null&&typeof dz.totalCount==='number')totaal=dz.totalCount;
     var items2=dz.items||[]; if(!items2.length)break;
     alle=alle.concat(items2); skip+=items2.length;
     document.title='Leerlingen '+alle.length+(totaal?'/'+totaal:'')+'...';
     if(totaal!==null&&alle.length>=totaal)break;
     if(totaal===null&&items2.length<100)break;
   }
   var wil={}; ids.forEach(function(id){wil[id]=1});
   slim=alle.filter(function(s){return wil[s.id]}).map(function(s){
     return{id:s.id,roepnaam:s.roepnaam,tussenvoegsel:s.tussenvoegsel,achternaam:s.achternaam,
       lesgroepen:s.lesgroepen||[],studies:s.studies||[],klassen:s.klassen||[],mentor:''};});
 }
 var gevonden={}; slim.forEach(function(s){gevonden[s.id]=1});
 var kwijt=ids.filter(function(id){return !gevonden[id]});
 if(!slim.length){document.title='Magister';
   alert('Geen van deze leerlingnummers kon opgehaald worden. Kloppen de nummers?');return;}

 // 4. Verzuim, met dezelfde voorzichtigheid als bij de teamleider.
 var parse=function(items){var out=[];(items||[]).forEach(function(item){
   var a=item.afspraak||{},lu=a.lesuur||{},dt=a.begin||'';
   (item.verantwoordingen||[]).forEach(function(v){out.push({
     date:dt?dt.slice(0,10):(v.moment||'').slice(0,10),
     time:dt?dt.slice(11,16):(v.moment||'').slice(11,16),
     code:(v.reden||{}).code||'?',period:lu.begin||null,subject:a.omschrijving||''});});});return out;};
 var entries={},lijstIds=slim.map(function(s){return s.id});
 var haalVerzuim=async function(lijst,pogingen,label){
   var mis=[];
   for(var i=0;i<lijst.length;i+=SZ){
     document.title=label+' '+Math.min(i+SZ,lijst.length)+'/'+lijst.length+'...';
     var res2=await Promise.all(lijst.slice(i,i+SZ).map(function(id){
       return haal('/api/m6/leerlingen/'+id+'/verantwoordingen?begin='+b+'&einde='+e,pogingen)
         .then(function(r){
           if(!r||!r.ok){mis.push(id);return{id:id,items:null};}
           return r.json().then(function(d){return{id:id,items:d.items||[]}});})
         .catch(function(){mis.push(id);return{id:id,items:null};});}));
     res2.forEach(function(r){if(r.items!==null)entries[r.id]=parse(r.items);});
     if(i+SZ<lijst.length)await wacht(pauze);
   }
   return mis;};
 var mislukt=await haalVerzuim(lijstIds,3,'Verzuim');
 if(mislukt.length){SZ=4;pauze=Math.max(pauze,1200);
   mislukt=await haalVerzuim(mislukt,4,'Verzuim herkansing');}

 // 5. Logboek: altijd, de laatste drie per leerling.
 var logboek={},bron='';
 var lb='1980-01-01',le='2030-01-01';
 var maker=function(id){return '/api/leerlingen/'+id+'/lvs/logboekformulieren?begin='+lb+'&einde='+le};
 var slank=function(f){return{id:f.id,omschrijving:f.omschrijving,
   aangemaaktOp:f.aangemaaktOp,eigenaar:f.eigenaar,inhoud:f.inhoud};};
 for(var i3=0;i3<lijstIds.length;i3+=SZ){
   document.title='Logboek '+Math.min(i3+SZ,lijstIds.length)+'/'+lijstIds.length+'...';
   var res3=await Promise.all(lijstIds.slice(i3,i3+SZ).map(function(id){
     return haal(maker(id),2)
       .then(function(r){return (r&&r.ok)?r.json():null})
       .then(function(d){return{id:id,items:lijstUit(d)||[]}})
       .catch(function(){return{id:id,items:[]}});}));
   res3.forEach(function(r){
     if(!r.items.length)return;
     bron=maker('{id}');
     var op=function(f){return (f.aangemaaktOp||f.gewijzigdOp||'')};
     logboek[r.id]=r.items.slice().sort(function(a,b){return op(b).localeCompare(op(a))})
                    .slice(0,3).map(slank);});
   if(i3+SZ<lijstIds.length)await wacht(pauze);
 }

 var payload={period:{begin:b,einde:e},scope:'eigen lijst',students:slim,
   own_ids:lijstIds,entries:entries,verzuim_fouten:mislukt.length,
   niet_gevonden:kwijt,via:direct?'per leerling':'zoeklijst',
   logboek:logboek,logboek_bron:bron,logboek_diag:[],
   logboek_periode:{begin:lb,einde:le}};

 document.title='Versturen...';
 var body=JSON.stringify(payload);
 var r9=await fetch('__INGEST__?token=__TOKEN__',{method:'POST',
   headers:{'Content-Type':'text/plain;charset=UTF-8'},body:body});
 document.title='Magister';
 if(!r9.ok){alert('De app antwoordde met HTTP '+r9.status+'.');return;}
 alert('Klaar: '+slim.length+' leerlingen'
   +(kwijt.length?', '+kwijt.length+' nummer(s) niet gevonden':'')
   +(mislukt.length?', '+mislukt.length+' zonder verzuimgegevens':'')
   +'. Ga terug naar het tabblad van de app.');
}catch(err){document.title='Magister';alert('Fout bij ophalen: '+err);}
})();"""


def coordinator_href(ingest_url, lijst_url, token):
    """Bookmarklet voor de coördinator: haalt de eigen lijst op en stuurt terug."""
    js = (_JS_COORD.replace('__INGEST__', ingest_url)
                   .replace('__LIJST__', lijst_url)
                   .replace('__TOKEN__', token))
    return 'javascript:' + quote(js, safe='')
