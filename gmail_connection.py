"""Per-browser Gmail OAuth connection; outbound demo mail is recipient-locked."""
import base64
import hashlib
import json
import os
import secrets
import sqlite3
import time
from email.message import EmailMessage
from pathlib import Path
from urllib.parse import urlencode
import requests
from cryptography.fernet import Fernet
from flask import jsonify, redirect, request, session

SCOPE = 'openid email https://www.googleapis.com/auth/gmail.send'
TEST_RECIPIENT = 'haces@hotmail.com'

def register_gmail(app):
    app.secret_key = os.environ.get('FLASK_SECRET_KEY') or secrets.token_hex(32)
    app.config.update(SESSION_COOKIE_SECURE=True, SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax')

    def ready():
        return all(os.environ.get(k) for k in ('FLASK_SECRET_KEY', 'GOOGLE_CLIENT_ID', 'GOOGLE_CLIENT_SECRET', 'GOOGLE_REDIRECT_URI', 'GMAIL_TOKEN_KEY', 'GMAIL_DB_PATH')) and os.environ['GOOGLE_REDIRECT_URI'].startswith('https://')

    def db():
        con = sqlite3.connect(os.environ['GMAIL_DB_PATH'])
        con.execute('CREATE TABLE IF NOT EXISTS gmail (id TEXT PRIMARY KEY, payload BLOB NOT NULL)')
        return con

    def read():
        if not ready() or not session.get('gmail_id'):
            return None
        with db() as con:
            row = con.execute('SELECT payload FROM gmail WHERE id=?', (session['gmail_id'],)).fetchone()
        return json.loads(Fernet(os.environ['GMAIL_TOKEN_KEY']).decrypt(row[0])) if row else None

    def write(value):
        payload = Fernet(os.environ['GMAIL_TOKEN_KEY']).encrypt(json.dumps(value).encode())
        with db() as con:
            con.execute('INSERT OR REPLACE INTO gmail VALUES (?,?)', (session['gmail_id'], payload))

    def csrf_ok():
        token = session.get('gmail_csrf', '')
        return bool(token) and secrets.compare_digest(token, request.headers.get('X-Gmail-CSRF', ''))

    @app.get('/api/gmail/status')
    def gmail_status():
        session.permanent = True
        session.setdefault('gmail_csrf', secrets.token_urlsafe(32))
        try:
            account = read()
            return jsonify(configured=ready(), connected=bool(account), email=account.get('email') if account else None, csrf=session['gmail_csrf'])
        except Exception:
            return jsonify(configured=False, connected=False, error='Anslutningen kunde inte läsas.'), 503

    @app.get('/auth/gmail/start')
    def gmail_start():
        if not ready():
            return redirect('/?gmail=not_configured')
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
            write(dict(refresh_token=tokens['refresh_token'], email=identity['email']))
            return redirect('/?gmail=connected')
        except Exception:
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
                    con.execute('DELETE FROM gmail WHERE id=?', (session['gmail_id'],))
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
