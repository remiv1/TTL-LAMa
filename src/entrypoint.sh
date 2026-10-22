#!/bin/sh
set -eu

exec gunicorn --config python:gunicorn_conf main:app