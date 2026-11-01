"""Small source-relevant translation vocabulary; contains no business rules."""
import re
from .canonical_context import norm

TERMS=[('فوري بلس','Fawry Plus'),('محفظة','wallet'),('مدخراتي','My Savings'),
       ('إضافة صندوق','Add Fund'),('صندوق','fund'),('رصيد','balance'),
       ('أكسس باي','AXIS Pay'),('اكسس باي','AXIS Pay'),
       ('الكارت الأصفر','Yellow Card'),('إنستاباي','InstaPay'),('انستاباي','InstaPay'),
       ('اعرف عميلك','Know Your Customer (KYC)'),('حوالة','remittance'),
       ('جنيه','pounds'),('جنيه مصري','Egyptian pounds (EGP)')]

def source_glossary(text):
    value=norm(text);entries={}
    for arabic,english in TERMS:
        if norm(arabic) in value:entries[arabic]=english
    if 'يستقر' in value and 'رصيد' in value and 'محفظه' in value:
        entries['يستقر المبلغ في رصيد العميل']='the deposit remains in the customer’s wallet balance'
    return entries
