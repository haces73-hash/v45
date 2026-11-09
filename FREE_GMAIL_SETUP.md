# B 1.15: Gmail på Render Free med Neon Free

Appen kan behålla sin gratis Render-tjänst. Gmail-anslutningar lagras krypterat i extern PostgreSQL i stället för på Render-disk. Ansökningshistoriken ligger som tidigare lokalt i webbläsaren. Testmejl kan fortfarande bara skickas till haces@hotmail.com.

## 1. Skapa databasen en gång

1. Öppna https://neon.com/ och skapa/logga in på ett konto.
2. Välj Free-planen. Skapa projektet Jobb4kevin och välj en lämplig europeisk region.
3. Öppna Connect för projektets databas. Välj en PostgreSQL-anslutningssträng (gärna pooled) och kopiera den kompletta strängen inklusive SSL-parametrarna.
4. Behåll `sslmode=require` eller striktare och eventuell `channel_binding=require`.
5. Anslutningssträngen innehåller lösenord. Lägg den endast i Render Environment, aldrig i GitHub eller chatt.

Källor: https://neon.com/blog/neon-free-plan-1-gb-per-project och https://neon.com/docs/get-started/connect-neon

## 2. Render Environment

Behåll Free-planen, lägg inte till disk. Sätt följande på befintlig tjänst:

| Key | Value |
| --- | --- |
| GMAIL_DATABASE_URL | Hela PostgreSQL-anslutningssträngen från Neon |
| GOOGLE_CLIENT_ID | OAuth-klientens ID från Google Cloud |
| GOOGLE_CLIENT_SECRET | OAuth-klientens hemlighet från Google Cloud |
| GOOGLE_REDIRECT_URI | https://no-more-clown-king-live-nweg.onrender.com/auth/gmail/callback |
| FLASK_SECRET_KEY | Bestående slumpmässig sessionsnyckel |
| GMAIL_TOKEN_KEY | Bestående Fernet-nyckel för kryptering |

GMAIL_DB_PATH behövs inte när GMAIL_DATABASE_URL används. PostgreSQL väljs före eventuell gammal SQLite-inställning. Tabell skapas automatiskt första gången uppgifter lagras/läses. Befintliga SQLite-anslutningar flyttas inte automatiskt; anslut Gmail igen efter bytet.

Behåll befintliga FLASK_SECRET_KEY och GMAIL_TOKEN_KEY om de redan är skapade. Om de saknas, generera på en betrodd dator med Python (inte någon publik nyckelgenerator):

```sh
python -c "import secrets; print(secrets.token_hex(32))"
```

Använd resultatet som FLASK_SECRET_KEY. Installera vid behov cryptography lokalt och generera GMAIL_TOKEN_KEY:

```sh
python -m pip install cryptography
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Publicera B 1.15 med Save, rebuild, and deploy så att psycopg-beroendet installeras. Behåll båda nycklarna vid framtida deployer. Ändrad krypteringsnyckel gör lagrade anslutningar oläsbara.

## 3. Google och iPhone

Google-konfigurationen är densamma: aktiverad Gmail API, webb-OAuth-klient, korrekt returadress och ditt Gmail-konto under Test users. Kevin behöver också vara testanvändare när han ska ansluta.

1. Öppna appen och tryck Anslut Gmail.
2. Välj ditt testkonto och godkänn sändningsbehörighet.
3. Kontrollera att rätt mejladress visas.
4. Skicka en testansökan och kontrollera brev och CV i haces@hotmail.com.
5. Publicera om Render-tjänsten och öppna appen från samma webbläsare igen. Anslutningen ska finnas kvar.
6. Testa Koppla från och ny anslutning.

Google-inloggning och faktisk sändning är ännu inte verifierade med den externa databasen. Browserdata/sessionen behöver finnas kvar; separat Safari/hemskärmsmiljö kan kräva egen anslutning.

## Gränser och verifiering

Detta kan köras inom leverantörernas gratisnivåer men är inte ett löfte om obegränsad kostnadsfri drift. Kontrollera Neons aktuella kvoter vid skapandet, stanna på Free och aktivera ingen betald uppgradering för detta test. Render och databasen kan behöva vakna efter inaktivitet.

Automatiska tester använder mockade Google-svar och en SQLite-baserad adapter för PostgreSQL-anrop. De kontrollerar kryptering, parameterbindning, upsert, borttagning, sessionsisolering, TLS-krav, CSRF och låst testmottagare. Ingen riktig Neon-databas har skapats eller testats av dessa tester.
