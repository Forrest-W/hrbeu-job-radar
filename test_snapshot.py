import json
import tempfile
import unittest
from pathlib import Path
from scrape_hrbeu import rebuild_saved_page, school_cutoff
from datetime import datetime, timezone


class SnapshotTests(unittest.TestCase):
    def test_cutoff_is_china_time_even_on_utc_runner(self):
        instant = datetime(2026, 9, 17, 4, 0, tzinfo=timezone.utc)
        self.assertEqual(school_cutoff(instant=instant), datetime(2026, 9, 17, 12, 0))
        self.assertEqual(school_cutoff('2026-09-16', instant), datetime(2026, 9, 16))
        midnight = datetime(2026, 9, 17, 17, 0, tzinfo=timezone.utc)
        self.assertEqual(school_cutoff(instant=midnight), datetime(2026, 9, 18, 1, 0))

    def test_keeps_source_time_and_merges_review(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            timestamp = '2026-09-08T20:03:33+08:00'
            root.joinpath('index.html').write_text('<script type="application/json" id="eventData">[{"company":"测试企业"}]</script>'
                '<script type="application/json" id="metaData">' + json.dumps({'fetchedAt':timestamp}) + '</script>', encoding='utf-8')
            root.joinpath('template.html').write_text('__EVENT_DATA__\n__META_DATA__', encoding='utf-8')
            root.joinpath('reviews').mkdir()
            root.joinpath('reviews/xhs-reviewed.json').write_text(json.dumps({'generatedAt':'2026-09-09T00:00:00+00:00',
                'reports':[{'company':'测试企业','overallScore':None}]}), encoding='utf-8')
            rebuild_saved_page(root, root/'out.html')
            events, meta = map(json.loads, (root/'out.html').read_text(encoding='utf-8').splitlines())
            self.assertEqual(events[0]['xhsResearch']['company'], '测试企业')
            # UTC offset may be normalized to the machine timezone, instant must not change.
            from datetime import datetime
            self.assertEqual(datetime.fromisoformat(meta['fetchedAt']), datetime.fromisoformat(timestamp))
            self.assertIn('刷新失败', meta['schoolRefreshWarning'])

    def test_empty_or_broken_snapshot_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for value in ('invalid', '<script type="application/json" id="eventData">[]</script><script type="application/json" id="metaData">{}</script>'):
                (root/'index.html').write_text(value, encoding='utf-8')
                with self.assertRaises(ValueError): rebuild_saved_page(root, root/'out.html')
                self.assertFalse((root/'out.html').exists())

if __name__ == '__main__':
    unittest.main()
