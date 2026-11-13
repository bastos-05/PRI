#!/usr/bin/env bash
set -euo pipefail

# evaluate.sh - runs the end-to-end evaluation pipeline (adapted from the PRI tutorial 06).
# Run it from solr/eval (it uses relative paths like ./scripts/...).
#
# Usage: ./evaluate.sh <queries_dir> <qrels_dir> [collection] [--plot]
#   e.g. ./evaluate.sh config/queries_a config/qrels
#        ./evaluate.sh config/queries_b config/qrels pri --plot
#
# Differences from the tutorial: trec_eval_py.py (pytrec_eval) replaces the compiled
# trec_eval binary, and the plot is only shown with --plot.
if [[ $# -lt 2 ]]; then
  echo "Usage: $0 <queries_dir> <qrels_dir> [collection] [--plot]" >&2
  exit 1
fi

QUERIES="$1"; QRELS="$2"; COLLECTION="${3:-pri}"
PLOT="${4:-}"

if ! compgen -G "$QRELS/*.txt" > /dev/null; then
  echo "No qrels found in $QRELS (expected 0001.txt ... 0004.txt, one document id per line)." >&2
  exit 1
fi

# convert qrels to TREC format
python scripts/qrels2trec.py --qrels "$QRELS" > qrels_trec.txt

# query Solr and convert results to TREC format
python scripts/query_solr.py --queries "$QUERIES" --collection "$COLLECTION" \
  | python scripts/solr2trec.py --run-id "$(basename "$QUERIES")" > results_trec.txt

# evaluate
python scripts/trec_eval_py.py qrels_trec.txt results_trec.txt > eval_output.txt
echo "== $(basename "$QUERIES"): per-query and mean (all) =="
awk -F'\t' '$1 ~ /^(map|P_5|P_10|recip_rank|11pt_avg) *$/ { printf "%-12s query %-4s %s\n", $1, $2, $3 }' eval_output.txt | sort -k1,1 -k3,3

if [[ "$PLOT" == "--plot" ]]; then
  python scripts/plot_pr.py < eval_output.txt
fi

# cleanup
rm -f qrels_trec.txt results_trec.txt eval_output.txt
