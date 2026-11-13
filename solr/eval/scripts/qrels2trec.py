#!/usr/bin/env python3

from argparse import ArgumentParser
from pathlib import Path
import glob


def qrels_to_trec(qrels: Path) -> None:
    """
    Converts qrels (query relevance judgments) to TREC evaluation format.

    Arguments:
    - qrels: A list of qrel lines (document IDs) from standard input.
    """

    for qrel_file in glob.glob(qrels.joinpath("*.txt").as_posix()):

        qrels = open(qrel_file).readlines()

        # filename contains query number
        filename = Path(qrel_file).stem

        for line in qrels:
            doc_id = line.strip()
            print(f"{int(filename)} 0 {doc_id} 1")


if __name__ == "__main__":
    """
    Read qrels from file and output them in TREC format.
    """
    parser = ArgumentParser(description="Convert QRELs to TREC format")

    parser.add_argument(
        "--qrels",
        type=Path,
        default="config/qrels/",
        help="Path to QREL data.",
    )

    args = parser.parse_args()

    qrels_to_trec(args.qrels)

