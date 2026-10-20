#!/bin/sh
# play.sh - start the native build of Champions: Return to Arms (Linux).
#   ./play.sh "/path/to/your image.iso" [more options of rta_app, see ./rta_app --help]
# The output goes to the terminal and to rta-data/rta_app-log.txt beside this file (send that with a report).
cd "$(dirname "$0")" || exit 1
if [ -z "$1" ]; then
  echo "Give your own disc image of Champions: Return to Arms (SLUS-20973 v2.00):  ./play.sh \"/path/to/image.iso\""
  exit 1
fi
mkdir -p rta-data
./rta_app --disc "$@" 2>&1 | tee rta-data/rta_app-log.txt
