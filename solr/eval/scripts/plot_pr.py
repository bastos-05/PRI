#!/usr/bin/env python3

import sys

import matplotlib.pyplot as plt
import numpy as np


def main(trec_eval_stdout: str):

    # preprocessing - obtain results for each query
    results = {x: {} for x in set([x.split()[1] for x in trec_eval_stdout])}

    for metric in trec_eval_stdout:
        (name, query_id, value) = metric.split()
        results[query_id][name] = value

    del results["all"]  # discard aggregated results

    for query_id, metrics in results.items():

        # Obtain interpolated precision and recall
        recall = np.arange(0, 1.1, 0.1)

        pr_keys = [f"iprec_at_recall_{k:.2f}" for k in recall]
        iprecision = np.array([float(metrics[k]) for k in pr_keys])

        # Obtain Average Precision (AP)
        ap_score = float(metrics["map"])
        p_10 = float(metrics["P_10"])

        # Obtain the Area Under Curve (AUC) estimate
        auc_score = float(metrics["11pt_avg"])

        line_kwargs = {
            "drawstyle": "steps-post",
            "label": f"Q{query_id}: AP={ap_score:.3f}, AUC={auc_score:.3f}, P@10={p_10:.3f}",
            "linewidth": 2,
            "markersize": 10,
        }

        # Plot the 11-point interpolated precision-recall curve
        plt.plot(recall, iprecision, **line_kwargs)

    # Keep the title as "Precision-Recall Curve"
    plt.title("Precision-Recall Curve")

    # Customize plot appearance
    axis_kwargs = {
        "fontsize": 9,
        "verticalalignment": "baseline",
        "style": "italic",
    }

    plt.xlabel("Recall", fontdict=axis_kwargs)
    plt.ylabel("Precision", fontdict=axis_kwargs)
    plt.xlim(-0.005, 1.005)
    plt.ylim(-0.005, 1.005)
    plt.legend(loc="lower left", prop={"size": 10}, )
    plt.grid(True)
    plt.grid(linestyle='--', linewidth=0.5)
    plt.tight_layout()

    # Show the PR curve
    plt.show()


if __name__ == "__main__":
    # Run the main function with trec_eval's output
    trec_eval_stdout = sys.stdin.readlines()

    main(trec_eval_stdout)
