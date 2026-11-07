#!/usr/bin/env bash
# deploy.sh — mirror a built static site to an FTP or SFTP host with lftp.
#
# Usage: deploy.sh [SOURCE_DIR] [options]
#
#   --protocol ftp|sftp       Override protocol auto-detection
#   --port PORT               SFTP port (default: 22)
#   --lftp-option 'COMMAND'   Extra lftp command, repeatable
#   --dry-run                 Print the resolved deployment and exit
#   -h, --help                Show this help
#
# Credentials come from the environment or from .env in the current directory:
#
#   DEPLOY_HOST DEPLOY_USER DEPLOY_PASS DEPLOY_PATH DEPLOY_PORT
#   FTP_HOST FTP_USER FTP_PASS FTP_PATH
#   SFTP_HOST SFTP_USER SFTP_PASS SFTP_PATH SFTP_PORT
#
# Other settings:
#
#   DEPLOY_SOURCE               Source directory (default: dist)
#   DEPLOY_PROTOCOL             ftp or sftp (default: auto-detect)
#   DEPLOY_LFTP_OPTIONS         Extra lftp commands, one per line
#   DEPLOY_SKIP_IF_UNCONFIGURED Skip when no credentials are set at all
#
# The password is passed to lftp through LFTP_PASSWORD, so it never appears in
# the process list, on disk, or in a workflow log.
set -euo pipefail

die() {
	printf 'error: %s\n' "$*" >&2
	exit 1
}

usage() {
	cat <<'EOF'
Mirror a built static site to an FTP or SFTP host with lftp.

Usage: deploy.sh [SOURCE_DIR] [options]

  --protocol ftp|sftp       Override protocol auto-detection
  --port PORT               SFTP port (default: 22)
  --lftp-option 'COMMAND'   Extra lftp command, repeatable
  --dry-run                 Print the resolved deployment and exit
  -h, --help                Show this help

Credentials come from the environment or from .env in the current directory:

  DEPLOY_HOST DEPLOY_USER DEPLOY_PASS DEPLOY_PATH DEPLOY_PORT
  FTP_HOST FTP_USER FTP_PASS FTP_PATH
  SFTP_HOST SFTP_USER SFTP_PASS SFTP_PATH SFTP_PORT

Other settings:

  DEPLOY_SOURCE               Source directory (default: dist)
  DEPLOY_PROTOCOL             ftp or sftp (default: auto-detect)
  DEPLOY_LFTP_OPTIONS         Extra lftp commands, one per line
  DEPLOY_SKIP_IF_UNCONFIGURED Skip when no credentials are set at all
EOF
}

# Quote a value for an lftp command, including backslashes, double quotes and
# dollar signs, so lftp never expands anything inside it.
lftp_quote() {
	local value=$1
	value=${value//\\/\\\\}
	value=${value//\"/\\\"}
	value=${value//\$/\\\$}
	printf '"%s"' "$value"
}

# Load .env before defaulting anything, so flags and environment variables can
# still override it.
if [ -f .env ]; then
	set -a
	# shellcheck disable=SC1091
	. ./.env
	set +a
fi

src=""
protocol="${DEPLOY_PROTOCOL:-}"
port="${DEPLOY_PORT:-}"
extra=()
dry_run=0
skip_unconfigured="${DEPLOY_SKIP_IF_UNCONFIGURED:-0}"

while [ $# -gt 0 ]; do
	case "$1" in
	--protocol)
		[ $# -ge 2 ] || die "--protocol needs a value"
		protocol=$2
		shift 2
		;;
	--port)
		[ $# -ge 2 ] || die "--port needs a value"
		port=$2
		shift 2
		;;
	--lftp-option)
		[ $# -ge 2 ] || die "--lftp-option needs a value"
		extra+=("$2")
		shift 2
		;;
	--dry-run)
		dry_run=1
		shift
		;;
	-h | --help)
		usage
		exit 0
		;;
	-*)
		die "unknown option: $1 (try --help)"
		;;
	*)
		[ -z "$src" ] || die "unexpected argument: $1"
		src=$1
		shift
		;;
	esac
done

if [ -n "${DEPLOY_LFTP_OPTIONS:-}" ]; then
	while IFS= read -r line; do
		if [ -n "$line" ]; then
			extra+=("$line")
		fi
	done <<<"$DEPLOY_LFTP_OPTIONS"
fi

case "$skip_unconfigured" in
1 | true | TRUE | yes | YES) skip_unconfigured=1 ;;
*) skip_unconfigured=0 ;;
esac

case "$protocol" in
"" | ftp | sftp) ;;
*) die "unknown protocol: $protocol (expected ftp or sftp)" ;;
esac

if [ -z "$protocol" ]; then
	if [ -n "${SFTP_HOST:-}" ] && [ -z "${FTP_HOST:-}" ]; then
		protocol=sftp
	elif [ -n "${FTP_HOST:-}" ]; then
		protocol=ftp
	elif [ -n "${SFTP_HOST:-}" ]; then
		protocol=sftp
	else
		protocol=ftp
	fi
fi

if [ -n "${DEPLOY_HOST:-}" ]; then
	host=$DEPLOY_HOST
	user=${DEPLOY_USER:-}
	pass=${DEPLOY_PASS:-}
	path=${DEPLOY_PATH:-}
else
	if [ "$protocol" = "sftp" ]; then
		host=${SFTP_HOST:-}
		user=${SFTP_USER:-}
		pass=${SFTP_PASS:-}
		path=${SFTP_PATH:-}
		[ -n "$port" ] || port=${SFTP_PORT:-}
	else
		host=${FTP_HOST:-}
		user=${FTP_USER:-}
		pass=${FTP_PASS:-}
		path=${FTP_PATH:-}
	fi
fi

src=${src:-${DEPLOY_SOURCE:-dist}}
src=${src%/}
[ -d "$src" ] || die "source directory not found: $src (run ./update.sh first)"

missing=""
[ -n "$host" ] || missing="$missing HOST"
[ -n "$user" ] || missing="$missing USER"
[ -n "$pass" ] || missing="$missing PASSWORD"
[ -n "$path" ] || missing="$missing PATH"

if [ -n "$missing" ]; then
	if [ "$skip_unconfigured" = "1" ] &&
		[ -z "$host" ] && [ -z "$user" ] && [ -z "$pass" ] && [ -z "$path" ]; then
		message="Deploy skipped: no credentials configured (host, user, password, path)."
		if [ -n "${GITHUB_ACTIONS:-}" ]; then
			echo "::warning::$message"
		else
			printf 'warning: %s\n' "$message" >&2
		fi
		exit 0
	fi
	die "missing credentials:$missing — set them in .env or as action inputs"
fi

remote_path=${path%/}
[ -n "$remote_path" ] || remote_path="/"

if [ "$protocol" = "sftp" ]; then
	port=${port:-22}
fi

if [ "$dry_run" = "0" ] && ! command -v lftp >/dev/null 2>&1; then
	die "lftp is required — install it with: brew install lftp (macOS) or apt-get install lftp"
fi

commands=""
append() {
	if [ -z "$commands" ]; then
		commands=$1
	else
		commands="$commands"$'\n'"$1"
	fi
}

if [ "$protocol" = "ftp" ]; then
	append "set ssl:verify-certificate no"
fi
if [ ${#extra[@]} -gt 0 ]; then
	for option in "${extra[@]}"; do
		append "$option"
	done
fi
if [ "$protocol" = "sftp" ]; then
	append "set sftp:connect-program \"ssh -a -x -o StrictHostKeyChecking=accept-new\""
	append "open --env-password -u $(lftp_quote "$user") $(lftp_quote "sftp://$host:$port")"
else
	append "open --env-password -u $(lftp_quote "$user") $(lftp_quote "$host")"
fi
append "mirror --reverse --delete --verbose --ignore-time --parallel=4 $(lftp_quote "$src/") $(lftp_quote "$remote_path/")"
# --ignore-time leaves size as the only comparison, so an edit that keeps the
# same byte length (for example a capitalisation fix) would be skipped. Force
# the small text assets up on every deploy; media stays size-compared.
append "mirror --reverse --verbose --ignore-time --ignore-size --parallel=4 --include-glob='*.html' --include-glob='*.css' --include-glob='*.js' --include-glob='*.json' --include-glob='*.webmanifest' --include-glob='*.xml' --include-glob='*.txt' --include-glob='*.svg' --include-glob='*.ico' --include-glob='.htaccess' $(lftp_quote "$src/") $(lftp_quote "$remote_path/")"

if [ "$dry_run" = "1" ]; then
	printf 'protocol: %s\n' "$protocol"
	printf 'source:   %s/\n' "$src"
	printf 'remote:   %s:%s/\n' "$host" "$remote_path"
	printf 'user:     %s\n' "$user"
	printf 'password: [set]\n'
	printf 'lftp commands:\n%s\n' "$commands"
	exit 0
fi

if [ "$protocol" = "sftp" ]; then
	# ssh needs the directory to exist before it can pin the host key.
	mkdir -p "$HOME/.ssh"
fi

# Normalise permissions so files aren't published as executable.
find "$src" -type f -exec chmod 644 {} +
find "$src" -type d -exec chmod 755 {} +

echo "Deploying $src/ to $host:$remote_path/ ..."
LFTP_PASSWORD="$pass" lftp -c "$commands"

echo "✓ Deployed"
