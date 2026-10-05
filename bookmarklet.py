"""
bookmarklet.py — genereert de bladwijzer die het verzuim uit Magister haalt.

Het verzuim komt niet op de server. Zo werkt het:

1. De bladwijzer draait in het tabblad waar de gebruiker zélf in Magister is
   ingelogd. Same-origin: geen CORS en geen Magister-wachtwoord op de server.
2. Hij opent meteen het rapportvenster (rapport.html, zie rapport.py). Dat moet
   bij de klik zelf, anders houdt de pop-upblokker het tegen. De periode en de
   selectie kies je daarom in dat venster, niet met prompt().
3. Het venster vraagt via postMessage om de gegevens; de bladwijzer haalt ze op
   en stuurt ze terug, alleen naar de origin van het rapportvenster. Het venster
   rekent het dashboard uit en mag zelf niets versturen (CSP).

Van de app haalt de bladwijzer alleen dingen die geen leerlinggegevens zijn:
de instellingen (codes, mentornamen, grenzen), de leerlingnummers van de
coördinator en klaargezette logboeknotities. Terug naar de app gaat alleen per
notitie of het schrijven gelukt is.

Eén bladwijzer-code voor beide pagina's; alleen de start-modus verschilt
(`#tl` teamleider, `#coord` coördinator). In het venster kun je wisselen.

Let op de snelheid: Magister geeft HTTP 429 als er te veel verzoeken tegelijk
binnenkomen. Daarom kleine blokjes met een pauze ertussen, opnieuw proberen bij
429, en een tweede ronde voor wie dan nog mislukt. Zonder dat verdween er stil
een hele klas uit het overzicht.

Logboekformulieren (LVS):

    /api/leerlingen/<id>/lvs/logboekformulieren?begin=1980-01-01&einde=2030-01-01

Ruime periode: een notitie van vorig schooljaar (de warme overdracht in juli) is
juist bruikbaar. Bij de teamleider worden alleen leerlingen mét verzuim bevraagd.
Mocht de URL in een andere omgeving anders heten, dan probeert de bladwijzer nog
vier varianten op de eerste leerlingen; welke werkte meldt het venster.
"""

import json
from urllib.parse import quote

_JS = r"""(()=>{
 var RAPPORT=__RAPPORT__,ORIG=new URL(RAPPORT).origin,APP=__APP__,TOKEN=__TOKEN__;
 var w=window.open(RAPPORT+'#__MODUS__','verzuimsignalering');
 if(!w){alert('Je browser hield het venster van Verzuimsignalering tegen. Sta pop-ups toe voor Magister en klik opnieuw op de bladwijzer.');return;}
 if(window.__vzsLuistert)return;
 window.__vzsLuistert=true;
 var base=location.origin;
 var pad=function(n){return String(n).padStart(2,'0')};
 var iso=function(d){return d.getFullYear()+'-'+pad(d.getMonth()+1)+'-'+pad(d.getDate())};
 var wacht=function(ms){return new Promise(function(k){setTimeout(k,ms)})};
 var SZ=6,pauze=250;
 // Magister staat maar een beperkt aantal verzoeken toe. Pauze die alleen
 // oploopt als er tóch een 429 komt.
 var vertraag=function(){pauze=Math.min(pauze+400,3000);};
 var haal=async function(url,pogingen){
   for(var poging=0;poging<(pogingen||3);poging++){
     var r=await fetch(base+url,{signal:AbortSignal.timeout(20000)}).catch(function(){return null});
     if(r&&r.ok)return r;
     if(r&&r.status===429){vertraag();await wacht(30000);continue;}
     if(r&&r.status>=500){await wacht(1500*(poging+1));continue;}
     return r;                       // andere fout: opnieuw proberen helpt niet
   }
   return null;};
 var jget=async function(u){try{var r=await fetch(base+u,{signal:AbortSignal.timeout(20000)});
   if(r.status===204)return{};var t=await r.text();return t&&t.trim()?JSON.parse(t):{};}catch(_){return{};}};
 var lijstUit=function(d){
   if(!d)return null;
   if(Array.isArray(d))return d;
   if(Array.isArray(d.items))return d.items;
   return null;};
 var slank=function(f){return{id:f.id,omschrijving:f.omschrijving,
   aangemaaktOp:f.aangemaaktOp,eigenaar:f.eigenaar,inhoud:f.inhoud};};
 var nieuwste=function(items){
   var op=function(f){return (f.aangemaaktOp||f.gewijzigdOp||'')};
   return items.slice().sort(function(a,b){return op(b).localeCompare(op(a))}).slice(0,3).map(slank);};
 // Magister geeft per leerling de afspraken met hun verantwoordingen terug, en
 // vertelt er zelf bij wat een code betekent en of hij geoorloofd is. 'Present'
 // slaan we over: aanwezigheid wordt ook geregistreerd en is verreweg het meeste.
 var parse=function(d){var out=[];((d&&d.afspraken)||[]).forEach(function(a){
   var dt=a.begin||'';
   (a.verantwoordingen||[]).forEach(function(v){
     var reden=v.reden||{};
     if(!reden.code||reden.type==='present')return;
     var r={
       date:dt?dt.slice(0,10):'',time:dt?dt.slice(11,16):'',
       code:reden.code,period:a.lesuurBegin||null,subject:a.omschrijving||'',
       naam:reden.omschrijving||'',type:reden.type||''};
     if(typeof reden.isGeoorloofd==='boolean')r.geoorloofd=reden.isGeoorloofd;
     out.push(r);});});return out;};
 var haalVerzuim=async function(lijst,b,e,entries,pogingen,label,meld){
   var mis=[];
   for(var i=0;i<lijst.length;i+=SZ){
     meld(label,Math.min(i+SZ,lijst.length),lijst.length);
     var chunk=lijst.slice(i,i+SZ);
     var res=await Promise.all(chunk.map(function(id){
       return haal('/api/m6/leerlingen/'+id+'/verantwoordingen/afwezigheidsredenen?begin='+b+'&einde='+e,pogingen)
         .then(function(r){
           if(!r||!r.ok){mis.push(id);return{id:id,data:null};}
           return r.json().then(function(d){return{id:id,data:d}});})
         .catch(function(){mis.push(id);return{id:id,data:null};});}));
     res.forEach(function(r){if(r.data!==null)entries[r.id]=parse(r.data);});
     if(i+SZ<lijst.length)await wacht(pauze);
   }
   return mis;};

 // Van de app: instellingen, leerlingnummers, klaargezette notities. Geen
 // leerlinggegevens; die gaan nooit die kant op.
 var inVlucht=null;
 var vraagApp=function(){
   if(!inVlucht){
     inVlucht=fetch(APP+'?token='+TOKEN,{signal:AbortSignal.timeout(10000)})
       .then(function(r){return r.ok?r.json():{ok:false,status:r.status}})
       .catch(function(){return{ok:false}})
       .finally(function(){setTimeout(function(){inVlucht=null},1500)});
   }
   return inVlucht;};

 // ── Teamleider: een afdeling of leerjaar ──────────────────────────────────
 var teamleider=async function(m,meld){
   var b=m.begin,e=m.einde,scope=String(m.scope||'').trim(),meldingen=[];
   var filters=scope?scope.split(',').map(function(s){return s.trim().toUpperCase()}).filter(Boolean):[];
   var alle=[],gezien={};
   var voegToe=function(items){
     var nieuw=0;
     (items||[]).forEach(function(s){if(!gezien[s.id]){gezien[s.id]=1;alle.push(s);nieuw++;}});
     return nieuw;};
   // Zoeken op de selectie zelf ('H5') geeft in één verzoek alle leerlingen
   // van dat leerjaar; alleen zonder selectie moet de hele school gepagineerd.
   for(var fi=0;fi<filters.length;fi++){
     meld('Leerlingen zoeken ('+filters[fi]+')');
     var q=encodeURIComponent(filters[fi]),gehaald=0,verwacht=null;
     for(var pz=0;pz<40;pz++){
       var rz=await jget('/api/leerlingen/zoeken?q='+q+'&top=200&skip='+gehaald);
       var items=rz.items||[];
       if(verwacht===null&&typeof rz.totalCount==='number')verwacht=rz.totalCount;
       if(!items.length)break;
       voegToe(items);
       gehaald+=items.length;
       if(verwacht!==null&&gehaald>=verwacht)break;
       if(verwacht===null&&items.length<200)break;
     }
     if(verwacht!==null&&gehaald<verwacht)
       meldingen.push('Voor "'+filters[fi]+'" gaf Magister '+gehaald+' van de '+verwacht+' leerlingen terug. De lijst is dus onvolledig.');
   }
   if(!alle.length){                                   // geen selectie, of niets gevonden
     var skip=0,TOP=100,totaal=null,paginas=0;
     for(var p=0;p<120;p++){
       var res=await jget('/api/leerlingen/zoeken?q=**&top='+TOP+'&skip='+skip);
       var items2=res.items||[];
       if(totaal===null){
         var t=[res.totalCount,res.totaalAantal,res.count,res.total];
         for(var ti=0;ti<t.length;ti++){if(typeof t[ti]==='number'){totaal=t[ti];break;}}
       }
       if(!items2.length)break;
       paginas++;
       var nieuw=voegToe(items2);
       skip+=items2.length;
       meld('Leerlingen',alle.length,totaal);
       if(!nieuw)break;
       if(totaal!==null){if(alle.length>=totaal)break;}
       else if(items2.length<TOP)break;
     }
     if(totaal!==null&&alle.length<totaal)
       meldingen.push('Magister gaf '+alle.length+' van de '+totaal+' leerlingen terug ('+paginas+' pagina\'s). De lijst is dus onvolledig.');
   }
   if(!alle.length)throw new Error('Geen leerlingen gevonden. Ben je in Magister ingelogd als docent of teamleider?');
   var past=function(s){
     if(!filters.length)return true;
     var labels=[].concat(s.klassen||[],s.studies||[]).map(function(x){return String(x).toUpperCase()});
     return labels.some(function(l){return filters.some(function(f){return l.indexOf(f)===0})});};
   var students=alle.filter(past);
   if(!students.length)throw new Error('Van de '+alle.length+' leerlingen past er geen op "'+scope+'". Kijk hoe de klassen in Magister heten (bijv. H4A) en probeer een andere selectie.');
   var slim=students.map(function(s){return{id:s.id,roepnaam:s.roepnaam,tussenvoegsel:s.tussenvoegsel,
     achternaam:s.achternaam,lesgroepen:s.lesgroepen||[],studies:s.studies||[],klassen:s.klassen||[]}});
   var ids=slim.map(function(s){return s.id}),entries={};
   var mislukt=await haalVerzuim(ids,b,e,entries,3,'Verzuim',meld);
   if(mislukt.length){
     pauze=Math.max(pauze,2000);                        // rustiger tweede ronde
     mislukt=await haalVerzuim(mislukt,b,e,entries,4,'Verzuim herkansing',meld);
   }
   // Logboekformulieren. Welke lijst-URL Magister hiervoor heeft, verschilt per
   // omgeving; we proberen er een paar en onthouden de winnaar.
   var logboek={},bron='',diag=[],lb='1980-01-01',le='2030-01-01';
   var lbIds=ids.filter(function(id){return (entries[id]||[]).length>0;});
   if(m.logboek&&lbIds.length){
     var kandidaten=[
       function(id){return '/api/leerlingen/'+id+'/lvs/logboekformulieren?begin='+lb+'&einde='+le},
       function(id){return '/api/leerlingen/'+id+'/lvs/logboekformulieren'},
       function(id){return '/api/leerlingen/lvs/logboekformulieren?leerling='+id+'&begin='+lb+'&einde='+le},
       function(id){return '/api/leerlingen/'+id+'/logboekformulieren?begin='+lb+'&einde='+le},
       function(id){return '/api/lvs/leerlingen/'+id+'/logboekformulieren?begin='+lb+'&einde='+le}];
     meld('Logboek zoeken');
     var werkend=null,leegMaarGeldig=null;
     for(var k=0;k<kandidaten.length&&!werkend;k++){
       var statussen=[];
       for(var t2=0;t2<Math.min(8,lbIds.length);t2++){
         var r0=await haal(kandidaten[k](lbIds[t2]),2);
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
     if(!maker){bron='niet gevonden';}
     else{
       bron=maker('{id}');
       for(var i2=0;i2<lbIds.length;i2+=SZ){
         meld('Logboek',Math.min(i2+SZ,lbIds.length),lbIds.length);
         var res3=await Promise.all(lbIds.slice(i2,i2+SZ).map(function(id){
           return haal(maker(id),2)
             .then(function(r){return (r&&r.ok)?r.json():null})
             .then(function(d){return{id:id,items:lijstUit(d)||[]}})
             .catch(function(){return{id:id,items:[]}});}));
         res3.forEach(function(r){if(r.items.length)logboek[r.id]=nieuwste(r.items);});
       }
     }
   }
   return{period:{begin:b,einde:e},scope:scope,students:slim,own_ids:ids,entries:entries,
     verzuim_fouten:mislukt.length,logboek:logboek,logboek_bron:bron,logboek_diag:diag,
     logboek_periode:(bron&&bron!=='niet gevonden'?{begin:lb,einde:le}:null),meldingen:meldingen};
 };

 // ── Coördinator: een eigen lijst leerlingnummers ──────────────────────────
 // Periode: deze week plus de drie ervoor. Naam, klas en mentor per leerling:
 //   /api/leerlingen/<id>               naam
 //   /api/leerlingen/<id>/aanmeldingen  klas (groep.code) en studie
 //   links.mentoren                     de mentor
 // Kan die route niet, dan alsnog via de zoeklijst — trager, zonder mentor.
 var coordinator=async function(m,meld){
   meld('Lijst ophalen bij de app');
   var app=await vraagApp();
   if(!app||!app.ok)throw new Error('De app Verzuimsignalering is niet bereikbaar, dus de leerlingnummers ook niet. Open de app en probeer het opnieuw.');
   var ids=app.ids||[];
   if(!ids.length)throw new Error('Er staan nog geen leerlingnummers in de app. Vul ze daar eerst in.');
   var vandaag=new Date();
   var ma=new Date(vandaag); ma.setDate(ma.getDate()-((ma.getDay()+6)%7));
   var start=new Date(ma); start.setDate(start.getDate()-21);
   var b=iso(start),e=iso(vandaag);
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
             var lijstM=lijstUit(await r3.json().catch(function(){return{}}))||[];
             if(lijstM.length)mNaam=lijstM[0].naam||
               [lijstM[0].roepnaam,lijstM[0].tussenvoegsel,lijstM[0].achternaam].filter(Boolean).join(' ');
           }
         }
         uit.mentor=mNaam||'';
       }
     }
     return uit;};
   meld('Leerlingen',0,ids.length);
   var proef=await eenLeerling(ids[0]);
   if(!proef){direct=false;}
   else{
     slim.push(proef);
     for(var i=1;i<ids.length;i+=SZ){
       meld('Leerlingen',Math.min(i+SZ,ids.length),ids.length);
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
       var dz=await jget('/api/leerlingen/zoeken?q=**&top=100&skip='+skip);
       if(totaal===null&&typeof dz.totalCount==='number')totaal=dz.totalCount;
       var items2=dz.items||[]; if(!items2.length)break;
       alle=alle.concat(items2); skip+=items2.length;
       meld('Leerlingen zoeken',alle.length,totaal);
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
   if(!slim.length)throw new Error('Geen van deze leerlingnummers kon opgehaald worden. Kloppen de nummers?');
   var entries={},lijstIds=slim.map(function(s){return s.id});
   var mislukt=await haalVerzuim(lijstIds,b,e,entries,3,'Verzuim',meld);
   if(mislukt.length){pauze=Math.max(pauze,1200);
     mislukt=await haalVerzuim(mislukt,b,e,entries,4,'Verzuim herkansing',meld);}
   var logboek={},bron='',lb='1980-01-01',le='2030-01-01';
   var maker=function(id){return '/api/leerlingen/'+id+'/lvs/logboekformulieren?begin='+lb+'&einde='+le};
   for(var i3=0;i3<lijstIds.length;i3+=SZ){
     meld('Logboek',Math.min(i3+SZ,lijstIds.length),lijstIds.length);
     var res3=await Promise.all(lijstIds.slice(i3,i3+SZ).map(function(id){
       return haal(maker(id),2)
         .then(function(r){return (r&&r.ok)?r.json():null})
         .then(function(d){return{id:id,items:lijstUit(d)||[]}})
         .catch(function(){return{id:id,items:[]}});}));
     res3.forEach(function(r){if(!r.items.length)return;bron=maker('{id}');logboek[r.id]=nieuwste(r.items);});
     if(i3+SZ<lijstIds.length)await wacht(pauze);
   }
   return{period:{begin:b,einde:e},scope:'eigen lijst',students:slim,own_ids:lijstIds,
     entries:entries,verzuim_fouten:mislukt.length,niet_gevonden:kwijt,
     via:direct?'per leerling':'zoeklijst',logboek:logboek,logboek_bron:bron,logboek_diag:[],
     logboek_periode:{begin:lb,einde:le},meldingen:[]};
 };

 // ── Logboeknotities schrijven ─────────────────────────────────────────────
 // De enige plek die iets wijzigt in Magister. Alleen wat in de wachtrij van
 // de app staat; het venster kiest welke (na bevestiging daar). Elke opdracht
 // heeft een sleutel, de app haalt gelukte uit de wachtrij: niets dubbel.
 var schrijf=async function(m,meld){
   var app=await vraagApp();
   if(!app||!app.ok)throw new Error('De app is niet bereikbaar; er is niets geschreven.');
   var wil={}; (m.sleutels||[]).forEach(function(s){wil[s]=1});
   var opdrachten=(app.schrijf||[]).filter(function(o){return wil[o.sleutel]});
   var geschreven=[];
   for(var oi=0;oi<opdrachten.length;oi++){
     var o=opdrachten[oi];
     meld('Logboek schrijven',oi+1,opdrachten.length);
     var lichaam={aangemaaktOp:new Date().toISOString(),bovenliggendeId:null,
       formuliertypeId:o.typeId,heeftPrioriteit:false,inhoud:o.inhoud,
       isAfgerond:false,omschrijving:o.titel,verlooptOp:null,
       waarden:{bstVeld1:null,bstVeld2:null}};
     var rs=await fetch(base+'/api/leerlingen/'+encodeURIComponent(o.leerlingId)+'/lvs/logboekformulieren',
       {method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify(lichaam),signal:AbortSignal.timeout(20000)})
       .catch(function(){return null});
     var fout='';
     if(!rs)fout='netwerkfout';
     else if(!(rs.status>=200&&rs.status<300))fout='HTTP '+rs.status+' '+(await rs.text().catch(function(){return''})).slice(0,120);
     geschreven.push({sleutel:o.sleutel,ok:!fout,fout:fout});
     await wacht(400);
   }
   var ra=await fetch(APP+'?token='+TOKEN+'&schrijf=1',{method:'POST',
     headers:{'Content-Type':'text/plain;charset=UTF-8'},
     body:JSON.stringify({geschreven:geschreven})}).catch(function(){return null});
   inVlucht=null;
   return{geschreven:geschreven,gemeld:!!(ra&&ra.ok)};
 };

 var bezig=false;
 window.addEventListener('message',async function(ev){
   if(ev.origin!==ORIG||!ev.data||!ev.source)return;
   var src=ev.source,stuur=function(m){try{src.postMessage(m,ORIG)}catch(_){}},m=ev.data;
   if(m.type==='vzs-ready'){stuur({type:'vzs-hallo',app:await vraagApp()});return;}
   var taak={'vzs-ophalen':m.modus==='coord'?coordinator:teamleider,'vzs-schrijf':schrijf}[m.type];
   if(!taak)return;
   if(bezig){stuur({type:'vzs-fout',melding:'Er loopt al een ophaalronde. Wacht tot die klaar is.'});return;}
   if(m.type==='vzs-ophalen'&&m.modus!=='coord'){
     var re=/^\d{4}-\d{2}-\d{2}$/;
     if(!re.test(m.begin)||!re.test(m.einde)){stuur({type:'vzs-fout',melding:'Ongeldige datum.'});return;}
   }
   bezig=true;
   var meld=function(tekst,klaar,totaal){stuur({type:'vzs-voortgang',tekst:tekst,klaar:klaar,totaal:totaal});};
   try{
     var uit=await taak(m,meld);
     stuur(m.type==='vzs-schrijf'?{type:'vzs-geschreven',uitslag:uit}
                                 :{type:'vzs-data',modus:m.modus,payload:uit});
   }catch(err){stuur({type:'vzs-fout',melding:String(err&&err.message||err)});}
   finally{bezig=false;}
 });
})();"""


def href(rapport_url, app_url, token, modus='tl'):
    """De bladwijzer. `modus` is de pagina waarop het venster opent: tl of coord."""
    js = (_JS.replace('__RAPPORT__', json.dumps(rapport_url))
             .replace('__APP__', json.dumps(app_url))
             .replace('__TOKEN__', json.dumps(token))
             .replace('__MODUS__', 'coord' if modus == 'coord' else 'tl'))
    return 'javascript:' + quote(js, safe='')
