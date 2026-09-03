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

Optioneel haalt hij ook de logboekformulieren op (LVS):

    /api/leerlingen/<id>/lvs/logboekformulieren?begin=2026-08-01&einde=2027-07-31

Die vraagt om een periode, en dat is bewust het hele schooljaar: een notitie uit
juli hoort in september nog steeds bij de leerling. Mocht die URL in een andere
omgeving anders heten, dan probeert de bookmarklet nog een paar varianten op de
eerste leerlingen; welke werkte komt in `logboek_bron` terug en toont de app.

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
 var jget=async function(u){try{var r=await fetch(u,{signal:AbortSignal.timeout(20000)});
   if(r.status===204)return{};var t=await r.text();return t&&t.trim()?JSON.parse(t):{};}catch(_){return{};}};

 // 1. Leerlingen ophalen (gepagineerd; stopt zodra er niets nieuws meer bijkomt).
 document.title='Leerlingen ophalen...';
 var alle=[],gezien={},skip=0,TOP=200;
 for(var p=0;p<40;p++){
   var res=await jget(base+'/api/leerlingen/zoeken?q=**&top='+TOP+'&skip='+skip);
   var items=res.items||[]; if(!items.length)break;
   var nieuw=0;
   items.forEach(function(s){if(!gezien[s.id]){gezien[s.id]=1;alle.push(s);nieuw++;}});
   if(!nieuw||items.length<TOP)break;
   skip+=items.length;
 }
 if(!alle.length){document.title='Magister';
   alert('Geen leerlingen gevonden.\n\nBen je hier ingelogd als docent/teamleider? Open eerst Magister en probeer het opnieuw.');return;}

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
 var entries={},ids=slim.map(function(s){return s.id}),SZ=20;
 for(var i=0;i<ids.length;i+=SZ){
   document.title='Verzuim TL '+Math.min(i+SZ,ids.length)+'/'+ids.length+'...';
   var chunk=ids.slice(i,i+SZ);
   var res2=await Promise.all(chunk.map(function(id){
     return fetch(base+'/api/m6/leerlingen/'+id+'/verantwoordingen?begin='+b+'&einde='+e,
       {signal:AbortSignal.timeout(20000)}).then(function(r){return r.json()})
       .then(function(d){return{id:id,items:d.items||[]}}).catch(function(){return{id:id,items:[]}});}));
   res2.forEach(function(r){entries[r.id]=parse(r.items);});}


 // 4. Logboekformulieren (optioneel). Welke lijst-URL Magister hiervoor heeft,
 //    verschilt per omgeving; we proberen er een paar en onthouden de winnaar.
 var logboek={},bron='';
 // Logboek gaat over het hele schooljaar, niet over de verzuimperiode: een
 // notitie uit juli hoort er in september nog steeds bij.
 var eJaar=parseInt(e.slice(0,4),10),eMaand=parseInt(e.slice(5,7),10);
 var jaar1=(eMaand>=8)?eJaar:eJaar-1;
 var lb=jaar1+'-08-01',le=(jaar1+1)+'-07-31';
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
 if(confirm('Ook de logboekformulieren ophalen (schooljaar '+jaar1+'-'+(jaar1+1)+')?\n\nDat kost ongeveer '+seconden+' seconden extra.')){
   document.title='Logboek zoeken...';
   var werkend=null,leegMaarGeldig=null;
   for(var k=0;k<kandidaten.length&&!werkend;k++){
     for(var t=0;t<Math.min(6,ids.length);t++){
       var r0=await fetch(base+kandidaten[k](ids[t]),{signal:AbortSignal.timeout(20000)}).catch(function(){return null});
       if(!r0||!r0.ok)break;
       var d0=await r0.json().catch(function(){return null});
       var l0=lijstUit(d0);
       if(l0===null)break;
       if(!leegMaarGeldig)leegMaarGeldig=kandidaten[k];
       if(l0.length){werkend=kandidaten[k];break;}
     }
   }
   var maker=werkend||leegMaarGeldig;
   if(!maker){bron='niet gevonden';}
   else{
     bron=maker('{id}');
     for(var i2=0;i2<ids.length;i2+=SZ){
       document.title='Logboek '+Math.min(i2+SZ,ids.length)+'/'+ids.length+'...';
       var chunk2=ids.slice(i2,i2+SZ);
       var res3=await Promise.all(chunk2.map(function(id){
         return fetch(base+maker(id),{signal:AbortSignal.timeout(20000)})
           .then(function(r){return r.ok?r.json():null})
           .then(function(d){return{id:id,items:lijstUit(d)||[]}})
           .catch(function(){return{id:id,items:[]}});}));
       res3.forEach(function(r){if(r.items.length)logboek[r.id]=r.items.map(slank);});
     }
   }
 }

 var payload={period:{begin:b,einde:e},scope:scope,students:slim,
   own_ids:ids,entries:entries,logboek:logboek,logboek_bron:bron,logboek_periode:(bron?{begin:lb,einde:le}:null)};
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
