"""Real installed JOSE encoder/decoder with an ephemeral test signing key.
No production/staging key, real token, browser storage or credential is read.
"""
from pathlib import Path
import importlib.util,os,secrets,time,unittest
from datetime import timedelta
from unittest.mock import patch
from jose import JWTError
SOURCE=Path(__file__).resolve().parent/'application/src/routes/users/auth_utils.py'
with patch.dict(os.environ,{'STAGING_JWT_SECRET':secrets.token_urlsafe(48)}):
 spec=importlib.util.spec_from_file_location('expiry_test_auth',SOURCE);auth=importlib.util.module_from_spec(spec);spec.loader.exec_module(auth)
class Tests(unittest.TestCase):
 def setUp(self):self.identity={'sub':'synthetic-expiry','email':'synthetic-expiry@uat.invalid','role':'admin'}
 def test_valid_access(self):
  token=auth._encode_token(self.identity,timedelta(seconds=30),'access');self.assertEqual(auth.decode_token(token,'access')['sub'],'synthetic-expiry')
 def test_already_expired_access(self):
  token=auth._encode_token(self.identity,timedelta(seconds=-5),'access')
  with self.assertRaises(JWTError):auth.decode_token(token,'access')
 def test_already_expired_refresh(self):
  token=auth._encode_token(self.identity,timedelta(seconds=-5),'refresh')
  with self.assertRaises(JWTError):auth.decode_token(token,'refresh')
 def test_refresh_cannot_be_access(self):
  token=auth._encode_token(self.identity,timedelta(seconds=30),'refresh')
  with self.assertRaises(JWTError):auth.decode_token(token,'access')
 def test_tampered_signature_rejected(self):
  token=auth._encode_token(self.identity,timedelta(seconds=30),'access');a,b,c=token.split('.');c=('A' if c[0]!='A' else 'B')+c[1:]
  with self.assertRaises(JWTError):auth.decode_token('.'.join([a,b,c]),'access')
 def test_actual_elapsed_time_expiry(self):
  token=auth._encode_token(self.identity,timedelta(seconds=1),'access');auth.decode_token(token,'access');time.sleep(2.1)
  with self.assertRaises(JWTError):auth.decode_token(token,'access')
if __name__=='__main__':unittest.main()
