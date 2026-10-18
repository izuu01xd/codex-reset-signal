import base64
from datetime import datetime, timezone
import json
import os
import re
import sys
import urllib.error
import urllib.request


SOURCE = "https://raw.githubusercontent.com/izuu01xd/codex-reset-signal/monitor-state/state.json"
STATE_PATH = ".ntfy-watcher-state.json"
RULE = "reset-mentions-v1"

def request(url, data=None, headers=None, method=None):
    with urllib.request.urlopen(
        urllib.request.Request(url, data=data, headers=headers or {}, method=method),
        timeout=30,
    ) as response:
        return response.read()


def timestamp(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("Expected a timezone-aware timestamp")
    return result


def parse_matches(data):
    source = json.loads(data)
    if source.get("username") != "thsottiaux" or not isinstance(source.get("matches"), list):
        raise ValueError("Expected @thsottiaux monitor matches")
    events = {}
    for post in source["matches"]:
        text = post["text"]
        if "reset" not in text.casefold():
            continue
        identity = post["id"]
        if not isinstance(identity, str) or not re.fullmatch(r"[0-9]+", identity):
            raise ValueError("Reset mention requires a numeric post ID")
        timestamp(post["createdAt"])
        events[identity] = {
            "link": "https://x.com/thsottiaux/status/" + identity,
            "description": text,
            "createdAt": post["createdAt"],
        }
    return events


class Store:
    def __init__(self):
        self.url = (
            "https://api.github.com/repos/"
            + os.environ["GITHUB_REPOSITORY"]
            + "/contents/" + STATE_PATH
        )
        self.branch = os.environ["STATE_BRANCH"]
        self.headers = {
            "Authorization": "Bearer " + os.environ["GH_TOKEN"],
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        self.sha = None

    def load(self):
        try:
            result = json.loads(request(self.url + "?ref=" + self.branch, headers=self.headers))
        except urllib.error.HTTPError as error:
            if error.code == 404:
                return None
            raise
        self.sha = result["sha"]
        state = json.loads(base64.b64decode(result["content"]))
        if state.get("version") != 1 or not isinstance(state.get("events"), dict):
            raise ValueError("Invalid saved state; refusing to reset baseline")
        if any(value not in ("baseline", "claimed", "sent") for value in state["events"].values()):
            raise ValueError("Invalid event status")
        if "rule" in state:
            if state["rule"] != RULE:
                raise ValueError("Unknown watcher rule; refusing to reset baseline")
            timestamp(state["baselineAt"])
        return state

    def save(self, state):
        payload = {
            "message": "chore: checkpoint ntfy watcher",
            "branch": self.branch,
            "content": base64.b64encode((json.dumps(state, indent=2) + "\n").encode()).decode(),
        }
        if self.sha:
            payload["sha"] = self.sha
        result = json.loads(request(self.url, json.dumps(payload).encode(), self.headers, "PUT"))
        self.sha = result["content"]["sha"]


def watch(events, store, publish, now=None):
    state = store.load()
    if state is None:
        state = {"version": 1, "events": {}}
    if "claimed" in state["events"].values():
        raise RuntimeError("Uncertain delivery checkpoint: inspect state and ntfy before recovery")
    if state.get("rule") != RULE:
        # Retain all legacy GUID checkpoints and add post-ID aliases. A parser
        # reclassification or text edit must never replay an already seen post.
        for identity, status in list(state["events"].items()):
            post_id = identity.split(":", 1)[0]
            if re.fullmatch(r"[0-9]+", post_id):
                state["events"].setdefault(post_id, status)
        for identity in events:
            state["events"].setdefault(identity, "baseline")
        state["rule"] = RULE
        state["baselineAt"] = (now or datetime.now(timezone.utc)).isoformat()
        store.save(state)
        print("Reset mention baseline saved; no historical notifications sent.")
        return
    for identity, event in reversed(list(events.items())):
        if identity in state["events"]:
            continue
        # Older posts can reappear in matches after a monitor/parser refresh.
        if timestamp(event["createdAt"]) <= timestamp(state["baselineAt"]):
            state["events"][identity] = "baseline"
            store.save(state)
            continue
        state["events"][identity] = "claimed"
        store.save(state)
        publish(event)
        state["events"][identity] = "sent"
        store.save(state)
        print("New reset mention notification delivered and checkpointed.")


def publish(event, topic, test=False):
    title = "TEST: Tibo reset watcher" if test else "Tibo mentioned reset"
    body = event["description"] + "\n\n" + event["link"]
    response = json.loads(request("https://ntfy.sh/" + topic, body.encode(), {
        "Title": title,
        "Priority": "high",
        "Tags": "arrows_counterclockwise,robot",
        "Click": event["link"],
        "Content-Type": "text/plain; charset=utf-8",
    }))
    if response.get("event") != "message" or not response.get("id"):
        raise ValueError("ntfy did not acknowledge the notification")
    print("ntfy accepted message ID: " + response["id"])


def main():
    topic = os.environ.get("NTFY_TOPIC", "")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", topic):
        raise ValueError("Set NTFY_TOPIC to a valid topic name (not a URL)")
    if os.environ.get("TEST_NOTIFICATION") == "true":
        publish({"description": "TEST ONLY: GitHub Actions to ntfy connection test. This is not a reset announcement. Watcher state unchanged.", "link": SOURCE}, topic, test=True)
        print("Test notification sent; state unchanged.")
        return
    events = parse_matches(request(SOURCE))
    print("Read " + str(len(events)) + " reset mentions from monitor-state/state.json.")
    watch(events, Store(), lambda event: publish(event, topic))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print("Watcher failed (" + type(error).__name__ + "); inspect connectivity, permissions, and saved checkpoints.", file=sys.stderr)
        sys.exit(1)
