import unittest
from types import SimpleNamespace
from staging_session_policy import account_matches
class Tests(unittest.TestCase):
 def setUp(self):self.payload={'sub':'original-id','email':'synthetic-user@uat.invalid','role':'admin'};self.employee=SimpleNamespace(employee_id='original-id',email='synthetic-user@uat.invalid',department='admin')
 def test_current_identity(self):self.assertTrue(account_matches(self.payload,self.employee))
 def test_deleted_or_unavailable_account(self):self.assertFalse(account_matches(self.payload,None))
 def test_recycled_email_new_identity(self):self.employee.employee_id='replacement-id';self.assertFalse(account_matches(self.payload,self.employee))
 def test_changed_role(self):self.employee.department='Retail';self.assertFalse(account_matches(self.payload,self.employee))
 def test_changed_email(self):self.employee.email='synthetic-other@uat.invalid';self.assertFalse(account_matches(self.payload,self.employee))
 def test_virtual_or_empty_identity(self):self.assertFalse(account_matches({},self.employee))
 def test_normalized_role_and_email(self):self.employee.department='Admin';self.employee.email='SYNTHETIC-USER@uat.invalid';self.assertTrue(account_matches(self.payload,self.employee))
if __name__=='__main__':unittest.main()
