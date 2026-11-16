import json
import sys
import requests
from pathlib import Path

CORE = "http://localhost:8983/solr/pri"
schema = json.loads((Path(__file__).parent / "schema.json").read_text(encoding="utf-8"))


def call(path, body=None):
    if body is None:
        response = requests.get(CORE + path, timeout=60)
    else:
        response = requests.post(CORE + path, json=body, timeout=60)

    response.raise_for_status()
    return response.json()


existing_fields = {f["name"] for f in call("/schema/fields")["fields"]}
existing_types = {t["name"] for t in call("/schema/fieldtypes")["fieldTypes"]}
existing_copies = {(c["source"], c["dest"]) for c in call("/schema/copyfields")["copyFields"]}

commands = {}
types = [t for t in schema["add-field-type"] if t["name"] not in existing_types]

replaced_types = [t for t in schema["add-field-type"] if t["name"] in existing_types]
fields = [f for f in schema["add-field"] if f["name"] not in existing_fields]
copies = [c for c in schema["add-copy-field"] if (c["source"], c["dest"]) not in existing_copies]
if types:
    commands["add-field-type"] = types
if replaced_types:
    commands["replace-field-type"] = replaced_types
if fields:
    commands["add-field"] = fields
if copies:
    commands["add-copy-field"] = copies

if not commands:
    print("Schema already up to date")
    sys.exit(0)
try:
    call("/schema", commands)
except requests.HTTPError as error:
    print(error.response.text)
    raise
print("Applied:", {k: [x.get("name") or x.get("source") for x in v] for k, v in commands.items()})
