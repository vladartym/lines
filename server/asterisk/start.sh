#!/bin/sh
# Starts Asterisk with the configs of this folder.
#
# pjsip.conf holds its passwords as ${...}. They come from the environment here, from .env, so no password is in
# git. Only these names are filled in: the dialplan has ${...} of its own.
set -eu
umask 027
# The addresses that VoIP.ms sends calls from. With no value, the address of VOIPMS_SERVER.
: "${VOIPMS_MATCH:=$VOIPMS_SERVER}"
export VOIPMS_MATCH
cp /conf/*.conf /etc/asterisk/
envsubst '${PHONE_SIP_PASSWORD} ${VOIPMS_SIP_USERNAME} ${VOIPMS_SIP_PASSWORD} ${VOIPMS_SERVER} ${VOIPMS_MATCH}' \
  < /conf/pjsip.conf > /etc/asterisk/pjsip.conf
# Asterisk runs as the user asterisk, and these files are new, so root owns them.
chown asterisk:asterisk /etc/asterisk/*.conf
exec /usr/local/bin/entrypoint.sh /usr/sbin/asterisk -f -n -T -vvv -U asterisk -G asterisk
