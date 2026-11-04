#!/bin/sh
set -eu

mounted_secret=/run/secrets/flask_secret_key
persistent_secret=/data/flask_secret_key

if [ ! -e "$mounted_secret" ] && [ ! -L "$mounted_secret" ]; then
	if [ ! -e "$persistent_secret" ]; then
		if ! (umask 077; set -C; python -c 'import secrets; print(secrets.token_urlsafe(48))' > "$persistent_secret"); then
			if [ ! -e "$persistent_secret" ]; then
				exit 1
			fi
		fi
	fi
	export TTL_LAMA_SECRET_KEY_FILE="$persistent_secret"
fi

exec gunicorn --config python:gunicorn_conf main:app