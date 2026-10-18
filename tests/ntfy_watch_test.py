import copy
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('watcher', Path(__file__).parents[1] / 'scripts/ntfy-watch.py')
watcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(watcher)
NOW = datetime(2026, 10, 18, tzinfo=timezone.utc)
OLD = '2026-10-17T16:20:57.000Z'
NEW = '2026-10-19T00:00:00Z'


def post(identity='1', text='Day 13/ Le limit reset', created=NEW, **extra):
    return dict(id=identity, text=text, createdAt=created, **extra)


def parse(*posts):
    return watcher.parse_matches(json.dumps({'username': 'thsottiaux', 'matches': posts}))


def migrated(events=None):
    return {'version': 1, 'rule': watcher.RULE, 'baselineAt': NOW.isoformat(), 'events': events or {}}


class MemoryStore:
    def __init__(self, state=None):
        self.state = state
        self.saves = []

    def load(self):
        return copy.deepcopy(self.state)

    def save(self, state):
        self.state = copy.deepcopy(state)
        self.saves.append(copy.deepcopy(state))


class WatcherTests(unittest.TestCase):
    def test_source_is_repository_monitor_state(self):
        self.assertEqual(watcher.SOURCE, 'https://raw.githubusercontent.com/izuu01xd/codex-reset-signal/monitor-state/state.json')

    def test_reset_case_insensitive_and_substring(self):
        for text in ['reset', 'Reset', 'RESET', 'a ReSeT today', 'resets']:
            with self.subTest(text=text):
                self.assertEqual(parse(post(text=text))['1']['description'], text)
        self.assertEqual(parse(post(text='bank credits')), {})

    def test_uncertain_mention_notified_with_original_text_and_x_link(self):
        original = 'The reports of my reset button being lost are greatly exaggerated\n\nDay 10/ Reset'
        events = parse(post(text=original, events=[{'type': 'mention', 'status': 'uncertain'}]))
        delivered = []
        watcher.watch(events, MemoryStore(migrated()), delivered.append)
        self.assertEqual(delivered[0]['description'], original)
        self.assertEqual(delivered[0]['link'], 'https://x.com/thsottiaux/status/1')

    def test_duplicate_post_and_reclassification_only_notify_once(self):
        store = MemoryStore(migrated())
        delivered = []
        watcher.watch(parse(post(), post(events=[{'type': 'reset', 'status': 'confirmed'}])), store, delivered.append)
        watcher.watch(parse(post(text='Reset edited text')), store, delivered.append)
        self.assertEqual(len(delivered), 1)
        self.assertEqual(store.state['events']['1'], 'sent')

    def test_fresh_baseline_then_only_new_no_replay(self):
        store = MemoryStore()
        delivered = []
        watcher.watch(parse(post(created=OLD)), store, delivered.append, now=NOW)
        self.assertEqual(delivered, [])
        watcher.watch(parse(post(created=OLD), post('2')), store, delivered.append)
        watcher.watch(parse(post('2')), store, delivered.append)
        self.assertEqual(len(delivered), 1)
        self.assertEqual(store.state['events'], {'1': 'baseline', '2': 'sent'})

    def test_first_rule_migration_preserves_all_legacy_records_no_backfill(self):
        legacy = {'10:reset': 'sent', '11:reset': 'baseline', '12:bank_credit': 'sent'}
        store = MemoryStore({'version': 1, 'events': legacy, 'extra': 'preserved'})
        watcher.watch(parse(post('2111492673890824348', created=OLD), post('2110595484180214059', created=OLD)), store, self.fail, now=NOW)
        for identity, status in legacy.items():
            self.assertEqual(store.state['events'][identity], status)
            self.assertEqual(store.state['events'][identity.split(':')[0]], status)
        self.assertEqual(store.state['extra'], 'preserved')
        self.assertEqual(store.state['events']['2111492673890824348'], 'baseline')
        self.assertEqual(store.state['events']['2110595484180214059'], 'baseline')
        self.assertEqual(store.state['rule'], watcher.RULE)
        watcher.watch(parse(post('10'), post('11'), post('12')), store, self.fail)
        self.assertEqual(len(store.saves), 1)

    def test_older_posts_appearing_after_migration_are_baselined(self):
        store = MemoryStore(migrated())
        watcher.watch(parse(post(created=OLD), post('2', created=NOW.isoformat())), store, self.fail)
        self.assertEqual(store.state['events'], {'2': 'baseline', '1': 'baseline'})

    def test_empty_migration_is_persisted_once(self):
        store = MemoryStore({'version': 1, 'events': {}})
        watcher.watch({}, store, self.fail, now=NOW)
        watcher.watch({}, store, self.fail)
        self.assertEqual(len(store.saves), 1)

    def test_uncertain_delivery_blocks_replay(self):
        store = MemoryStore(migrated())
        def fail(event):
            self.assertEqual(store.state['events']['1'], 'claimed')
            raise TimeoutError()
        with self.assertRaises(TimeoutError):
            watcher.watch(parse(post()), store, fail)
        with self.assertRaises(RuntimeError):
            watcher.watch(parse(post()), store, self.fail)

    def test_legacy_claim_blocks_migration_without_changes(self):
        store = MemoryStore({'version': 1, 'events': {'1:reset': 'claimed'}})
        before = copy.deepcopy(store.state)
        with self.assertRaises(RuntimeError):
            watcher.watch(parse(post()), store, self.fail, now=NOW)
        self.assertEqual(store.state, before)
        self.assertEqual(store.saves, [])

    def test_failed_checkpoint_never_publishes(self):
        for state in [None, {'version': 1, 'events': {}}, migrated()]:
            store = MemoryStore(state)
            def fail(state):
                raise OSError()
            store.save = fail
            with self.assertRaises(OSError):
                watcher.watch(parse(post()), store, self.fail, now=NOW)

    def test_malformed_source_never_initializes_baseline(self):
        for data in ['{}', '{', json.dumps({'username': 'someone', 'matches': []}), json.dumps({'username': 'thsottiaux', 'matches': None})]:
            with self.assertRaises((ValueError, TypeError)):
                watcher.parse_matches(data)
        for bad in [post(identity=''), post(identity='1:reset'), post(created='bad'), post(created='2026-10-19')]:
            with self.assertRaises(ValueError):
                parse(bad)

    def test_notification_title_and_body_do_not_claim_reset(self):
        event = parse(post(text='Maybe Reset?'))['1']
        with patch.object(watcher, 'request', return_value=b'{"event":"message","id":"receipt"}') as request:
            watcher.publish(event, 'test-topic')
        args = request.call_args.args
        self.assertEqual(args[0], 'https://ntfy.sh/test-topic')
        self.assertEqual(args[1].decode(), 'Maybe Reset?\n\nhttps://x.com/thsottiaux/status/1')
        self.assertEqual(args[2]['Title'], 'Tibo mentioned reset')
        self.assertEqual(args[2]['Click'], event['link'])

    def test_main_test_notification_is_labelled_and_never_touches_state(self):
        with patch.dict(watcher.os.environ, {'NTFY_TOPIC': 'test-topic', 'TEST_NOTIFICATION': 'true'}), patch.object(watcher, 'Store') as store, patch.object(watcher, 'request', return_value=b'{"event":"message","id":"receipt"}') as request:
            watcher.main()
        store.assert_not_called()
        self.assertEqual(request.call_count, 1)
        args = request.call_args.args
        self.assertTrue(args[2]['Title'].startswith('TEST:'))
        self.assertIn('TEST ONLY', args[1].decode())

    def test_ntfy_missing_acknowledgment_leaves_claimed(self):
        store = MemoryStore(migrated())
        with patch.object(watcher, 'request', return_value=b'{}'), self.assertRaises(ValueError):
            watcher.watch(parse(post()), store, lambda e: watcher.publish(e, 'test-topic'))
        self.assertEqual(store.state['events']['1'], 'claimed')

    def test_invalid_saved_state_never_resets_baseline(self):
        import base64
        for state in [{'version': 2, 'events': {}}, {'version': 1, 'events': {'1': 'bad'}}, {'version': 1, 'events': {}, 'rule': 'unknown'}, {'version': 1, 'events': {}, 'rule': watcher.RULE, 'baselineAt': 'bad'}]:
            response = json.dumps({'sha': 'sha', 'content': base64.b64encode(json.dumps(state).encode()).decode()}).encode()
            with patch.dict(watcher.os.environ, {'GITHUB_REPOSITORY': 'izuu01xd/codex-reset-signal', 'STATE_BRANCH': 'main', 'GH_TOKEN': 'test'}), patch.object(watcher, 'request', return_value=response):
                with self.assertRaises(ValueError):
                    watcher.watch(parse(post()), watcher.Store(), self.fail)


if __name__ == '__main__':
    unittest.main()
