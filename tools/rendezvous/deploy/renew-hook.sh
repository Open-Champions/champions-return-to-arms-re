#!/bin/sh
# renew-hook.sh - certbot's deploy hook for the room service (docs/issues/native-rendezvous-tls.md).
# Installed on the server as /etc/letsencrypt/renewal-hooks/deploy/champions-net2 (mode 0755),
# with <server-host> replaced by the certificate's host name.  certbot runs every deploy hook
# after it has renewed a certificate and names the renewed one in RENEWED_LINEAGE.
#
# The service takes its certificate at start (LoadCredential=), so it is restarted. What that
# costs: every player's TCP link drops and comes back by itself within seconds; open rooms
# and the relay of games that run are lost (games on straight routes go on). About every
# 60 days, at a time certbot chooses.
case "${RENEWED_LINEAGE:-}" in
    */<server-host>) systemctl try-restart champions-net2.service ;;
esac
exit 0
