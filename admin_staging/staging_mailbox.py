"""Private synthetic OTP delivery for normal staging authentication tests only.

No HTTP inbox, external SMTP, real account delivery or diagnostic logging.
"""
from pathlib import Path
import hashlib,json,os,re,time
ROOT=Path(__file__).resolve().parent
ADDRESS=re.compile(r'synthetic-[a-z0-9.-]+@[a-z0-9.-]+\.invalid')

def deliver(address,otp):
    address=str(address).strip().lower()
    if os.environ.get('FAWRY_ISOLATED_ADMIN')!='1' or not ADDRESS.fullmatch(address):return False
    private=ROOT/'.private'
    if Path(os.environ.get('STAGING_PRIVATE_ROOT','')).resolve()!=private.resolve():return False
    inbox=private/'synthetic_mailbox';inbox.mkdir(exist_ok=True)
    key=hashlib.sha256(address.encode()).hexdigest()
    target=inbox/(key+'.json');temporary=inbox/(key+'.tmp')
    temporary.write_text(json.dumps({'address':address,'otp':str(otp),'expires_at':time.time()+300}),encoding='utf-8')
    temporary.replace(target)
    return True
