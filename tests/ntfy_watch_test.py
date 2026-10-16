import copy
import importlib.util
from pathlib import Path
import unittest


spec = importlib.util.spec_from_file_location("watcher", Path(__file__).parents[1] / "scripts/ntfy-watch.py")
watcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(watcher)


class MemoryStore:
    def __init__(self, state=None):
        self.state = state

    def load(self):
        return copy.deepcopy(self.state)

    def save(self, state):
        self.state = copy.deepcopy(state)


class WatcherTests(unittest.TestCase):
    def test_feed_belongs_to_this_repository(self):
        self.assertEqual(watcher.FEED, "https://raw.githubusercontent.com/izuu01xd/codex-reset-signal/monitor-state/feed.xml")

    def test_baseline_then_only_new_and_no_replay(self):
        store = MemoryStore()
        delivered = []
        watcher.watch({"old": {}}, store, delivered.append)
        self.assertEqual(delivered, [])
        watcher.watch({"new": {"title": "new"}, "old": {}}, store, delivered.append)
        watcher.watch({"new": {}, "old": {}}, store, delivered.append)
        self.assertEqual(delivered, [{"title": "new"}])
        self.assertEqual(store.state["events"]["new"], "sent")

    def test_uncertain_delivery_blocks_replay(self):
        store = MemoryStore({"version": 1, "events": {}})
        def fail(event):
            self.assertEqual(store.state["events"]["new"], "claimed")
            raise TimeoutError()
        with self.assertRaises(TimeoutError):
            watcher.watch({"new": {}}, store, fail)
        with self.assertRaises(RuntimeError):
            watcher.watch({"new": {}}, store, self.fail)

    def test_failed_checkpoint_never_publishes(self):
        store = MemoryStore({"version": 1, "events": {}})
        def fail(state):
            raise OSError()
        store.save = fail
        with self.assertRaises(OSError):
            watcher.watch({"new": {}}, store, self.fail)

    def test_rss_filter_and_guid_dedup(self):
        data = b'<rss><channel><item><category>bank_credit</category></item><item><category>reset</category><guid>1:reset</guid><link>https://x.com/a/status/1</link></item><item><category>reset</category><guid>1:reset</guid><link>https://x.com/a/status/1</link></item></channel></rss>'
        self.assertEqual(list(watcher.parse_feed(data)), ["1:reset"])
        with self.assertRaises(ValueError):
            watcher.parse_feed(b'<html/>')
        with self.assertRaises(ValueError):
            watcher.parse_feed(b'<rss><channel><item><category>reset</category></item></channel></rss>')


if __name__ == "__main__":
    unittest.main()
