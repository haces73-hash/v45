# B 1.32 – förberett skarpt e-postläge

## Standard: test, inga arbetsgivarmejl

GMAIL_SEND_MODE saknas eller har annat värde än live: testläge används och endast haces@hotmail.com kan få mejl. Publicering av denna version aktiverar inte skarpa mejl. Befintlig Gmail-inloggning och krypterad lagring behålls.

## Efter separat beslut att gå skarpt

Sätt GMAIL_SEND_MODE till live i Render Environment och publicera om. Gör detta först efter godkänd slutkontroll och separat beslut att aktivera. Ändra tillbaka till test för att stänga av skarpa mejl.

Skarpt läge:
- Granskningssidan visar faktisk arbetsgivarmottagare, avsändare, brev, ämne och CV.
- Knappen heter Bekräfta och skicka ansökan; en sista dialog namnger mottagare och avsändare.
- Servern kräver att klientens granskade läge matchar aktuellt serverläge samt att granskad avsändare matchar anslutet Gmail.
- Originalannonsen hämtas på nytt. Endast strukturerad ansökningsadress från ett verifierat numeriskt JobSearch-ID används. Ändrad/ogiltig/saknad adress, extern ansökningslänk och otillgängligt original stoppar sändning.
- Inget testprefix eller testmeddelande i mejlet. CV bifogas som tidigare.
- Bekräftad sändning märks Ansökan skickad till mottagaren i historiken och jobbet filtreras bort.
- Ingen automatisk omsändning görs vid oklar status. Kontrollera Skickat i Gmail före nytt försök.

Avsändaren måste vara Kevins konto när han söker. Google-projektets test-/publiceringsstatus är separat från GMAIL_SEND_MODE; Google-inställningar kan fortfarande kräva testanvändare eller förnyat godkännande. B 1.32 ändrar inte Google-projektet.

## Verifierat och kvar

Mockade backendtester kontrollerar test som standard, felskrivet läge, modebyte, avsändarbyte, serverkontrollerad mottagare, rätt ämne och frånvaro av testtext i live-MIME. Inga verkliga mejl till arbetsgivare skickades.

Manuell slutkontroll av UI i testläge och beslut om aktivering återstår. Frontsidan är fortfarande ett separat arbete före release. Den manuella kontrollen av borttagen annons i historik avvaktar verkligt fall.
