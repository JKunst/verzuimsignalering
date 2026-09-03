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
