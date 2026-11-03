import contextlib,io,json,os,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
import staging_mailbox as mailbox
class Tests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);(self.root/'.private').mkdir()
        self.p=patch.object(mailbox,'ROOT',self.root);self.p.start();self.addCleanup(self.p.stop)
        self.env=patch.dict(os.environ,{'FAWRY_ISOLATED_ADMIN':'1','STAGING_PRIVATE_ROOT':str(self.root/'.private')});self.env.start();self.addCleanup(self.env.stop)
    def test_private_synthetic_delivery_no_stdout(self):
        out=io.StringIO()
        with contextlib.redirect_stdout(out):ok=mailbox.deliver('synthetic-test@uat.invalid','123456')
        self.assertTrue(ok);self.assertEqual(out.getvalue(),'')
        files=list((self.root/'.private/synthetic_mailbox').glob('*.json'));self.assertEqual(len(files),1)
        value=json.loads(files[0].read_text());self.assertEqual(value['otp'],'123456');self.assertGreater(value['expires_at'],time.time())
    def test_real_recipient_denied_without_writes(self):
        self.assertFalse(mailbox.deliver('someone@example.com','123456'));self.assertFalse((self.root/'.private/synthetic_mailbox').exists())
    def test_non_synthetic_invalid_denied(self):
        self.assertFalse(mailbox.deliver('ordinary@uat.invalid','123456'))
    def test_nonisolated_denied(self):
        with patch.dict(os.environ,{'FAWRY_ISOLATED_ADMIN':'0'}):self.assertFalse(mailbox.deliver('synthetic-test@uat.invalid','123456'))
    def test_wrong_private_destination_denied(self):
        with patch.dict(os.environ,{'STAGING_PRIVATE_ROOT':str(self.root/'other')}):self.assertFalse(mailbox.deliver('synthetic-test@uat.invalid','123456'))
if __name__=='__main__':unittest.main()
