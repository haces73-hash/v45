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
  with patch('gmail_connection.requests.post',side_effect=[self.response({'access_token':'access'}),self.response({'id':'sent-id'})]) as post:
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

if __name__=='__main__':unittest.main()

