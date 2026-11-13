#!/usr/bin/env python3

import argparse
import json
import sys
from pathlib import Path
import glob

import requests


def fetch_solr_results(query_file, solr_uri, collection):
    """
    Fetch search results from a Solr instance based on the query parameters.

    Arguments:
    - query_file: Path to the JSON file containing Solr query parameters.
    - solr_uri: URI of the Solr instance (e.g., http://localhost:8983/solr).
    - collection: Solr collection name from which results will be fetched.

    Output:
    - Prints the JSON search results to STDOUT.
    """

    # Load the query parameters from the JSON file
    try:
        query_params = json.load(open(query_file))
    except FileNotFoundError:
        print(f"Error: Query file {query_file} not found.")
        sys.exit(1)

    # Construct the Solr request URL
    uri = f"{solr_uri}/{collection}/select"

    try:
        # Send the POST request to Solr
        response = requests.post(uri, json=query_params)
        response.raise_for_status()  # Raise error if the request failed
    except requests.RequestException as e:
        print(f"Error querying Solr: {e}")
        sys.exit(1)

    # Fetch and print the results as JSON
    return response.json()


def main(query_folder: Path, solr_uri, collection):

    results = {}

    for query_file in glob.glob(query_folder.joinpath("*.json").as_posix()):
        # filename contains query number
        filename = Path(query_file).stem

        results[int(filename)] = fetch_solr_results(
            query_file, solr_uri, collection
        )

    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    # Set up argument parsing for the command-line interface
    parser = argparse.ArgumentParser(
        description="Fetch search results from Solr and output them in JSON format."
    )

    # Add arguments for query file, Solr URI, and collection name
    parser.add_argument(
        "--queries",
        type=Path,
        required=True,
        help="Path to the directory containing JSON files with Solr query parameters",
    )
    parser.add_argument(
        "--uri",
        type=str,
        default="http://localhost:8983/solr",
        help="The URI of the Solr instance (default: http://localhost:8983/solr).",
    )
    parser.add_argument(
        "--collection",
        type=str,
        default="pri",
        help="Name of the Solr collection to query (default: 'pri').",
    )

    # Parse command-line arguments
    args = parser.parse_args()

    # Call the function with parsed arguments
    main(args.queries, args.uri, args.collection)
