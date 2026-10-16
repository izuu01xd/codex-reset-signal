#!/usr/bin/env bash
set -euo pipefail

if git ls-remote --exit-code --heads origin refs/heads/monitor-state >/dev/null; then
  exit 0
else
  result=$?
  if [ "$result" -ne 2 ]; then
    exit "$result"
  fi
fi

init_dir=$(mktemp -d)
trap 'rm -rf "$init_dir"' EXIT
node --import tsx scripts/initialize-runtime.ts "$init_dir"
git -C "$init_dir" init --initial-branch=monitor-state
git -C "$init_dir" config user.name "reset-signal[bot]"
git -C "$init_dir" config user.email "reset-signal[bot]@users.noreply.github.com"
git -C "$init_dir" add state.json status.json feed.xml .gitignore
git -C "$init_dir" commit -m "chore: initialize isolated monitor runtime"
git fetch "$init_dir" refs/heads/monitor-state
if ! git push origin FETCH_HEAD:refs/heads/monitor-state; then
  git ls-remote --exit-code --heads origin refs/heads/monitor-state >/dev/null
fi
