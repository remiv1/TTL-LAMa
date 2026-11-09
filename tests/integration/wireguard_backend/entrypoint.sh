#!/bin/sh
set -eu

mkdir -p /run/sshd /run/ttl-lama-test
chmod 0777 /run/ttl-lama-test
ssh-keygen -A
interface=${TTL_LAMA_TEST_WIREGUARD_INTERFACE:-ttlama-test0}
ip link add "$interface" type wireguard
ip link set "$interface" up

exec /usr/sbin/sshd -D -e -f /etc/ssh/sshd_config