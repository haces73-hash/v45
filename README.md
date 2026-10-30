Jobb4kevin v50 – Versionsbunden sökcache, automatisk rensning av gamla sökresultat, knapp för sökcache-rensning och tidsstämpel för senaste lyckade sökning. Historik och avböjanden behålls. Uppdatera befintlig Render-tjänst, skapa ingen ny Blueprint.

## v51
- Knappen heter MARKERA SOM ANSÖKT tills användaren själv bekräftar en skickad ansökan.
- NEJ TACK döljer jobbkortet direkt, även efter en manuell omsökning samma svenska kalenderdag.
- Samma annons kan visas igen en annan kalenderdag, högst tills den avböjts tre gånger.
- Efter tredje avböjningen döljs annonsen permanent på denna enhet/webbläsare.
- Historik och avböjningar ligger kvar vid rensning av sökcache.
- Äldre avböjningar migreras utan att deras antal förloras.

## v52
- NEJ TACK ritar alltid om jobblistan, även när annonsen redan avböjts samma dag.
- Dagens avböjning räknas bara en gång och samma jobb återkommer inte förrän nästa dag.
- Historik och tre-avböjningar-regeln bevaras.

## v53
- Dagens fem bäst matchade jobb är en fast lista per kalenderdag (svensk tid) och valda sökinställningar.
- NEJ TACK tar bort jobbkortet direkt, utan automatisk påfyllning. Två avböjningar lämnar tre av fem jobb kvar.
- Manuell sökning och rensning av sökcache fyller inte på dagens fasta lista.
- En ny svensk kalenderdag får en ny lista med upp till fem jobb; tidigare avböjningar kan återkomma på senare dagar, högst två gånger till.
- Byte av sökinställningar ger en egen fast lista för de inställningarna.
- Den fasta listan, historik och avböjningar sparas lokalt i samma webbläsare.

## v54 – Kevins uppdaterade CV och personliga brev
- PDF- och Word-kopior av godkänt personligt brev och nytt CV utan körkortsuppgift ingår under static/ och kan öppnas från startsidan.
- Nya genomförda utbildningar och kompetenser vägs in som en begränsad positiv matchningssignal när annonstexten nämner dem. De ersätter inte kontroll av obligatoriska krav.
- Erfarenhetstexten anger byggutbildning Movant avslutad 6 november 2026.
- Körkortsfilter är kvar internt men ingen uppgift om avsaknad av körkort skrivs i CV.
- v53-regeln om fast lista och NEJ TACK utan automatisk påfyllning behålls.
- Obs: v54 uppdaterar lokal sökcache, men bevarar v53:s fasta dagslista samt ansöknings- och avböjningshistorik.
