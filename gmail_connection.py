"""Per-browser Gmail OAuth connection; outbound demo mail is recipient-locked."""
import base64
import hashlib
import json
import os
import secrets
import sqlite3
import time
from contextlib import contextmanager
from email.message import EmailMessage
from pathlib import Path
from urllib.parse import urlencode
import requests
from cryptography.fernet import Fernet, InvalidToken
from flask import jsonify, redirect, request, session

SCOPE = 'openid email https://www.googleapis.com/auth/gmail.send'
TEST_RECIPIENT = 'haces@hotmail.com'

def register_gmail(app):
    app.secret_key = os.environ.get('FLASK_SECRET_KEY') or secrets.token_hex(32)
    app.config.update(SESSION_COOKIE_SECURE=True, SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax')

    def ready():
        return all(os.environ.get(k) for k in ('FLASK_SECRET_KEY', 'GOOGLE_CLIENT_ID', 'GOOGLE_CLIENT_SECRET', 'GOOGLE_REDIRECT_URI', 'GMAIL_TOKEN_KEY')) and bool(os.environ.get('GMAIL_DATABASE_URL') or os.environ.get('GMAIL_DB_PATH')) and os.environ['GOOGLE_REDIRECT_URI'].startswith('https://')

    @contextmanager
    def db():
        url = os.environ.get('GMAIL_DATABASE_URL')
        if url:
            import psycopg
            from psycopg.conninfo import conninfo_to_dict
            settings = conninfo_to_dict(url)
            mode = settings.get('sslmode', 'require')
            if mode not in ('require', 'verify-ca', 'verify-full'):
                raise ValueError('TLS required')
            con = psycopg.connect(url, sslmode=mode, connect_timeout=15)
            schema = 'CREATE TABLE IF NOT EXISTS gmail (id TEXT PRIMARY KEY, payload BYTEA NOT NULL)'
        else:
            con = sqlite3.connect(os.environ['GMAIL_DB_PATH'])
            schema = 'CREATE TABLE IF NOT EXISTS gmail (id TEXT PRIMARY KEY, payload BLOB NOT NULL)'
        try:
            if url:
                con.execute("SELECT set_config('statement_timeout', '10000', true)")
            con.execute(schema)
            yield con
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

    def query(con, sql, args):
        # Both drivers bind parameters; credentials and IDs never enter SQL text.
        return con.execute(sql.replace('?', '%s') if os.environ.get('GMAIL_DATABASE_URL') else sql, args)

    def read():
        if not ready() or not session.get('gmail_id'):
            return None
        with db() as con:
            row = query(con, 'SELECT payload FROM gmail WHERE id=?', (session['gmail_id'],)).fetchone()
        return json.loads(Fernet(os.environ['GMAIL_TOKEN_KEY']).decrypt(row[0])) if row else None

    def write(value):
        payload = Fernet(os.environ['GMAIL_TOKEN_KEY']).encrypt(json.dumps(value).encode())
        with db() as con:
            query(con, 'INSERT INTO gmail (id,payload) VALUES (?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload', (session['gmail_id'], payload))

    def csrf_ok():
        token = session.get('gmail_csrf', '')
        return bool(token) and secrets.compare_digest(token, request.headers.get('X-Gmail-CSRF', ''))

    def connection_error(exc, stage='storage'):
        if isinstance(exc, InvalidToken):
            code, message = 'gmail_token_key', 'Den sparade Gmail-anslutningen kan inte dekrypteras. Kontrollera att GMAIL_TOKEN_KEY är oförändrad och anslut Gmail igen.'
        elif isinstance(exc, (ValueError, TypeError)):
            code, message = 'gmail_config', 'Gmail-inställningen eller krypteringsnyckeln är ogiltig. Kontrollera serverinställningarna.'
        else:
            code = 'gmail_database' if stage == 'storage' else 'gmail_google'
            message = 'Databasen kunde inte nås eller användas. Kontrollera GMAIL_DATABASE_URL och databasens åtkomst.' if stage == 'storage' else 'Google-anslutningen kunde inte slutföras. Starta en ny anslutning.'
        app.logger.warning('Gmail connection failure: code=%s stage=%s type=%s', code, stage, type(exc).__name__)
        return dict(code=code, error=message)

    @app.get('/api/gmail/status')
    def gmail_status():
        session.permanent = True
        session.setdefault('gmail_csrf', secrets.token_urlsafe(32))
        try:
            account = read()
            return jsonify(configured=ready(), connected=bool(account), email=account.get('email') if account else None, csrf=session['gmail_csrf'], **({} if account else session.get('gmail_error', {})))
        except Exception as exc:
            return jsonify(configured=ready(), connected=False, csrf=session['gmail_csrf'], **connection_error(exc)), 503

    @app.get('/auth/gmail/start')
    def gmail_start():
        if not ready():
            return redirect('/?gmail=not_configured')
        session.pop('gmail_error', None)
        state = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(64)
        session['gmail_oauth'] = {'state': state, 'verifier': verifier, 'at': time.time()}
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
        return redirect('https://accounts.google.com/o/oauth2/v2/auth?' + urlencode(dict(client_id=os.environ['GOOGLE_CLIENT_ID'], redirect_uri=os.environ['GOOGLE_REDIRECT_URI'], response_type='code', scope=SCOPE, state=state, code_challenge=challenge, code_challenge_method='S256', access_type='offline', prompt='consent select_account')))

    @app.get('/auth/gmail/callback')
    def gmail_callback():
        pending = session.pop('gmail_oauth', {})
        if not ready() or not pending or time.time()-pending.get('at', 0)>600 or not secrets.compare_digest(pending.get('state', ''), request.args.get('state', '')):
            return redirect('/?gmail=failed')
        if request.args.get('error') or not request.args.get('code'):
            return redirect('/?gmail=cancelled')
        stage = 'google'
        try:
            response = requests.post('https://oauth2.googleapis.com/token', data=dict(client_id=os.environ['GOOGLE_CLIENT_ID'], client_secret=os.environ['GOOGLE_CLIENT_SECRET'], code=request.args['code'], code_verifier=pending['verifier'], redirect_uri=os.environ['GOOGLE_REDIRECT_URI'], grant_type='authorization_code'), timeout=15)
            response.raise_for_status()
            tokens = response.json()
            if 'https://www.googleapis.com/auth/gmail.send' not in tokens.get('scope', '').split() or not tokens.get('refresh_token'):
                raise ValueError('Missing permission')
            profile = requests.get('https://openidconnect.googleapis.com/v1/userinfo', headers={'Authorization': 'Bearer '+tokens['access_token']}, timeout=15)
            profile.raise_for_status()
            identity = profile.json()
            if not identity.get('email_verified'):
                raise ValueError('Unverified email')
            session.setdefault('gmail_id', secrets.token_urlsafe(32))
            stage = 'storage'
            write(dict(refresh_token=tokens['refresh_token'], email=identity['email']))
            session.pop('gmail_error', None)
            return redirect('/?gmail=connected')
        except Exception as exc:
            session['gmail_error'] = connection_error(exc, stage)
            return redirect('/?gmail=failed')

    @app.post('/api/gmail/disconnect')
    def gmail_disconnect():
        if not csrf_ok():
            return jsonify(error='Ladda om sidan och försök igen.'), 403
        try:
            account = read()
            if account:
                response = requests.post('https://oauth2.googleapis.com/revoke', data={'token': account['refresh_token']}, timeout=15)
                response.raise_for_status()
                with db() as con:
                    query(con, 'DELETE FROM gmail WHERE id=?', (session['gmail_id'],))
            session.pop('gmail_id', None)
            return jsonify(disconnected=True)
        except Exception:
            return jsonify(error='Kunde inte koppla från. Försök igen eller återkalla åtkomsten i ditt Google-konto.'), 502

    @app.post('/api/gmail/send-test')
    def gmail_send_test():
        if not csrf_ok():
            return jsonify(error='Ladda om sidan och försök igen.'), 403
        body = request.get_json(silent=True) or {}
        letter, title = body.get('letter'), body.get('title')
        if not isinstance(letter, str) or not letter.strip() or len(letter)>30000 or not isinstance(title, str) or len(title)>200 or '\n' in title or '\r' in title:
            return jsonify(error='Kontrollera brevet och jobbrubriken.'), 400
        try:
            account = read()
            if not account:
                return jsonify(error='Anslut Gmail först.'), 401
            response = requests.post('https://oauth2.googleapis.com/token', data=dict(client_id=os.environ['GOOGLE_CLIENT_ID'], client_secret=os.environ['GOOGLE_CLIENT_SECRET'], refresh_token=account['refresh_token'], grant_type='refresh_token'), timeout=15)
            response.raise_for_status()
            message = EmailMessage()
            message['To'], message['From'] = TEST_RECIPIENT, account['email']
            message['Subject'] = 'TESTANSÖKAN – '+title
            message.set_content('TEST – skickad för granskning, ingen ansökan till arbetsgivare.\n\n'+letter.strip())
            pdf = Path(app.static_folder)/'Kevin_Martini_CV.pdf'
            message.add_attachment(pdf.read_bytes(), maintype='application', subtype='pdf', filename='Kevin_Martini_CV.pdf')
            result = requests.post('https://gmail.googleapis.com/gmail/v1/users/me/messages/send', headers={'Authorization': 'Bearer '+response.json()['access_token']}, json={'raw': base64.urlsafe_b64encode(message.as_bytes()).decode()}, timeout=20)
            result.raise_for_status()
            if not result.json().get('id'):
                raise ValueError('No receipt')
            return jsonify(sent=True, recipient=TEST_RECIPIENT)
        except Exception:
            # Never retry a send automatically: provider acceptance may be uncertain.
            return jsonify(error='Sändningen kunde inte bekräftas. Kontrollera Skickat i Gmail innan du försöker igen.'), 502


