<#
.SYNOPSIS
    Windows equivalent of `make demo`: runs the full Relay stack locally with Docker.

.EXAMPLE
    .\scripts\demo.ps1            # Echo provider, no API keys
    .\scripts\demo.ps1 -Ollama    # real local model via Ollama (first run downloads ~1.3 GB)
    .\scripts\demo.ps1 -Down      # stop, keep data
    .\scripts\demo.ps1 -Reset     # stop and wipe data
#>
param(
    [switch]$Ollama,
    [switch]$Down,
    [switch]$Reset,
    [string]$OllamaModel = "llama3.2:1b"
)

$ErrorActionPreference = "Stop"
$compose = Join-Path $PSScriptRoot "..\infra\demo\compose.yml"

function Invoke-Compose {
    & docker compose -f $compose @args
    if ($LASTEXITCODE -ne 0) { throw "docker compose $args failed (exit $LASTEXITCODE)" }
}

if ($Down) { Invoke-Compose --profile ollama down; return }
if ($Reset) { Invoke-Compose --profile ollama down -v; return }

if ($Ollama) {
    $env:DEMO_PROVIDER = "ollama"
    $env:DEMO_MODEL = $OllamaModel
    try {
        Invoke-Compose --profile ollama up -d --build --wait
        Invoke-Compose exec ollama ollama pull $OllamaModel
    } finally {
        Remove-Item Env:DEMO_PROVIDER, Env:DEMO_MODEL -ErrorAction SilentlyContinue
    }
} else {
    Invoke-Compose up -d --build --wait
}

Write-Host ""
Write-Host "Relay demo is up."
Write-Host "  Studio       http://localhost:3000   (start at /playground)"
Write-Host "  Gateway      http://localhost:8000   (API key: demo-key)"
Write-Host "  Sync server  ws://localhost:1234"
Write-Host "Stop with '.\scripts\demo.ps1 -Down'; wipe data with '.\scripts\demo.ps1 -Reset'."
