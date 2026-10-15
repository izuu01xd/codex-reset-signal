import base64
import json
import os
import re
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET


FEED = "https://raw.githubusercontent.com/AllenXiao95/codex-reset-signal/monitor-state/feed.xml"STATE_PATH = ".ntfy-watcher-state.json"


def request(url, data=None, headers=None, method=None):
    with urllib.request.urlopen(
        urllib.request.Request(url, data=data, headers=headers or {}, method=method),
        timeout=30,
    ) as response:
        return response.read()


def parse_feed(data):
    root = ET.fromstring(data)
    if root.tag != "rss" or root.find("channel") is None:
        raise ValueError("Expected an RSS channel")
    events = {}
    for item in root.findall("./channel/item"):
        if item.findtext("category") != "reset":
            continue
        identity = (item.findtext("guid") or "").strip()
        link = (item.findtext("link") or "").strip()
        if not identity or not link.startswith("https://"):
            raise ValueError("Reset event requires a GUID and HTTPS link")
        events[identity] = {
            "title": item.findtext("title") or "Codex reset",
            "link": link,
            "description": item.findtext("description") or "",
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


def watch(events, store, publish):
    state = store.load()
    if state is None:
        store.save({"version": 1, "events": dict.fromkeys(events, "baseline")})
        print("Baseline saved; no old notifications sent.")
        return
    if "claimed" in state["events"].values():
        raise RuntimeError("Uncertain delivery checkpoint: inspect state and ntfy before recovery")
    for identity, event in reversed(list(events.items())):
        if identity in state["events"]:
            continue
        state["events"][identity] = "claimed"
        store.save(state)
        publish(event)
        state["events"][identity] = "sent"
        store.save(state)
        print("New reset notification delivered and checkpointed.")


def publish(event, topic):
    body = event["title"] + "\n\n" + event["description"] + "\n\n" + event["link"]
    request("https://ntfy.sh/" + topic, body.encode(), {
        "Title": "Codex reset detected",
        "Priority": "high",
        "Tags": "arrows_counterclockwise,robot",
        "Click": event["link"],
        "Content-Type": "text/plain; charset=utf-8",
    })


def main():
    topic = os.environ.get("NTFY_TOPIC", "")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", topic):
        raise ValueError("Set NTFY_TOPIC to a valid topic name (not a URL)")
    if os.environ.get("TEST_NOTIFICATION") == "true":
        publish({"title": "TEST: Codex watcher connection", "description": "Manual test; watcher state unchanged.", "link": FEED}, topic)
        print("Test notification sent; state unchanged.")
        return
    events = parse_feed(request(FEED))
    watch(events, Store(), lambda event: publish(event, topic))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print("Watcher failed (" + type(error).__name__ + "); inspect connectivity, permissions, and saved checkpoints.", file=sys.stderr)
        sys.exit(1)
