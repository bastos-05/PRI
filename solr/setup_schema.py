"""Apply solr/schema.json to the 'pri' core (safe to re-run)."""
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

CORE = "http://127.0.0.1:8983/solr/pri"
schema = json.loads((Path(__file__).parent / "schema.json").read_text(encoding="utf-8"))


def call(path, body=None):
    request = urllib.request.Request(
        CORE + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


existing_fields = {f["name"] for f in call("/schema/fields")["fields"]}
existing_types = {t["name"] for t in call("/schema/fieldtypes")["fieldTypes"]}
existing_copies = {(c["source"], c["dest"]) for c in call("/schema/copyfields")["copyFields"]}

commands = {}
types = [t for t in schema["add-field-type"] if t["name"] not in existing_types]
# Field types that already exist are replaced, so edits to analyzers are applied.
# (Changing a type requires re-indexing the documents afterwards.)
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
except urllib.error.HTTPError as error:
    print(error.read().decode())
    raise
print("Applied:", {k: [x.get("name") or x.get("source") for x in v] for k, v in commands.items()})
