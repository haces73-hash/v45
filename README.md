Jobb4kevin v60 – stabilisering för Render

Orsak i Render Events: /health timeout efter 5 sekunder.

Ändringar:
- En enda jobbsökning åt gången för att skydda begränsade resurser.
- Max 12 externa detaljkontroller per sökning och begränsade regionala API-frågor. Det kan minska antalet annonser i breda regionala sökningar.
- /health är fristående från externa API-anrop.
- Gunicorn med 1 gthread-worker och 8 trådar så hälsokontroller kan svara under jobbsökning.
- Flask, requests, gunicorn och Procfile ingår.
- Dokument och historikhantering oförändrade.

Render-inställningar:
Build Command: pip install -r requirements.txt
Start Command: gunicorn --bind 0.0.0.0:$PORT --workers 1 --worker-class gthread --threads 8 --timeout 120 --graceful-timeout 30 app:app
Health Check Path: /health

OBS: Render Free kan fortfarande sova vid inaktivitet och orsaka lång första laddning.
Historik som sparas i webbläsaren påverkas inte av serverfilerna, men versionens sökcache förnyas.

Version 61: Förtydligad Word-knapp för originalets personliga brev. Render-stabilisering från v60 oförändrad.


Version 62: Mobil PDF-granskning med synlig Tillbaka-knapp, Skriv ut PDF, Dela/Spara PDF och Öppna externt. iPhone-utskrift kan kräva Safari/Braves delningsmeny; utskrift från inbäddad PDF beror på webbläsaren. Render-stabilisering från v60/v61 oförändrad.

Version 63: PDF-visaren har endast två knappar: TILLBAKA TILL APPEN och DELA / SPARA PDF. Separata knappar för utskrift och extern öppning borttagna.
