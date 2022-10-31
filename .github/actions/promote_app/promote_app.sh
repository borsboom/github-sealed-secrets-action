#!/usr/bin/env bash
#
# Promote the version of the app from one environment to another. See README.md
# for an overview of how to use this script.
#
# Usage:
#
#   scripts/promote_app APP FROMENV TOENV
#
# Arguments:
#
#   - APP: name of the app to sync
#   - FROMENV: name of the stage environment to promote _from_
#   - TOENV: name of the stage environment to promote _to_
#

set -eu -o pipefail
cd "$(dirname "$0")/.."

if [[ "$#" -ne 3 ]]; then
    echo "$0: Invalid arguments; see header of script for usage information." >&2
    exit 1
fi
APP=$1
FROMENV=$2
TOENV=$3

imagetag=$(grep ' *newTag:' "kubernetes/$APP/overlays/$FROMENV/kustomization.yaml" |head -1 |sed 's/ *newTag: //')
gitref=$(grep '?ref=' "kubernetes/$APP/overlays/$FROMENV/kustomization.yaml" |sed 's/.*\?ref=//')

(set -x
    sed -i.bak 's/^\( *newTag: \).*/\1'"$imagetag"'/' "kubernetes/$APP/overlays/$TOENV/kustomization.yaml"
    sed -i.bak 's/\(?ref=\).*/\1'"$gitref"'/' "kubernetes/$APP/overlays/$TOENV/kustomization.yaml"
)

if [[ "$(git status --porcelain)" != "" ]]; then
    (set -x
        git add "kubernetes/$APP/overlays/$TOENV/kustomization.yaml"
        git commit -m "$APP: promote $TOENV to $imagetag (from $FROMENV)"
    )
else
    echo "$(basename $0): no changes; nothing to commit."
fi
