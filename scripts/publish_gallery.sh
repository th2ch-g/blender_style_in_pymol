#!/usr/bin/env bash
set -euo pipefail

gallery=$(cd "$1" && pwd)
publication=$2
cd "$publication"
if git fetch origin gallery --depth=1; then
    git checkout -B gallery FETCH_HEAD
else
    git checkout --orphan gallery
fi
git rm -rf --ignore-unmatch .
cp -R "$gallery"/. .
git config user.name 'github-actions[bot]'
git config user.email '41898282+github-actions[bot]@users.noreply.github.com'
git add --all
if ! git diff --cached --quiet; then
    git commit -m "Update rendered gallery for ${GITHUB_SHA:-local}"
    git push origin gallery
fi
