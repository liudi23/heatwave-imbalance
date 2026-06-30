#!/usr/bin/env bash
#
# One-shot local git setup for the heatwave-Imbalance project.
#
# Targets the existing GitHub repo  liudi23/heatwave-imbalance  and pushes this
# initial version to the  mvp  branch.
#
# Why this exists: the project files were created from a sandboxed folder mount
# that blocks file deletion, so git could not run there (it left a half-built
# .git/ with a stale index.lock). Run this from your own terminal, which has
# full permissions:
#
#     cd ~/Documents/Claude/Projects/heatwave-Imbalance
#     bash setup_git.sh

set -euo pipefail

# Run from the directory this script lives in, wherever it's invoked from.
cd "$(dirname "$0")"

REMOTE_URL="https://github.com/liudi23/heatwave-imbalance.git"
BRANCH="mvp"
GIT_USER_NAME="Di Liu"
GIT_USER_EMAIL="liudisy@gmail.com"

echo "==> Working in: $(pwd)"

# 1. Clear any broken partial repo the sandbox left behind.
if [ -d .git ]; then
  echo "==> Removing existing .git/ (partial/broken init)…"
  rm -rf .git
fi

# 2. Initialise on the mvp branch and make the first commit.
echo "==> git init on branch '$BRANCH' + first commit…"
git init -b "$BRANCH"
git config user.name  "$GIT_USER_NAME"
git config user.email "$GIT_USER_EMAIL"
# Drop any stray sandbox artefact before staging.
rm -f _perm_test.txt
git add -A
git commit -m "Phase 1: heatwave stress on GB balancing — scaffold, BMRS fetchers, anchor figure

- Scope (PHASE1_SCOPE.md): climate-resilience framing, hypotheses H1-H5
- Reuses uk-system-price-forecast conventions; vendors fetch_elexon/fetch_weather
- New BMRS fetchers: fetch_demand (INDO/ITSDO), fetch_fuelhh (gen+interconnectors)
- Anchor figure: hot vs mild summer diurnal price/NIV profile (2021-2026)
- docs/DATA_SOURCES.md confirms dataset IDs/endpoints; MIT license"

echo
echo "==> Local commit ready:"
git log --oneline -1

# 3. Point at the existing GitHub repo and push to the mvp branch.
#    The remote mvp may already hold GitHub's auto-init commit (README/license
#    added at repo creation). We overwrite it with this project history using
#    the safe force variant: --force-with-lease only overwrites if nothing new
#    landed on the remote since our fetch.
echo
echo "==> Adding remote and pushing to '$BRANCH' (overwriting auto-init)…"
git remote add origin "$REMOTE_URL" 2>/dev/null || git remote set-url origin "$REMOTE_URL"
git fetch origin
git push -u origin "$BRANCH" --force-with-lease

echo
echo "==> Done. Pushed to $REMOTE_URL ($BRANCH)."
echo "    View: https://github.com/liudi23/heatwave-imbalance/tree/$BRANCH"
