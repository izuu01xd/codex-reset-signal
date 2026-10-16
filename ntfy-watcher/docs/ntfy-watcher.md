# ntfy Codex reset watcher

Independent of the upstream monitor, CI, and Pages workflows. Polls
https://raw.githubusercontent.com/izuu01xd/codex-reset-signal/monitor-state/feed.xml
every five minutes at minutes 3, 8, ..., 58.
Only category `reset` is delivered; `bank_credit` is excluded. This watches public
announcements, not your individual account quota or reset timer.

## Enable

1. Repository Settings > Secrets and variables > Actions > New repository secret:
   name `NTFY_TOPIC`, value your existing topic name only. Never commit the value.
2. Actions > enable workflows if the fork shows an enable banner.
3. Actions > Ntfy Codex reset watcher > Run workflow, leave test unchecked.
   The first successful run saves a baseline without sending old events.
4. Optionally run again with `test_notification` checked for one labeled phone
   test. A test does not initialize or modify the baseline.

The workflow requests contents write permission. If repository policy or branch
protection rejects state updates, allow this workflow to update the default
branch, or adapt the storage destination; do not bypass organization rules.

## Persistence and recovery

`.ntfy-watcher-state.json` on the default branch stores GUIDs and statuses only,
never the topic. State is retained indefinitely, avoiding cache eviction and
artifact expiry. Commits happen only on initialization or new events. Each
update uses the current blob SHA, so conflicting updates fail safely. Workflow
concurrency serializes scheduled and manual runs. GITHUB_TOKEN state commits do
not recursively trigger push workflows.

A durable `claimed` checkpoint is saved BEFORE publishing and `sent` afterward.
This favors avoiding duplicate notifications. ntfy and GitHub cannot share a
transaction: a crash or ambiguous HTTP outcome can leave an uncertain delivery.
The next run fails visibly rather than automatically replaying or silently
skipping it. Check the phone/ntfy history for that event, then edit the state
file in GitHub: set that GUID to `sent` if received, or remove only that GUID to
retry if certain it was not received. Removing a GUID may duplicate a message
if it actually arrived. Do not delete the entire state file: that establishes
a fresh silent baseline. Network/XML failures never overwrite state. A failed
baseline save never sends notifications. Old GUIDs are never pruned.

## Limits and checks

GitHub schedules can be delayed or dropped and public repositories' scheduled
workflows can be disabled after 60 days without repository activity. Check
Actions if notifications stop; re-enable the workflow if needed. A five-minute
cron is not a delivery-time guarantee. Events that disappear from the feed
between successful polls cannot be recovered by this watcher.

No external Python packages are required. Local checks:

```sh
python -m py_compile scripts/ntfy-watch.py
python -m unittest discover -s tests -p 'ntfy_watch_test.py'
actionlint .github/workflows/ntfy-watch.yml
```
