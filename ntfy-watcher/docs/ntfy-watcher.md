# ntfy reset mention watcher

Every five minutes (minutes 3, 8, ..., 58), the watcher reads this repository's
`monitor-state/state.json` at
https://raw.githubusercontent.com/izuu01xd/codex-reset-signal/monitor-state/state.json.
It reads `matches` for @thsottiaux and sends any post whose original text contains
`reset`, case-insensitively, including `mention` / `uncertain` classifications.
RSS categories and event confirmation do not control ntfy notifications.

The title is **Tibo mentioned reset**. The body includes the original post text
and its canonical X link. A mention does not confirm that a reset happened.
The existing X/FxEmbed monitor and RSS generation are unchanged.

## Enable and test

1. Run **Monitor X for reset** to collect posts into the isolated `monitor-state`
   branch, if needed. Existing runtime state is never overwritten.
2. Keep the existing Actions secret `NTFY_TOPIC` (topic name only, never a URL).
3. Run **Ntfy Codex reset watcher** with `test_notification` unchecked. The first
   successful run establishes a silent baseline, including when migrating an
   existing RSS watcher. Historical posts, including October 15 and 17 mentions,
   are not sent. Any historical backfill requires separate explicit approval.
4. Run with `test_notification` checked to send one notification with **TEST:**
   in its title and **TEST ONLY** in its body. This does not read or modify
   watcher state. Logs include the ntfy acknowledgment message ID, never the topic.

The existing schedule, `contents: write` permission, and workflow concurrency
remain in place. GitHub schedules can be delayed or disabled; check Actions if
notifications stop. The schedule is not a delivery-time guarantee.

## Persistence and migration

`.ntfy-watcher-state.json` on the default branch retains its version 1 format
and every existing `events` record. The one-time `rule: reset-mentions-v1`
migration adds post-ID aliases for legacy `postID:eventType` GUIDs, baselines
all currently matching posts, and records `baselineAt`. Posts created at or
before that time are also silently baselined if they appear in a later poll.
Newer posts are deduplicated by X post ID, regardless of text edits, duplicate
matches, or changed classifications. IDs are retained indefinitely.

A durable `claimed` checkpoint is saved BEFORE publishing and `sent` afterward.
ntfy must acknowledge a message ID before the watcher saves `sent`. GitHub and
ntfy cannot share a transaction, so an ambiguous delivery or failed final save
can leave `claimed`. The next run fails visibly to avoid duplicate delivery,
including during migration. Inspect ntfy history before setting the relevant
record to `sent`, or removing it to retry only when delivery did not occur.
Do not delete the whole state file: that creates a new silent baseline.

Each save uses the current GitHub blob SHA to fail safely on concurrent changes.
Invalid JSON, invalid saved checkpoints, or source/network failures do not reset
the baseline. A failed checkpoint save never publishes. The watcher does not
store the ntfy topic. `GITHUB_TOKEN` state commits do not trigger push workflows.
Repository policy must permit the workflow to update the default branch.

Posts that never appear in the monitor's retained `matches` cannot be recovered
by the watcher. Receiving an ntfy acknowledgment verifies server acceptance;
phone delivery still depends on the subscribed client and its connectivity.

## Local checks

No external Python packages are required:

```sh
python -m unittest discover -s tests -p 'ntfy_watch_test.py'
python -m unittest discover -s ntfy-watcher/tests -p 'ntfy_watch_test.py'
```

The standalone `ntfy-watcher/` copy is kept in sync with the root watcher.
