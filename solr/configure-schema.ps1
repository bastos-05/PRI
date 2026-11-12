$ErrorActionPreference = "Stop"

$schemaUrl = "http://127.0.0.1:8983/solr/pri/schema"
$schema = Invoke-RestMethod -Uri "$schemaUrl/fields?wt=json" -TimeoutSec 10
$existingFields = @($schema.fields | ForEach-Object { $_.name })

$fieldDefinitions = @(
    @{ name = "page_id"; type = "plong"; stored = $true; indexed = $true },
    @{ name = "revision_id"; type = "plong"; stored = $true; indexed = $false },
    @{ name = "title"; type = "text_general"; stored = $true; indexed = $true },
    @{ name = "text"; type = "text_general"; stored = $true; indexed = $true }
)

foreach ($field in $fieldDefinitions) {
    if ($existingFields -contains $field.name) {
        Write-Output "Field already configured: $($field.name)"
        continue
    }

    $payload = @{ "add-field" = $field } | ConvertTo-Json -Depth 4 -Compress
    $null = Invoke-RestMethod `
        -Uri $schemaUrl `
        -Method Post `
        -ContentType "application/json" `
        -Body $payload `
        -TimeoutSec 10

    Write-Output "Configured field: $($field.name)"
}
