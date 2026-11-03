import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import catalog_store
import answer_feedback as feedback


class FeedbackTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.patch = patch.object(catalog_store, 'DB', Path(self.temp.name) / 'isolated.sqlite')
        self.patch.start(); self.addCleanup(self.patch.stop)
        self.actor = {'sub': 'synthetic-admin-A'}
        self.other = {'sub': 'synthetic-admin-B'}
        self.result = {'answer': 'Example answer', 'supported_fact_ids': ['F0001'],
                       'backend': 'Core_BM25', 'complete': True,
                       'citations': [{'fact_id': 'F0001', 'source_sha256': '1' * 64,
                                      'source_document': 'original.md', 'locator': {'line_start': 216}}],
                       'Authorization': 'secret-must-not-copy',
                       'request_contract': {'requests': [{'service_id': 'axis_pay', 'intent_id': 'deposit_tariff'}]}}

    def capture(self, question='Synthetic question'):
        return feedback.capture({'question': question, 'knowledge_mode': 'review_preview'}, self.result, self.actor)

    def test_exact_source_binding_and_whitelist(self):
        trace = feedback.read(self.capture(), self.actor)
        self.assertEqual(trace['citations'][0]['source_sha256'], '1' * 64)
        self.assertEqual(trace['citations'][0]['locator'], {'line_start': 216})
        self.assertNotIn('secret-must-not-copy', json.dumps(trace))
        self.assertNotIn('owner', trace)

    def test_report_links_actual_trace(self):
        trace = self.capture(); report = feedback.report(trace, 'Missing condition', self.actor)
        exported = feedback.export(trace, self.actor)
        self.assertEqual(exported['trace']['trace_id'], trace)
        self.assertEqual(exported['feedback'][0]['report_id'], report['report_id'])
        self.assertFalse(report['policy_approval'])

    def test_cross_user_read_report_export_denied(self):
        trace = self.capture()
        for operation in (lambda: feedback.read(trace, self.other),
                          lambda: feedback.report(trace, 'Attempt', self.other),
                          lambda: feedback.export(trace, self.other)):
            with self.assertRaises(LookupError): operation()
        self.assertEqual(feedback.listing(self.other), [])

    def test_secrets_and_personal_canaries_redacted(self):
        trace = self.capture('password=CANARYPASS token=CANARYTOKEN test.person@example.invalid 01012345678')
        feedback.report(trace, 'secret=CANARYNOTE', self.actor)
        exported = json.dumps(feedback.export(trace, self.actor))
        for sensitive in ('CANARYPASS', 'CANARYTOKEN', 'CANARYNOTE', 'test.person@example.invalid', '01012345678'):
            self.assertNotIn(sensitive, exported)

    def test_unknown_trace_cannot_forge_report(self):
        with self.assertRaises(LookupError): feedback.report('trace-' + '0' * 32, 'Forged', self.actor)
        self.assertEqual(feedback.listing(self.actor), [])

    def test_feedback_audit_and_real_records_untouched(self):
        with catalog_store.db() as c:
            catalog_store.put(c, 'fact', 'F0001', 'frozen', {'pending': True})
        feedback.report(self.capture(), 'Incorrect scope', self.actor)
        with catalog_store.db() as c:
            self.assertEqual(json.loads(c.execute("select data from record where kind='fact'").fetchone()[0]), {'pending': True})
            self.assertEqual(c.execute("select count(*) from event where kind='answer_feedback_submitted'").fetchone()[0], 1)

    def test_anonymous_capture_denied(self):
        with self.assertRaises(PermissionError): feedback.capture({'question': 'test'}, self.result, {})


if __name__ == '__main__': unittest.main()
