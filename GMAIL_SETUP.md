> **Render Free, B 1.15:** Följ [FREE_GMAIL_SETUP.md](FREE_GMAIL_SETUP.md) för extern PostgreSQL utan betald Render-disk. Diskstegen nedan gäller bara det äldre SQLite-alternativet.

# Gmail-test och första start (B 1.14)

Koden kräver Google-konfiguration innan Gmail kan anslutas. Appens vanliga demo fungerar utan den. Inga Google-hemligheter ska läggas i GitHub eller skickas i chatt.

## Google Cloud

1. Skapa/välj projekt i Google Cloud Console. Aktivera Gmail API.
2. Konfigurera Google Auth Platform med appnamn Jobb4kevin och kontaktadress. Under Audience välj External/Testing för det privata testet och lägg till ditt Gmail-konto som testanvändare. Lägg till Kevins konto när han ska testa.
3. Lägg till behörigheterna `openid`, `email` och `https://www.googleapis.com/auth/gmail.send`. Appen läser inte inkorgen.
4. Skapa OAuth Client ID av typen Web application.
5. Ange exakt Authorized redirect URI: `https://no-more-clown-king-live-nweg.onrender.com/auth/gmail/callback`.
6. Spara Client ID och Client secret som serverhemligheter. Testing är för privat test, inte slutlig distribution. Google kan kräva verifiering för gmail.send, och testauktorisering kan behöva förnyas.

Officiell dokumentation: https://developers.google.com/identity/protocols/oauth2/web-server och https://developers.google.com/workspace/gmail/api/auth/scopes

## Render

Installera requirements och konfigurera:

- `GOOGLE_CLIENT_ID`: OAuth Client ID
- `GOOGLE_CLIENT_SECRET`: OAuth Client secret
- `GOOGLE_REDIRECT_URI`: exakt callback-URL ovan
- `FLASK_SECRET_KEY`: lång slumpnyckel som behålls mellan deployer
- `GMAIL_TOKEN_KEY`: Fernet-nyckel, generera med `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
- `GMAIL_DB_PATH`: exempel `/var/data/gmail.sqlite3` på monterad persistent disk, endast tillgänglig för appen

Skapa inte tokenfilen i den tillfälliga filytan: då förloras anslutningar vid omstart/deploy. Denna SQLite-lösning är för en Render-instans med persistent disk. Flera instanser kräver en delad databas. Behåll krypteringsnyckeln för att kunna läsa sparade anslutningar.

## iPhone-test

1. Öppna appen i Safari. Läs guiden: Dela → Lägg till på hemskärmen → Lägg till. Öppna därefter hemskärmsikonen.
2. Tryck Anslut Gmail, välj ditt testkonto och godkänn sändningsbehörigheten. Återvänd till samma webbläsare/app efter Googles inloggning. Safari och hemskärmsappen kan ha separata sessioner; anslut från den miljö du ska använda. Om Google nekar inloggning i hemskärmsappen, prova Safari och kontrollera detta före release.
3. Status ska visa rätt e-postadress. Ingen sändning sker vid anslutning.
4. Förbered en ansökan och redigera brevet. Tryck Skicka test till haces@hotmail.com och bekräfta. Kontrollera mottagen text och bifogad PDF. Testet sparar inte ansökan och döljer inte jobbet; vanlig Spara demo-knapp finns kvar.
5. Servern ignorerar mottagare från klienten: endast haces@hotmail.com kan få testmejlet. Ingen arbetsgivare kan få ett mejl via denna endpoint.
6. Testa avbruten Google-inloggning, frånkoppling, offline och omstart. Vid oklart sändningsresultat kontrollera Skickat innan nytt försök; ingen automatisk omsändning görs.

Startguiden har en egen lokal markering och kan återläsas under Hjälp med hemskärmen. Avsaknad av Gmail-anslutning betyder inte att användaren är ny. Rensad webbläsardata kan visa guiden igen och kräva ny anslutning. Historiken ligger fortfarande lokalt på respektive enhet, inte i Gmail.

## Automatiska kontroller

`python -m unittest discover -s tests -p test_gmail_connection.py`

Mockade Google-svar kontrollerar state, anslutningsisolering, krypterad tokenlagring, CSRF och mottagarlåst mejl med PDF. Faktisk Google-inloggning och mottagning måste testas efter konfiguration.
