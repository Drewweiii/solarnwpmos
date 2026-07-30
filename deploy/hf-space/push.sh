#!/usr/bin/env bash
# Sync this monorepo's API into a Hugging Face Space and push it.
#
# A Docker Space builds from a `Dockerfile` at the ROOT of its own git repo, so
# the source cannot simply be a subdirectory of this one. This script assembles
# that layout in a temp clone: the HF Dockerfile and README go to the root, and
# only the paths that Dockerfile actually COPYs come along under nongfab-ems/.
#
# It copies a SUBSET on purpose - no web/, no tests, no node_modules, no
# .venv, no mlruns. Those would add hundreds of MB to a repo that is pushed
# over the network on every deploy, and the image never reads them.
#
# Usage:
#   deploy/hf-space/push.sh <hf-username>/<space-name> ["commit message"]
#
# Requires: git, and an HF token with write access. If the push prompts for a
# password, paste a token from https://huggingface.co/settings/tokens (a
# "Write" token) - HF does not accept an account password over git.
set -euo pipefail

SPACE_ID="${1:-}"
COMMIT_MSG="${2:-Sync API from source repo}"

if [[ -z "$SPACE_ID" ]]; then
  echo "usage: $0 <hf-username>/<space-name> [\"commit message\"]" >&2
  exit 2
fi

# Resolve the source repo root from this script's own location, so the script
# works regardless of the caller's cwd.
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/../.." && pwd)"

if [[ ! -d "$REPO_ROOT/nongfab-ems/api" ]]; then
  echo "error: $REPO_ROOT does not look like the source repo (no nongfab-ems/api)" >&2
  exit 1
fi

# Exactly the paths deploy/hf-space/Dockerfile COPYs. Keep this list in step
# with it - a path here that the Dockerfile ignores is dead weight, and one
# the Dockerfile needs but is missing here fails the build.
PATHS=(
  libs/nongfab_common/pyproject.toml libs/nongfab_common/src
  features/pyproject.toml features/src
  forecast/pyproject.toml forecast/src
  simulation/pyproject.toml simulation/src
  financial/pyproject.toml financial/src
  ingestion/nwp/pyproject.toml ingestion/nwp/src
  ingestion/himawari/pyproject.toml ingestion/himawari/src
  ingestion/nasa_power/pyproject.toml ingestion/nasa_power/src
  ingestion/pvgis/pyproject.toml ingestion/pvgis/src
  api/pyproject.toml api/src
  config/assets.yaml
)

WORK="$(mktemp -d)"
# Only ever removes the temp dir this script made itself.
trap 'rm -rf "$WORK"' EXIT

echo "==> cloning Space $SPACE_ID"
git clone "https://huggingface.co/spaces/$SPACE_ID" "$WORK/space"
cd "$WORK/space"

# Replace the tracked source wholesale rather than merging: a file deleted or
# renamed upstream must disappear here too, otherwise a stale module keeps
# getting installed and the Space runs code the repo no longer has.
echo "==> staging source"
rm -rf nongfab-ems Dockerfile README.md
for path in "${PATHS[@]}"; do
  dest="nongfab-ems/$path"
  mkdir -p "$(dirname "$dest")"
  cp -R "$REPO_ROOT/nongfab-ems/$path" "$dest"
done

# __pycache__ dirs ride along inside src/ copies; they are noise in git and can
# shadow a stale .pyc into the image.
find nongfab-ems -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
find nongfab-ems -name '*.pyc' -delete 2>/dev/null || true

cp "$HERE/Dockerfile" ./Dockerfile
cp "$HERE/README.md" ./README.md

if git diff --quiet && git diff --cached --quiet && [[ -z "$(git status --porcelain)" ]]; then
  echo "==> nothing changed; Space is already up to date"
  exit 0
fi

echo "==> committing and pushing"
git add -A
git -c user.email="deploy@localhost" -c user.name="hf-space-sync" commit -m "$COMMIT_MSG"
git push

cat <<EOF

==> pushed. The Space is now building.
    Logs:     https://huggingface.co/spaces/$SPACE_ID?logs=build
    Base URL: https://$(echo "$SPACE_ID" | tr '/' '-' | tr '[:upper:]' '[:lower:]').hf.space

    Reminder: the API base URL above must also be set as VITE_API_URL for the
    Cloudflare Pages build, and added to API_CORS_ORIGINS in the Space's
    Settings -> Variables and secrets. See deploy/hf-space/SETUP.md.
EOF
