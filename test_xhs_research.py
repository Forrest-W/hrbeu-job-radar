"""Offline regression checks: credential parsing, checkpointing and evidence scoring."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import xhs_research as x
from xhs_transport import ResearchError, NoRedirect


class ResearchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = x.connect(Path(self.temp.name))
        self.company = "示例测试企业"
        self.key = x.company_key(self.company)
        self.db.execute("INSERT INTO companies VALUES (?,?,?)", (self.key, self.company, 80))
        for dim in x.DIMENSIONS:
            self.db.execute("INSERT INTO tasks(company_id,dimension,query) VALUES (?,?,?)", (self.key, dim, self.company + dim))
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def test_windows_curl(self):
        text = 'curl --url ^"https://so.xiaohongshu.com/api/sns/web/v2/search/notes^" ^\n-b ^"a1=TEST_A1; web_session=TEST_SESSION^"'
        out = x.parse_curl(text)
        self.assertEqual(out['cookies']['a1'], 'TEST_A1')
        self.assertIn('/v2/', out['searchEndpoint'])

    def test_bash_curl(self):
        out = x.parse_curl("curl 'https://edith.xiaohongshu.com/api/sns/web/v1/search/notes' -H 'cookie: a1=TEST; web_session=TEST_SESSION'")
        self.assertEqual(len(out['cookies']), 2)

    def test_markdown_curl_and_case(self):
        out = x.parse_curl('curl --url ^"[https://so.xiaohongshu.com/api/sns/web/v2/search/notes^](https://unused.invalid)^" -H ^"Cookie: a1=TEST; web_session=TEST_SESSION^"')
        self.assertEqual(out['cookies']['web_session'], 'TEST_SESSION')

    def test_collect_without_cookie_rejected(self):
        with self.assertRaisesRegex(ResearchError, 'Cookie'):
            x.parse_curl('curl "https://t2.xiaohongshu.com/api/v2/collect" --data-raw "TEST"')

    def test_external_host_rejected(self):
        with self.assertRaises(ResearchError):
            x.parse_curl('curl https://xiaohongshu.com.evil.test/ -b "a1=TEST; web_session=TEST"')

    def test_cookie_newline_rejected_and_never_printed(self):
        with self.assertRaises(ResearchError) as error:
            x.parse_curl('curl https://www.xiaohongshu.com/ -b "a1=TEST; web_session=VERY_SECRET\nHEADER"')
        self.assertNotIn('VERY_SECRET', str(error.exception))

    def test_command_substitution_not_executed(self):
        # Supplied commands are data, never passed to a shell.
        with patch('subprocess.Popen', side_effect=AssertionError('must not execute')):
            out = x.parse_curl('curl https://www.xiaohongshu.com/ -b "a1=TEST; web_session=$(echo NEVER_EXECUTE)"')
        self.assertIn('NEVER_EXECUTE', out['cookies']['web_session'])

    @unittest.skipUnless(os.name == 'nt', 'DPAPI is Windows-specific')
    def test_dpapi_roundtrip(self):
        clear = b'LOCAL_TEST_SECRET_ONLY'
        encrypted = x.protect(clear)
        self.assertNotIn(clear, encrypted)
        self.assertEqual(x.protect(encrypted, True), clear)

    def test_batch_lock_prevents_parallel_queries(self):
        with patch.object(x, 'PRIVATE', Path(self.temp.name)):
            with x.batch_lock():
                with self.assertRaises(ResearchError):
                    with x.batch_lock():
                        self.fail('second job acquired lock')
            with x.batch_lock():
                pass

    def test_redirect_refused(self):
        self.assertIsNone(NoRedirect().redirect_request(None, None, 302, '', {}, 'https://evil.test'))

    def test_pause_resume_and_no_repeat_of_completed_task(self):
        class Fake:
            def __init__(self): self.calls = 0; self.fail = True
            def search(self, query):
                self.calls += 1
                if self.fail: raise ResearchError('验证失败')
                return []
        fake = Fake()
        with self.assertRaises(ResearchError): x.run_pending(self.db, fake, 1, 3)
        self.assertEqual(self.db.execute("SELECT count(*) FROM tasks WHERE state='blocked'").fetchone()[0], 1)
        fake.fail = False
        x.run_pending(self.db, fake, 3, 3)
        x.run_pending(self.db, fake, 3, 3)
        self.assertEqual(fake.calls, 4)

    def test_notes_deduplicated_across_dimensions(self):
        class Fake:
            details = 0
            def search(self, query): return [{'id': 'a'*24, 'note_card': {}}]
            def detail(self, note_id, token):
                self.details += 1
                return {'title': 'TEST', 'desc': '测试正文', 'user': {'user_id': 'test-user'}}
        fake = Fake()
        x.run_pending(self.db, fake, 3, 3)
        self.assertEqual(fake.details, 1)
        self.assertEqual(self.db.execute('SELECT count(*) FROM evidence').fetchone()[0], 3)

    def review(self):
        return {'company': self.company, 'reviewer': 'offline test', 'dimensions': {
            d: {'score': None, 'summary': '', 'evidenceIds': []} for d in x.DIMENSIONS}}

    def add_evidence(self):
        for dim in x.DIMENSIONS:
            for ident in ['a', 'b']:
                x.save_note(self.db, self.key, dim, ident*24, {
                    'title': '合成测试数据', 'desc': '合成测试正文，不是真实评价', 'user': {'user_id': ident}})

    def test_missing_evidence_yields_no_score(self):
        result = x.validate_assessment(self.db, self.review())
        self.assertIsNone(result['overallScore'])
        review = self.review()
        review['dimensions']['hours'].update(score=80, summary='fake')
        with self.assertRaises(ResearchError): x.validate_assessment(self.db, review)

    def test_two_authors_weighted_score_and_bad_reference(self):
        self.add_evidence()
        review = self.review()
        for dim, score in [('hours',80),('salary',60),('experience',40)]:
            review['dimensions'][dim].update(score=score, summary='合成摘要', evidenceIds=['a'*24,'b'*24])
        result = x.validate_assessment(self.db, review)
        self.assertEqual(result['overallScore'], 63)
        self.assertNotIn('user_id', json.dumps(result))
        review['dimensions']['hours']['evidenceIds'].append('c'*24)
        with self.assertRaises(ResearchError): x.validate_assessment(self.db, review)

    def test_duplicate_author_not_sufficient(self):
        for ident in ['a', 'b']:
            x.save_note(self.db, self.key, 'hours', ident*24, {'desc': '正文', 'user': {'user_id': 'same'}})
        review = self.review()
        review['dimensions']['hours'].update(score=80, summary='test', evidenceIds=['a'*24,'b'*24])
        with self.assertRaises(ResearchError): x.validate_assessment(self.db, review)

    def test_public_snapshot_has_progress_but_no_raw_notes(self):
        self.add_evidence()
        with patch.object(x, 'ROOT', Path(self.temp.name)):
            snapshot = x.export_snapshot(self.db)
        self.assertEqual(snapshot['progress'][self.company]['hours']['candidateCount'], 2)
        self.assertNotIn('合成测试正文', json.dumps(snapshot, ensure_ascii=False))
        self.assertNotIn('author_key', json.dumps(snapshot))

    def test_review_queue_only_returns_complete_unreviewed_companies(self):
        self.assertEqual(x.review_next(self.db)['packets'], [])
        self.db.execute("UPDATE tasks SET state='no_results'")
        self.db.commit()
        self.assertEqual(len(x.review_next(self.db)['packets']), 1)
        self.db.execute('INSERT INTO assessments VALUES (?,?)', (self.key, '{}'))
        self.db.commit()
        self.assertEqual(x.review_next(self.db)['packets'], [])

    def test_search_alias_and_cross_dimension_evidence(self):
        self.assertEqual(x.query_name('中国电子科技集团公司第五十三研究所'), '电科53所')
        self.assertEqual(x.query_name('中国船舶集团有限公司第七二二研究所'), '中船722所')
        self.add_evidence()
        self.db.execute("DELETE FROM evidence WHERE dimension='salary'")
        self.db.commit()
        review=self.review()
        review['dimensions']['salary'].update(score=60,summary='测试薪资证据',evidenceIds=['a'*24,'b'*24])
        self.assertEqual(x.validate_assessment(self.db, review)['dimensions']['salary']['score'], 60)

    def test_company_batch_queries_once_and_keeps_dimension_states(self):
        class Fake:
            calls=0
            def search(self, query):
                self.calls += 1
                return [{'id':'a'*24,'note_card':{}}]
            def detail(self, ident, token):
                return {'desc':'合成测试正文', 'user':{'user_id':'author'}}
        fake=Fake()
        x.run_companies(self.db, fake, 5)
        self.assertEqual(fake.calls, 1)
        self.assertEqual(self.db.execute("SELECT count(*) FROM tasks WHERE state='fetched'").fetchone()[0], 3)
        self.assertEqual(self.db.execute('SELECT count(*) FROM assessments').fetchone()[0], 0)
        self.assertEqual(x.run_companies(self.db, fake, 5), 0)

    def test_comments_are_cached_and_link_to_original_post(self):
        class Fake:
            calls=0
            def comments(self, ident, token):
                self.calls += 1
                return [{'id':c*24,'content':'合成评论','user_info':{'user_id':c}} for c in ('b','c')]
        client=Fake()
        x.save_note(self.db,self.key,'hours','a'*24,{'title':'测试问题','desc':''})
        x.collect_comments(self.db,client,self.key,list(x.DIMENSIONS),'a'*24,'TEST_ONLY')
        x.collect_comments(self.db,client,self.key,list(x.DIMENSIONS),'a'*24,'TEST_ONLY')
        self.assertEqual(client.calls,1)
        review=self.review()
        review['dimensions']['hours'].update(score=55,summary='合成评论测试',evidenceIds=['a'*24+':'+c*24 for c in ('b','c')])
        result=x.validate_assessment(self.db,review)['dimensions']['hours']
        self.assertEqual(result['sampleCount'],1)
        self.assertEqual(result['commentCount'],2)
        self.assertTrue(all(s['url'].endswith('/'+'a'*24) for s in result['sources']))

    def test_company_comment_failure_stops_and_resumes_from_cache(self):
        class Fake:
            details = 0
            blocked = True
            def search(self, query): return [{'id':'a'*24,'note_card':{}}]
            def detail(self, ident, token):
                self.details += 1
                return {'desc':'测试正文','user':{'user_id':'a'}}
            def comments(self, ident, token):
                if self.blocked: raise ResearchError('HTTP 461：测试暂停')
                return []
        client = Fake()
        with self.assertRaises(ResearchError):
            x.run_companies(self.db, client, 5, read_comments=True)
        self.assertEqual(self.db.execute("SELECT count(*) FROM tasks WHERE state='blocked'").fetchone()[0], 3)
        self.assertEqual(self.db.execute('SELECT state FROM enrichment').fetchone()[0], 'blocked')
        self.assertEqual(x.review_next(self.db)['packets'], [])
        client.blocked = False
        x.run_companies(self.db, client, 5, read_comments=True)
        self.assertEqual(client.details, 1)
        self.assertEqual(self.db.execute('SELECT state FROM enrichment').fetchone()[0], 'complete')
        self.assertEqual(x.run_companies(self.db, client, 5, read_comments=True), 0)


if __name__ == '__main__':
    unittest.main()
