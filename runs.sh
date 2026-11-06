#!/usr/bin/env bash
# runs.sh — print recent GitHub Actions workflow runs for several repositories.
#
# Configuration is read from the environment or from .runs.env in the current
# directory (or next to this script):
#
#   GH_OWNER=your-account
#   REPOS="example.com example.org"
#
# REPO entries may be bare repository names (combined with GH_OWNER) or full
# "owner/repo" slugs. Set RUNS_ENV to load a different config file.
set -euo pipefail

die() {
	printf 'error: %s\n' "$*" >&2
	exit 1
}

usage() {
	cat <<'EOF'
Print recent GitHub Actions runs for several repositories.

Usage: runs.sh [-n COUNT] [REPO...]

  -n, --limit COUNT   Runs per repository (default: 5)
  -h, --help          Show this help

Configuration is read from the environment or from .runs.env in the current
directory (or next to this script):

  GH_OWNER=your-account
  REPOS="example.com example.org"

REPO entries may be bare repository names or full owner/repo slugs. Set
RUNS_ENV to load a different config file.
EOF
}

config=${RUNS_ENV:-}
if [ -z "$config" ]; then
	if [ -f .runs.env ]; then
		config=.runs.env
	else
		script_dir=$(cd "$(dirname "$0")" && pwd)
		if [ -f "$script_dir/.runs.env" ]; then
			config="$script_dir/.runs.env"
		else
			config=.runs.env
		fi
	fi
fi

if [ -f "$config" ]; then
	set -a
	# shellcheck disable=SC1090
	. "$config"
	set +a
fi

limit=5
repos=()

while [ $# -gt 0 ]; do
	case "$1" in
	-n | --limit)
		[ $# -ge 2 ] || die "$1 needs a value"
		limit=$2
		shift 2
		;;
	-h | --help)
		usage
		exit 0
		;;
	-*)
		die "unknown option: $1 (try --help)"
		;;
	*)
		repos+=("$1")
		shift
		;;
	esac
done

if [ ${#repos[@]} -eq 0 ] && [ -n "${REPOS:-}" ]; then
	read -r -a repos <<<"$REPOS" || true
fi
[ ${#repos[@]} -gt 0 ] || die "no repositories configured (set REPOS in $config)"

case "$limit" in
'' | *[!0-9]*) die "--limit must be a positive number" ;;
0) die "--limit must be a positive number" ;;
esac

command -v gh >/dev/null 2>&1 || die "gh is required: https://cli.github.com"

status=0
for repo in "${repos[@]}"; do
	case "$repo" in
	*/*)
		slug=$repo
		;;
	*)
		[ -n "${GH_OWNER:-}" ] || die "set GH_OWNER for bare repository name: $repo"
		slug="$GH_OWNER/$repo"
		;;
	esac

	printf '\n%s\n%s\n' "$slug" "https://github.com/$slug/actions"
	if ! gh run list -R "$slug" -L "$limit" \
		--json status,conclusion,workflowName,headBranch,event,displayTitle,url \
		--template '{{range .}}{{if eq .status "completed"}}{{printf "%-11s" .conclusion}}{{else}}{{printf "%-11s" .status}}{{end}}  {{.workflowName}} · {{.headBranch}} · {{.event}} · {{.displayTitle}}
             {{.url}}
{{end}}'; then
		printf '  could not fetch runs for %s\n' "$slug" >&2
		status=1
	fi
done

exit "$status"
