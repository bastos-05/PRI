#!/usr/bin/env python3
"""Drop-in replacement for `trec_eval -q -m all_trec` (output format only), using pytrec_eval.

The tutorial uses the compiled trec_eval binary; this script prints the same
"<measure> <query_id> <value>" lines (including an aggregated "all" row) so that
plot_pr.py works unchanged. It also adds 11pt_avg, which plot_pr.py expects.

Usage: trec_eval_py.py qrels_trec.txt results_trec.txt
"""
import sys

try:
    import pytrec_eval
except ImportError:
    pytrec_eval = None

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


def eval_py(qrels, run):
    per_query = {}
    for q, docs in run.items():
        if q not in qrels:
            continue
        rels = qrels[q]
        n_rel = sum(1 for r in rels.values() if r > 0)
        ranked = [d for d, _ in sorted(docs.items(), key=lambda x: (-x[1], x[0]))]
        hits, ap, rr, pts = 0, 0.0, 0.0, []
        for i, d in enumerate(ranked, 1):
            if rels.get(d, 0) > 0:
                hits += 1
                ap += hits / i
                rr = rr or 1.0 / i
                if n_rel:
                    pts.append((hits / n_rel, hits / i))
        m = {"map": ap / n_rel if n_rel else 0.0, "recip_rank": rr}
        for k in (5, 10, 20):
            m[f"P_{k}"] = sum(1 for d in ranked[:k] if rels.get(d, 0) > 0) / k
        for r in RECALL_LEVELS:
            m[f"iprec_at_recall_{r}"] = max((p for rec, p in pts if rec >= float(r) - 1e-12), default=0.0)
        per_query[q] = m
    return per_query


def main(qrels_path, run_path):
    qrels, run = read_qrels(qrels_path), read_run(run_path)
    if pytrec_eval:
        per_query = pytrec_eval.RelevanceEvaluator(qrels, MEASURES).evaluate({q: d for q, d in run.items() if q in qrels})
    else:
        per_query = eval_py(qrels, run)

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
