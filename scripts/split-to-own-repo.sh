#!/bin/sh
# Move this project into its own git repository, keeping its history.
#
# The harness was developed inside the `gen` repository because the GitHub App
# running the session could not create repositories (403: administration:write).
# Once you have created an empty repo, this moves it across with history intact.
#
#   1. Create an empty repository on GitHub named `mdmp` (no README, no
#      .gitignore — it must be empty).
#   2. From the root of the gen repository:
#
#        sh mdmp/scripts/split-to-own-repo.sh git@github.com:dassey/mdmp.git
#
set -e

REMOTE="$1"
if [ -z "$REMOTE" ]; then
  echo "usage: $0 <git remote url>" >&2
  echo "example: $0 git@github.com:dassey/mdmp.git" >&2
  exit 1
fi

if [ ! -d mdmp ]; then
  echo "run this from the root of the repository that contains mdmp/" >&2
  exit 1
fi

BRANCH=mdmp-standalone
echo "==> splitting mdmp/ into branch $BRANCH (history preserved)"
git subtree split --prefix=mdmp -b "$BRANCH"

echo "==> pushing $BRANCH to $REMOTE as main"
git push "$REMOTE" "$BRANCH":main

echo ""
echo "Done. The project now lives at $REMOTE with its own history."
echo ""
echo "To work on it from a fresh clone:"
echo "    git clone $REMOTE"
echo "    cd mdmp && python3 serve.py"
echo ""
echo "The copy under mdmp/ in this repository is now redundant; remove it when"
echo "you are satisfied the new repository is good:"
echo "    git rm -r mdmp && git commit -m 'Move MDMP harness to its own repository'"
