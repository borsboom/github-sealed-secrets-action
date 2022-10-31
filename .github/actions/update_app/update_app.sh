#!/usr/bin/env bash
#
# Update the Docker image tag for an app. See README.md for an overview of how
# to use this script.
#
# Usage:
#
#   scripts/update_app APP ENV IMAGETAG [BASEREF]
#
# Required arguments:
#
#   - APP: name of the app to sync
#   - ENV: name of the stage environment (dev/test/staging/prod)
#   - IMAGETAG: new Docker image tag to update to
#
# Optional arguments
#
#   - BASEREF: new base kustomization Git ref (tag, branch, or commit ID) to
#     update to (if unspecified, do not change the base ref)
#

set -eux -o pipefail
#@@@ cd "$(dirname "$0")/.."

if [[ "$#" -lt 3 ]]; then
    echo "$0: Invalid arguments; see header of script for usage information." >&2
    exit 1
fi
APP=$1
ENV=$2
IMAGETAG=$3
BASEREF=${4:-}

kustomizationFile="kubernetes/$APP/overlays/$ENV/kustomization.yaml"

(set -x;
    sed 's/^\( *newTag: \).*/\1'"$IMAGETAG"'/' "$kustomizationFile" >"$kustomizationFile.NEW"
    mv "$kustomizationFile.NEW" "$kustomizationFile")

if [[ -n "$BASEREF" ]]; then
    (set -x;
        sed 's/\(\?ref=\).*/\1'"$BASEREF"'/' "$kustomizationFile" >"$kustomizationFile.NEW"
        mv "$kustomizationFile.NEW" "$kustomizationFile")
fi

if [[ "$(git status --porcelain -uno)" != "" ]]; then
    (set -x
        git add "$kustomizationFile"
        git commit -m "$APP: update $ENV to $IMAGETAG"
    )
else
    echo "$(basename $0): no changes; nothing to commit."
fi
