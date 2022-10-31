#!/usr/bin/env bash
#
# Sync an app using ArgoCD. See README.md for an overview of how to use this
# script.
#
# Usage:
#
#   scripts/sync-app APP [ENV ..]
#
# Arguments:
#
#   - APP: Name of the app to sync.
#   - ENV: Name of the stage environment (dev/test/staging/prod).
#          Multiple environments may be specified.
#
# Required environment variables:
#
#   - ARGOCD_SERVER: hostname of the ArgoCD server
#   - ARGOCD_AUTH_TOKEN: ArgoCD authorization token with permission to sync the
#     app
#
# Optional environment variables:
#
#   - ARGOCD_CLI_BIN: Path to ArgoCD CLI binary (default is to download the
#     binary)
#   - ARGOCD_CLI_URL: URL to download ArgoCD CLI from (default is the from the
#     ArgoCD server).
#   - ARGOCD_OPTS: Default options for ArgoCD CLI.
#
set -eu -o pipefail
cd "$(dirname "$0")/.."
ARGOCD_CLI_BIN="${ARGOCD_CLI_BIN:-./argocd}"
ARGOCD_CLI_URL="${ARGOCD_CLI_URL:-https://${ARGOCD_SERVER#grpc-}/download/argocd-linux-amd64}"
APP_PREFIX="$(basename "$PWD")"; APP_PREFIX="${APP_PREFIX%-env}"

if [[ "$#" -lt 2 ]]; then
    echo "$0: Invalid arguments; see header of script for usage information." >&2
    exit 1
fi
APP=$1; shift

if [[ ! -f "${ARGOCD_CLI_BIN}" ]]; then
    (set -x
        curl -sSL --fail -o "${ARGOCD_CLI_BIN}" ${ARGOCD_CLI_URL}
        chmod a+x "${ARGOCD_CLI_BIN}"
    )
fi

declare -a apps=()
for env in "$@"; do
    apps+=("${APP_PREFIX}-${APP}-${env}")
done

for app in "${apps[@]}"; do
    (set -x
        "${ARGOCD_CLI_BIN}" app get --hard-refresh "${app}"
    )
done

(set -x
    "${ARGOCD_CLI_BIN}" app sync --timeout 300 --prune "${apps[@]}"
    "${ARGOCD_CLI_BIN}" app wait --timeout 300 "${apps[@]}"
)
