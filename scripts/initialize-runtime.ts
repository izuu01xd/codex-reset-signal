import { mkdir, readdir, writeFile } from "node:fs/promises";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { loadConfig } from "../src/config";
import { buildPublicStatus, writePublicFeed, writePublicStatus } from "../src/public-status";
import { emptyState, writeState } from "../src/state";

export async function initializeRuntime(directory: string): Promise<void> {
  await mkdir(directory, { recursive: true });
  if ((await readdir(directory)).length) {
    throw new Error("Runtime initialization requires an empty directory; refusing to overwrite state");
  }
  const config = loadConfig();
  const state = emptyState(config.username, config.keyword);
  const status = buildPublicStatus(state, config.sourceProvider);
  await writeState(join(directory, "state.json"), state);
  await writePublicStatus(join(directory, "status.json"), status);
  await writePublicFeed(join(directory, "feed.xml"), status);
  await writeFile(join(directory, ".gitignore"), "*.lock\n*.tmp\n", "utf8");
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const directory = process.argv[2];
  if (!directory) throw new Error("Usage: initialize-runtime.ts <empty-directory>");
  await initializeRuntime(directory);
}
