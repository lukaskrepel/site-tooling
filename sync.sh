#!/usr/bin/env bash
# sync.sh — refresh the vendored _shared/ copies from this repository.
#
# Configuration is read from the environment or from .sync.env in the current
# directory (or next to this script):
#
#   TOOLING_REPO=your-account/site-tooling
#   TOOLING_REF=main
#   SITE_DIRS="
#   /path/to/site-one
#   /path/to/site-two
#   "
set -euo pipefail

die() {
	printf 'error: %s\n' "$*" >&2
	exit 1
}

usage() {
	cat <<'EOF'
Refresh the vendored _shared/ copies in local checkouts.

Usage: sync.sh [-h]

Configuration is read from the environment or from .sync.env in the current
directory (or next to this script):

  TOOLING_REPO=your-account/site-tooling
  TOOLING_REF=main
  SITE_DIRS="
  /path/to/site-one
  /path/to/site-two
  "

The script runs git subtree pull in each checkout. It never pushes; review and
push the resulting commits when you are ready.
EOF
}

config=${SYNC_ENV:-}
if [ -z "$config" ]; then
	if [ -f .sync.env ]; then
		config=.sync.env
	else
		script_dir=$(cd "$(dirname "$0")" && pwd)
		if [ -f "$script_dir/.sync.env" ]; then
			config="$script_dir/.sync.env"
		else
			config=.sync.env
		fi
	fi
fi

if [ -f "$config" ]; then
	set -a
	# shellcheck disable=SC1090
	. "$config"
	set +a
fi

case "${1:-}" in
-h | --help)
	usage
	exit 0
	;;
"") ;;
*) die "unknown option: $1 (try --help)" ;;
esac

[ -n "${TOOLING_REPO:-}" ] || die "set TOOLING_REPO in $config"
[ -n "${SITE_DIRS:-}" ] || die "set SITE_DIRS in $config"
ref=${TOOLING_REF:-main}
url="https://github.com/$TOOLING_REPO.git"

status=0
while IFS= read -r dir; do
	[ -n "$dir" ] || continue
	if [ ! -d "$dir/_shared" ]; then
		printf 'skip %s (no _shared/)\n' "$dir" >&2
		continue
	fi
	if ! git -C "$dir" diff --quiet || ! git -C "$dir" diff --cached --quiet; then
		printf 'skip %s (working tree has changes)\n' "$dir" >&2
		status=1
		continue
	fi

	before=$(git -C "$dir" rev-parse HEAD)
	if ! GIT_EDITOR=true git -C "$dir" subtree pull \
		--prefix _shared "$url" "$ref" --squash; then
		printf 'error: could not update %s\n' "$dir" >&2
		status=1
		continue
	fi
	after=$(git -C "$dir" rev-parse HEAD)

	if [ "$before" = "$after" ]; then
		printf '%s: up to date\n' "$dir"
	elif git -C "$dir" diff --quiet "$before" "$after"; then
		git -C "$dir" reset --hard "$before" >/dev/null
		printf '%s: up to date\n' "$dir"
	else
		printf '%s: updated — review and push\n' "$dir"
	fi
done <<<"$SITE_DIRS"

exit "$status"
