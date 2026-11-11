import base64
import json
import os
import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch, Mock
from flask import Flask
from cryptography.fernet import Fernet
from gmail_connection import register_gmail

class GmailTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory()
  self.env=patch.dict(os.environ,dict(FLASK_SECRET_KEY='test-secret',GOOGLE_CLIENT_ID='client',GOOGLE_CLIENT_SECRET='secret',GOOGLE_REDIRECT_URI='https://localhost/auth/gmail/callback',GMAIL_TOKEN_KEY=Fernet.generate_key().decode(),GMAIL_DB_PATH=self.tmp.name+'/tokens.db'))
  self.env.start();Path(self.tmp.name+'/Kevin_Martini_CV.pdf').write_bytes(b'%PDF-test')
  self.app=Flask(__name__,static_folder=self.tmp.name);register_gmail(self.app);self.client=self.app.test_client()
 def tearDown(self):self.env.stop();self.tmp.cleanup()
 def response(self,data):return Mock(json=lambda:data,raise_for_status=lambda:None)
 def connect(self):
  csrf=self.client.get('/api/gmail/status',base_url='https://localhost').json['csrf']
  url=self.client.get('/auth/gmail/start',base_url='https://localhost').location
  params=parse_qs(urlparse(url).query)
  self.assertIn('code_challenge',params)
  with patch('gmail_connection.requests.post',return_value=self.response(dict(access_token='access',refresh_token='refresh-secret',scope='https://www.googleapis.com/auth/gmail.send'))),patch('gmail_connection.requests.get',return_value=self.response(dict(email='test@gmail.com',email_verified=True))):
   result=self.client.get('/auth/gmail/callback?state='+params['state'][0]+'&code=code',base_url='https://localhost')
  self.assertIn('gmail=connected',result.location)
  return csrf
 def test_status_unconfigured(self):
  with patch.dict(os.environ,{'GOOGLE_CLIENT_ID':''}):self.assertFalse(self.client.get('/api/gmail/status').json['configured'])
 def test_state_rejected(self):
  with patch('gmail_connection.requests.post') as post:
   self.assertIn('failed',self.client.get('/auth/gmail/callback?state=bad&code=x').location);post.assert_not_called()
 def test_connection_isolated_encrypted_and_disconnect(self):
  csrf=self.connect();self.assertTrue(self.client.get('/api/gmail/status').json['connected'])
  self.assertFalse(self.app.test_client().get('/api/gmail/status').json['connected'])
  self.assertNotIn(b'refresh-secret',Path(os.environ['GMAIL_DB_PATH']).read_bytes())
  self.assertEqual(self.client.post('/api/gmail/disconnect').status_code,403)
  with patch('gmail_connection.requests.post',return_value=self.response({})):
   self.assertTrue(self.client.post('/api/gmail/disconnect',headers={'X-Gmail-CSRF':csrf}).json['disconnected'])
 def test_send_locked_to_test_address_with_pdf(self):
  csrf=self.connect()
  with patch('gmail_connection.validate_recipient',return_value='employer@example.com'), patch('gmail_connection.requests.post',side_effect=[self.response({'access_token':'access'}),self.response({'id':'sent-id'})]) as post:
   r=self.client.post('/api/gmail/send-test',headers={'X-Gmail-CSRF':csrf},json=dict(title='Montör',letter='Mitt ändrade brev',to='employer@invalid.test'))
   self.assertTrue(r.json['sent'])
   raw=base64.urlsafe_b64decode(post.call_args.kwargs['json']['raw']).decode()
   self.assertIn('haces@hotmail.com',raw);self.assertNotIn('employer@invalid.test',raw);self.assertIn('Kevin_Martini_CV.pdf',raw)
 def test_missing_csrf_denied(self):
  self.assertEqual(self.client.post('/api/gmail/send-test',json={}).status_code,403)




class PostgresGmailTests(GmailTests):
 def setUp(self):
  super().setUp()
  self.pg_env=patch.dict(os.environ,{'GMAIL_DATABASE_URL':'postgresql://test:password@host/test?sslmode=require','GMAIL_DB_PATH':''});self.pg_env.start()
  import sqlite3
  self.calls=[];self.connect_options=[]
  owner=self
  class Adapter:
   def __init__(self):self.con=sqlite3.connect(owner.tmp.name+'/pg-adapter.sqlite')
   def execute(self,sql,args=()):
    owner.calls.append(sql)
    if sql.startswith('SELECT set_config'):return self.con.execute('SELECT 1')
    return self.con.execute(sql.replace('%s','?'),args)
   def commit(self):self.con.commit()
   def rollback(self):self.con.rollback()
   def close(self):self.con.close()
  def connect(*a,**k):
   self.connect_options.append(k);return Adapter()
  self.pg=patch('psycopg.connect',side_effect=connect);self.pg.start()
 def tearDown(self):self.pg.stop();self.pg_env.stop();super().tearDown()
 def test_connection_isolated_encrypted_and_disconnect(self):
  csrf=self.connect()
  self.assertTrue(self.client.get('/api/gmail/status').json['connected'])
  self.assertFalse(self.app.test_client().get('/api/gmail/status').json['connected'])
  self.assertNotIn(b'refresh-secret',Path(self.tmp.name+'/pg-adapter.sqlite').read_bytes())
  self.assertTrue(any('BYTEA' in x for x in self.calls))
  self.assertTrue(any('id=%s' in x for x in self.calls))
  with patch('gmail_connection.requests.post',return_value=self.response({})):
   self.assertTrue(self.client.post('/api/gmail/disconnect',headers={'X-Gmail-CSRF':csrf}).json['disconnected'])
 def test_tls_required(self):
  self.connect()
  with patch.dict(os.environ,{'GMAIL_DATABASE_URL':'postgresql://test:password@host/test?sslmode=disable'}):
   self.assertEqual(self.client.get('/api/gmail/status').status_code,503)

class GmailFailureTests(GmailTests):
 def test_database_error_is_actionable(self):
  self.connect()
  with patch('gmail_connection.sqlite3.connect',side_effect=OSError('secret-password-must-not-leak')):
   r=self.client.get('/api/gmail/status')
  self.assertEqual(r.status_code,503);self.assertEqual(r.json['code'],'gmail_database')
  self.assertNotIn('secret-password',str(r.json));self.assertTrue(r.json['configured'])
 def test_changed_key_is_distinct(self):
  self.connect()
  with patch.dict(os.environ,{'GMAIL_TOKEN_KEY':Fernet.generate_key().decode()}):
   self.assertEqual(self.client.get('/api/gmail/status').json['code'],'gmail_token_key')

class LetterHtmlTests(unittest.TestCase):
 def test_signature_keeps_name_on_next_line(self):
  from gmail_connection import letter_html
  result=letter_html('Hej!\n\nJag vill utvecklas vidare hos\ner.\n\nMed vänliga hälsningar\nKevin Martini Test 2')
  self.assertIn('<p>Jag vill utvecklas vidare hos er.</p>',result)
  self.assertIn('<p>Med vänliga hälsningar<br>Kevin Martini Test 2</p>',result)
 def test_signature_escapes_user_text(self):
  from gmail_connection import letter_html
  result=letter_html('Med vänliga hälsningar,\r\nKevin <script>\r\nKontakt')
  self.assertIn('hälsningar,<br>Kevin &lt;script&gt;<br>Kontakt',result)
  self.assertNotIn('<script>',result)
 def test_prose_list_and_cv_reminder(self):
  from gmail_connection import letter_html
  result=letter_html('För tjänsten:\n• AutoCAD\n• Produktion\n\nSe även bifogat CV.')
  self.assertIn('<p>För tjänsten:</p>',result)
  self.assertIn('• AutoCAD</p>',result)
  self.assertIn('<p>Se även bifogat CV.</p>',result)

class RecipientTests(GmailTests):
 def test_recipient_validation_cases(self):
  from gmail_connection import validate_recipient, RecipientValidationError
  ad={'id':'12345678','application_details':{'email':'info@example.com'}}
  def response(payload):
   result=self.response(payload);result.status_code=200;return result
  with patch('gmail_connection.requests.get',return_value=response(ad)) as get:
   self.assertEqual(validate_recipient('12345678','info@example.com'),'info@example.com')
   self.assertFalse(get.call_args.kwargs['allow_redirects'])
   for email in ['',None,'bad','victim@example.com\r\nBcc:x@y.com','other@example.com']:
    with self.assertRaises(RecipientValidationError):validate_recipient('12345678',email)
  for details in [{'url':'https://example.com/apply','email':'info@example.com'},{},{'email':'bad'}]:
   with patch('gmail_connection.requests.get',return_value=response({'id':'12345678','application_details':details})):
    with self.assertRaises(RecipientValidationError):validate_recipient('12345678','info@example.com')
  for payload in [{'id':'99999999','application_details':ad['application_details']},{**ad,'removed':True}]:
   with patch('gmail_connection.requests.get',return_value=response(payload)):
    with self.assertRaises(RecipientValidationError):validate_recipient('12345678','info@example.com')
  with patch('gmail_connection.requests.get',side_effect=TimeoutError()):
   with self.assertRaises(RecipientValidationError):validate_recipient('12345678','info@example.com')
 def test_stop_before_any_send(self):
  from gmail_connection import RecipientValidationError
  csrf=self.connect()
  with patch('gmail_connection.validate_recipient',side_effect=RecipientValidationError('recipient_changed','Ny granskning krävs')),patch('gmail_connection.requests.post') as post:
   result=self.client.post('/api/gmail/send-test',headers={'X-Gmail-CSRF':csrf},json={'title':'Montör','letter':'Brev','job_id':'12345678','reviewed_email':'info@example.com'})
   self.assertEqual(result.status_code,409);self.assertEqual(result.json['code'],'recipient_changed');post.assert_not_called()

class MailModeTests(GmailTests):
 def test_default_and_unknown_mode_are_test(self):
  from gmail_connection import mail_mode
  for value in ['', 'typo', 'false']:
   with patch.dict(os.environ,{'GMAIL_SEND_MODE':value}):self.assertEqual(mail_mode(),'test')
 def test_live_uses_verified_recipient(self):
  from email import message_from_bytes,policy
  csrf=self.connect()
  with patch.dict(os.environ,{'GMAIL_SEND_MODE':'live'}),patch('gmail_connection.validate_recipient',return_value='verified@example.com'),patch('gmail_connection.requests.post',side_effect=[self.response({'access_token':'access'}),self.response({'id':'sent'})]) as post:
   r=self.client.post('/api/gmail/send-test',headers={'X-Gmail-CSRF':csrf},json={'title':'Montör','letter':'Brev','job_id':'12345678','reviewed_email':'verified@example.com','send_mode':'live','reviewed_sender':'test@gmail.com','to':'ignored@example.com'})
   self.assertTrue(r.json['sent']);self.assertEqual(r.json['mode'],'live')
   message=message_from_bytes(base64.urlsafe_b64decode(post.call_args.kwargs['json']['raw']),policy=policy.default)
   self.assertEqual(message['To'],'verified@example.com');self.assertEqual(message['Subject'],'Ansökan – Montör')
   self.assertEqual(message.get_body(preferencelist=('plain',)).get_content().strip(),'Brev')
 def test_mode_change_and_sender_change_stop_before_send(self):
  csrf=self.connect()
  with patch.dict(os.environ,{'GMAIL_SEND_MODE':'live'}),patch('gmail_connection.requests.post') as post:
   for fields in [{},{'send_mode':'test'},{'send_mode':'live','reviewed_sender':'wrong@example.com'}]:
    r=self.client.post('/api/gmail/send-test',headers={'X-Gmail-CSRF':csrf},json={'title':'Montör','letter':'Brev',**fields})
    self.assertEqual(r.status_code,409)
   post.assert_not_called()

if __name__=='__main__':unittest.main()



