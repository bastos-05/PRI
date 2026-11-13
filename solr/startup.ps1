# Starts Solr 10, applies the schema and loads the collection (like the tutorial's startup.sh).
# Run from the repository root:  powershell -File solr\startup.ps1
$ErrorActionPreference = "Stop"

docker compose -p pri-solr -f solr-compose.yaml up -d

Write-Output "Waiting for the 'pri' core..."
for ($i = 0; $i -lt 40; $i++) {
    try {
        Invoke-RestMethod "http://127.0.0.1:8983/solr/pri/select?q=*:*&rows=0" -TimeoutSec 5 | Out-Null
        break
    } catch {
        Start-Sleep -Seconds 5
    }
}

python solr\setup_schema.py
python solr\load_documents.py data\final.jsonl --clear
