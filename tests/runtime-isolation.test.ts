import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { initializeRuntime } from "../scripts/initialize-runtime";

describe("independent runtime initialization", () => {
  it("creates valid state, status and RSS without claiming a successful check", async () => {
    const directory = await mkdtemp(join(tmpdir(), "reset-runtime-test-"));
    try {
      await initializeRuntime(directory);
      const state = JSON.parse(await readFile(join(directory, "state.json"), "utf8"));
      const status = JSON.parse(await readFile(join(directory, "status.json"), "utf8"));
      const feed = await readFile(join(directory, "feed.xml"), "utf8");
      expect(state).toMatchObject({ version: 2, username: "thsottiaux", keyword: "reset", sinceId: null, outbox: [], seen: {} });
      expect(status.monitor).toMatchObject({ provider: "fxembed", lastCheckedAt: null, lastRunStatus: "waiting-for-first-run" });
      expect(feed).toContain('<rss version="2.0">');
      expect(feed).toContain("</channel>\n</rss>");
      await expect(initializeRuntime(directory)).rejects.toThrow("refusing to overwrite");
      expect(JSON.parse(await readFile(join(directory, "state.json"), "utf8"))).toEqual(state);
    } finally {
      await rm(directory, { recursive: true, force: true });
    }
  });

  it("uses this fork for every default runtime endpoint", async () => {
    for (const path of ["app/api/status/route.ts", "app/feed.xml/route.ts", "app/ResetDashboard.tsx", "pages/index.html", "workers/scheduler/index.mjs", "scripts/ntfy-watch.py", "ntfy-watcher/scripts/ntfy-watch.py"]) {
      const content = await readFile(path, "utf8");
      expect(content).toContain("izuu01xd/codex-reset-signal");
      expect(content).not.toMatch(/raw\.githubusercontent\.com\/AllenXiao95\//);
      expect(content).not.toContain("https://reset.onlyax.com");
    }
  });
});
