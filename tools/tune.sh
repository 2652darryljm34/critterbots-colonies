#!/bin/sh
# usage: tools/tune.sh '{"STUN": {"snatch": 1, "bonk": 3, "shove": 1}}' [ladder args]   (dev only)
T="$1"; shift
CRITTERBOTS_TUNE="$T" python ladder.py "$@"
