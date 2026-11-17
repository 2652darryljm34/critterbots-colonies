#!/bin/sh
# Dev only. Runs a ladder of the four main bots under several rule overrides. Usage: sh tools/tune_batch.sh SEEDS 'json1' 'json2' ...
SEEDS="$1"; shift
B="bots/forager.py bots/farmer.py bots/raider.py bots/warlord.py"
for t in '{}' "$@"; do
  echo "== $t"
  CRITTERBOTS_TUNE="$t" python ladder.py --seeds "$SEEDS" $B | tail -5
done
