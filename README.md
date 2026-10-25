# No More Clown – KING v23

Förändringar: Kontextbaserad körkortskontroll (obligatoriskt bilkörkort bort, meriterande truckkort kvar), platsangivelse i annonstext prioriteras över avvikande metadata och avstånd räknas från ortscentrum när koordinaterna motsäger placeringsorten. Datum visas på svenska. Matchningsorsak förbättrad. Kvällsskift 23:15 flaggas för kontroll av kollektivtrafik (ingen faktisk reseplanering). Separata lagringsnycklar för historik, avvisningar och daglig cache. Max fem jobb/dag och befintlig KING-design kvar.

OBS: Kräver test på Render med verkliga API-data. Extern annons kan vara förkortad och körkortskrav kan därför missas. Ingen Gmail-sändning. Uppgradering från v22 kan inte automatiskt återskapa historik eftersom den äldre versionen blandade lagringsnycklar.

## Version 24 – blockera Veterankraft
Veterankraft filtreras bort innan rangordning, i både radiesökning och regional sökning.
Kontrollen använder arbetsgivarnamn (även exempelvis "Veterankraft Halmstad AB") och ansöknings-/annonslänkar vars domän är `veterankraft.se` eller underdomäner.
Vi blockerar inte en annons bara för att Veterankraft nämns i löptexten. Blockeringen gäller företaget, inte alla seniora kandidater generellt.
Alla andra seniorfilter och max fem annonser per dag finns kvar. Dagens lokala cache har versionsuppdaterats för att förhindra återvisning av tidigare träffar.

## v26 – strikt yrkesprioritet
1. Bygg och anläggning, 2. Snickeri och träproduktion, 3. Industri och produktion, 4. Svets och metallarbete.
Först filtreras annonser mot CV-profilen och obligatoriska krav. Därefter sorteras alla kvalificerade annonser efter yrkesgrupp i ovanstående ordning; inom varje grupp avgör matchpoäng, avstånd och publicering. Visar högst fem per dag, och fyller på från nästa grupp om färre än fem finns i den högre.
Det betyder att en relevant byggannons alltid kommer före en industriannons, även om industriannonsen är närmare. Omsorg/service och lager/butik är fortsatt uteslutna. Ny cacheversion så tidigare dagssökning inte låser sorteringen.

## v27: Valbar sökning på hela CV:t
Kevin väljer i appen mellan **Prioriterade yrken (bygg först)** (standard, utesluter omsorg/service/lager/butik) och **Hela Kevins CV** (inkluderar erfarenhet från personlig assistans, omsorg, service, lager och butik). Bygg/anläggning, snickeri/träproduktion, industri/produktion och svets/metall har fortfarande prioritet i båda lägena. Båda lägena filtrerar obligatoriska körkort, seniorroller och Veterankraft. Valet påverkar sökfrågor och matchning på servern, inte bara synliga kort. Daglig cache är skild mellan lägena. Inga ansökningar skickas automatiskt.

\n## Jobb4kevin v30 – enbart platshantering
Läser arbetsort från fler strukturerade fält i Platsbanken och JobAd Links, inklusive objekt med label/name, alternativa kommunfält och kapslade GPS-koordinater. Tolkar vanliga former som "Halmstads kommun" och explicit placeringsort i annonstext. Om arbetsorten i texten skiljer sig från annonsens metadata används inte gamla koordinater. Okänd plats tas fortsatt inte med i radiesökning; vi gissar inte att jobb ligger i Halmstad. Ny dagscache-nyckel tvingar fram ny sökning efter uppdatering. Ingen annan matchningslogik eller design ändrad.

\n## v31 – endast platsfelsökning och kompletterande platsuppslag
* Räknar annonser med okänd plats **per källa** (Platsbanken / JobSearch respektive JobAd Links).
* För JobSearch-annonser med okänd arbetsort och en byggrelaterad titel görs ett begränsat försök (max 30 unika annonser per sökning) att hämta fullständig annons via JobSearch `/ad/{id}`. Uppslaget används **bara för platsfält**; övrig matchning och filter är oförändrade.
* Detaljförsök och återfunna platser redovisas i sökrapporten. Fel eller otillgänglig detaljannons leder inte till gissad arbetsort.
* Okänd plats avvisas fortfarande vid radiesökning. Inga externa annons-URL:er hämtas direkt.
* Ny dagscache för att tvinga fram färsk sökning. Befintlig historik och KING-design är kvar.

\n## v33 – källspårning och platsdiagnostik
- Ursprungskällan sätts när annonsen hämtas (`_origin`), inte genom att jämföra det visade källnamnet. Detta undviker att externa annonser som visar annan källetikett klassificeras fel.
- Orsaker till okänd plats härleds ur det ursprungliga API-objektet och räknas per unik annons.
- Diagnosen skiljer på saknad kommun/ort, ortnamn som inte känns igen och platsfält som inte kan tolkas.
- Ursprung och diagnos bevaras genom parsning, detaljuppslag och urvalsfilter.
- Diagnosfält visas i sökrapporten. Ny cacheversion för nya sökresultat.
- CV-matchning, yrkesprioritering, avståndskrav och KING-design är oförändrade.

\n## v34 – teknisk analys av platsfält
- För högst fyra olika platsformat per API-källa visas en anonymiserad struktur: namn och typer på platsfält, namn på underfält samt om kod-/koordinatfält finns.
- Urvalet tas direkt från API-svaren i respektive sökgren innan annonsen filtreras.
- Inga annons-ID:n, arbetsgivare, adresser, koordinatvärden eller annonstexter skickas i denna diagnostik.
- Rapporten visar fortfarande ursprungskälla och skäl till att arbetsorten inte kan fastställas.
- **Ingen ändring av CV-matchning, yrkesprioritering, platsacceptans eller design.**
- Nästa platsfix kan baseras på faktiska fältnamn i rapporten i stället för gissningar.

\n## v35 – synlig teknisk platsdiagnostik
En separat mörk panel med limegrön rubrik visas alltid under sökrapporten, före jobbannonserna. API:et returnerar upp till fyra olika anonymiserade platsformat per källa. Endast fältnamn, undertyp och närvaro rapporteras, inga fältvärden, adresser, arbetsgivare eller koordinater. Om exempel saknas visas en tydlig förklaring i panelen. CV-matchning, yrkesprioritering, avståndsfilter och KING-design är oförändrade. Ny dagscache används.

\n## v36 – platslistor och bekräftade kommuner
- Läser `workplace_addresses` som en lista och kontrollerar varje arbetsplats individuellt.
- Läser kommunnamn, GPS och ett litet antal verifierade SCB-kommunkoder. Okända kodsystem, däribland `municipality_concept_id`, översätts **inte** utan säkerställd mappning.
- I radiesökning väljs bara en bekräftad arbetsplats inom vald radie. Om alla kända arbetsplatser ligger utanför väljs inte annonsen. Regionval använder en arbetsplats i regionen om sådan finns.
- Ingen gissning att okänd arbetsort ligger i Halmstad. All CV-matchning, prioritering, design och diagnostikruta bevaras.
- Resultatcache får ny versionsnyckel. Riktiga API-anrop/Render måste verifieras efter publicering.

\n## v37 – körkortskrav och annonsverifiering
- Obligatoriska körkortskrav i strukturerade kvalifikationsfält (`must_have`, `requirements`, `qualifications`, `driving_license_required`) blockerar annonser även när annonstexten saknas.
- Meriterande körkort är inte diskvalificerande. Truckkort förblir separat.
- Annonskort med saknad beskrivning märks `EJ VERIFIERAD MATCH`; övriga osäkra matchningar märks för kontroll av originalannons. Ofullständiga annonser får lägre matchpoäng inom sitt yrkesområde.
- Fler alternativa källfält för sista ansökningsdag. Ansökningssätt via angiven länk/mejl visas om källan innehåller uppgifterna; inga mejl skickas.
- Ingen ändring av KING-design, CV-lägen, yrkesprioritering eller avståndsfilter.
- Kräver praktisk verifiering med riktiga API-svar och på Render.

\n## v38 – komplettering och separat granskningslista
- För högst 12 externa annonser per sökning som saknar full beskrivning görs ett begränsat korsuppslag i Platsbankens JobSearch API. Endast exakt samma titel, arbetsgivare och förenlig arbetsort får komplettera annonsen. Inga godtyckliga externa webbsidor hämtas.
- Om ett sådant exakt matchat JobSearch-svar innehåller ett obligatoriskt körkortskrav utesluts annonsen. Utan säkra uppgifter förblir annonsen i **Behöver kontrolleras**.
- Kvalificerade jobb och annonser som behöver granskas returneras som två olika API-listor. Max fem kvalificerade jobb visas; möjliga jobb räknas inte in i femman.
- Ansökningsdag och ansökningssätt hämtas från en exakt matchad fullständig annons när de finns. Inga mejl skickas.
- KING-design, prioriteringar, CV-lägen, avståndskontroll och historik bevaras.
- OBS: Begränsad automatisk komplettering kan inte verifiera varje extern originalannons. Inget krav får antas vara uppfyllt enbart från titel.

\n## v39 – annons-ID i stället för titelsökning
- För ofullständiga externa annonser används endast ett **uttryckligt JobSearch/Platsbanken-ID** eller ID från en original-URL på `arbetsformedlingen.se`. JobAd Links eget annons-ID antas aldrig vara samma ID.
- Detaljer hämtas från `https://jobsearch.api.jobtechdev.se/ad/{id}` (max 20 per sökning).
- Fullständig annons måste ha samma ID, arbetsgivare, titel och förenlig arbetsort innan krav och ansökningsuppgifter kopieras.
- Obligatoriskt körkort från den fullständiga annonsen blockerar jobbet; meriterande körkort blockerar inte.
- Om käll-ID saknas eller uppslaget misslyckas ligger annonsen fortsatt under **Behöver kontrolleras**.
- Diagnostik för saknade ID, uppslag, kompletteringar och körkortsblockeringar.
- CV-lägen, yrkesprioritering, platsfilter, KING-design och historik oförändrade.
- Ingen automatisk hämtning av godtyckliga externa webbsidor och inga mejl skickas.

\n## v40 – prioriterad detaljkontroll och heltidsfilter
- Externa annonser sorteras **bygg/anläggning, snickeri/trä, övriga** innan högst 20 säkra käll-ID-uppslag görs. Gränsen gäller fortfarande totalt per sökning.
- Annonsen visar varför den inte kunde verifieras: `Käll-ID saknas`, `Väntar på detaljkontroll (uppslagsgräns)`, `Detaljkontroll misslyckades`, `Detaljkontroll: annan annons` eller `Fullständig annons kontrollerad`.
- Nytt sökval **Endast heltidsjobb** (förvalt) eller **Alla anställningsformer**. Backend avgör omfattning från uttryckliga strukturerade fält, inte från lösa antaganden. Vid endast heltid: bekräftad deltid tas bort, okänd omfattning visas under **Behöver kontrolleras**, bekräftad heltid kan kvalificeras.
- Inställningen ingår i API-förfrågan och dagscachens nyckel.
- Visar omfattning och kontrollstatus på jobbkort. Ingen ändring av KING-design, CV-lägen, övriga filter eller historik.
- Testa mot riktiga API-svar efter publicering; olika annonskällor kan använda fler format för omfattning än de som stöds.


## v41 – global prioritering av detaljuppslag
- Externa kandidater samlas först och filtreras efter arbetsort, CV och senior/körkort innan detaljkontroll.
- **Alla** kvarvarande externa kandidater sorteras globalt efter faktisk CV-prioritet: bygg/anläggning, snickeri/trä, industri/produktion, svets/metall. Sedan görs högst 20 käll-ID-uppslag.
- Visar antal detaljuppslag, kompletteringar och körkortsblockeringar per yrkeskategori i sökrapporten.
- Annonser med obligatoriskt körkort som hittas vid detaljkontroll tas bort. Övriga uppdateras med bekräftade krav och kontrolleras på nytt mot CV.
- Heltidsfiltret från v40 är oförändrat: deltid bort, okänd omfattning till Behöver kontrolleras.
- Ingen garanti att en viss extern annons har ett användbart Platsbanken-ID.


## v42 – okänd arbetstid kan visas i topp fem
- **Endast heltidsjobb** är fortfarande förvalt. Bekräftad deltid sorteras bort.
- Okänd arbetstid diskvalificerar inte längre ett jobb från de fem bästa. Det måste fortfarande klara CV-matchning, körkortskrav, seniorfilter, platskontroll och verifieringskontroll.
- Jobbkort med okänd arbetstid visar tydligt **⚠️ Arbetstid ej bekräftad**.
- Jobb med ofullständig annons eller oklara körkortskrav ligger fortfarande i **Behöver kontrolleras**.
- Global detaljprioritering, KING-design och övriga filter är oförändrade.


## v43 – försiktig körkortsklassificering och anonymiserad evidens
- Tydligare åtskillnad mellan obligatoriskt körkort, meriterande körkort och truckkort i strukturerade kvalifikationsfält.
- Blockering vid detaljuppslag sker först efter att annonsens ID, titel och arbetsgivare har kontrollerats. Annons med ofullständiga uppgifter fortsätter till Behöver kontrolleras.
- Diagnostik redovisar antal blockerade annonser per källa/fältnamn och beslutstyp, utan annonsinnehåll eller personuppgifter.
- Heltidsfilter v42, globala yrkesprioriteringen och KING-designen är oförändrade.
- API-verifiering och Render-test återstår.


## v44 – spårbar körkortskontroll
- Strukturerat obligatoriskt körkort och uttryckligen meriterande körkort i samma annons behandlas som **motsägelse**, inte som ett säkert avslag. Annonsen flyttas till **Behöver kontrolleras**.
- Otvetydigt obligatoriskt körkort blockerar fortfarande. Truckkort hanteras separat.
- En separat panel **KÖRKORTSKONTROLL** visar anonymiserade kontrollrader för varje detaljbeslut (yrkeskategori, beslut, fältnamn, typ av belägg) och antal motsägelser.
- Heltidsfilter, yrkesprioritering, CV-lägen, platshantering och KING-design bevaras.
- API-fält kan variera mellan källor. Resultatet behöver testas mot riktiga annonser på Render.


## v45 – kravstatus per annons
- Varje jobbkort, även under **Behöver kontrolleras**, visar fem separata kontrollrader: körkort, erfarenhet, arbetstid, ansökningssätt och annonsunderlag.
- Kontrollraderna skiljer mellan belagt, okänt och sådant som måste granskas. Lång annonstext är inte i sig ett bevis för att erfarenhetskraven är uppfyllda.
- Saknade uppgifter visas uttryckligen i stället för enbart en allmän varning.
- Heltidsfiltret, yrkesprioriteringen, käll-ID-uppslagen, körkortsblockeringen, geografiska filter och KING-designen ändras inte.
- Ny lokal cacheversion. Ingen extern ansökan eller e-post skickas automatiskt.
