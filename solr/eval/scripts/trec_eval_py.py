#!/usr/bin/env python3
"""Drop-in replacement for `trec_eval -q -m all_trec` (output format only), using pytrec_eval.

The tutorial uses the compiled trec_eval binary; this script prints the same
"<measure> <query_id> <value>" lines (including an aggregated "all" row) so that
plot_pr.py works unchanged. It also adds 11pt_avg, which plot_pr.py expects.

Usage: trec_eval_py.py qrels_trec.txt results_trec.txt
"""
import sys

import pytrec_eval

RECALL_LEVELS = [f"{r / 10:.2f}" for r in range(11)]
MEASURES = {"map", "P", "iprec_at_recall", "recip_rank", "Rprec"}


def read_qrels(path):
    qrels = {}
    for line in open(path, encoding="utf-8"):
        query, _, doc, relevance = line.split()
        qrels.setdefault(query, {})[doc] = int(relevance)
    return qrels


def read_run(path):
    run = {}
    for line in open(path, encoding="utf-8"):
        query, _, doc, _, score, _ = line.split()
        run.setdefault(query, {})[doc] = float(score)
    return run


def main(qrels_path, run_path):
    qrels, run = read_qrels(qrels_path), read_run(run_path)
    evaluator = pytrec_eval.RelevanceEvaluator(qrels, MEASURES)
    per_query = evaluator.evaluate({q: d for q, d in run.items() if q in qrels})

    for metrics in per_query.values():
        metrics["11pt_avg"] = sum(metrics[f"iprec_at_recall_{r}"] for r in RECALL_LEVELS) / 11

    names = sorted({name for metrics in per_query.values() for name in metrics})
    for query in sorted(per_query, key=int):
        for name in names:
            print(f"{name:<24}\t{query}\t{per_query[query][name]:.4f}")
    for name in names:
        mean = sum(m[name] for m in per_query.values()) / len(per_query)
        print(f"{name:<24}\tall\t{mean:.4f}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
