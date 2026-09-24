<#
.SYNOPSIS
    Start the Relay full-stack demo locally with Docker Compose (Windows)

.DESCRIPTION
    Brings up all services (Postgres + Ollama + Gateway + Sync-Server + Studio)
    with docker-compose, prints the URLs, and waits for services to be ready.

    The demo uses the Echo provider for instant responses (no API key needed).

.EXAMPLE
    .\scripts\demo.ps1
    .\scripts\demo.ps1 -Logs
    .\scripts\demo.ps1 -Down
    .\scripts\demo.ps1 -Clean

.PARAMETER Logs
    Follow live logs from all services instead of starting

.PARAMETER Down
    Stop all services (keep data)

.PARAMETER Clean
    Stop and remove all services and volumes (fresh start next time)

.PARAMETER Status
    Show the status of all running services
#>

param(
    [switch]$Logs,
    [switch]$Down,
    [switch]$Clean,
    [switch]$Status
)

$ErrorActionPreference = "Stop"

function Write-Header {
    param([string]$Message)
    Write-Host ""
    Write-Host "🚀 $Message" -ForegroundColor Cyan
    Write-Host ""
}

function Write-Success {
    param([string]$Message)
    Write-Host "✅ $Message" -ForegroundColor Green
}

function Write-Info {
    param([string]$Message)
    Write-Host "   $Message" -ForegroundColor Gray
}

# Check if docker and docker-compose are available
function Test-DockerInstalled {
    try {
        $null = docker --version
        $null = docker-compose --version
        return $true
    } catch {
        Write-Host "❌ Docker and Docker Compose are required." -ForegroundColor Red
        Write-Host "   Install from: https://www.docker.com/products/docker-desktop" -ForegroundColor Red
        exit 1
    }
}

if ($Logs) {
    Write-Header "Following logs..."
    docker-compose logs -f
} elseif ($Down) {
    Write-Header "Stopping services..."
    docker-compose down
    Write-Success "Stopped (data preserved)"
} elseif ($Clean) {
    Write-Header "Cleaning up..."
    docker-compose down -v
    Write-Success "Cleaned (volumes removed)"
} elseif ($Status) {
    Write-Header "Service status:"
    docker-compose ps
} else {
    # Start the demo
    Test-DockerInstalled

    Write-Header "Starting Relay demo stack..."
    Write-Info "Studio:       http://localhost:3000"
    Write-Info "Gateway:      http://localhost:8000"
    Write-Info "Sync-server:  ws://localhost:3001"
    Write-Info ""
    Write-Info "Demo API key: demo-key-12345"
    Write-Info "Database:     postgresql://relay:relay@localhost:5432/relay"
    Write-Info ""
    Write-Info "Use 'Ctrl+C' to stop, or run: .\scripts\demo.ps1 -Down"

    docker-compose up -d

    Write-Host ""
    Write-Info "Waiting for services to be ready (this takes ~10 seconds)..."
    Start-Sleep -Seconds 10

    # Try to reach the gateway health endpoint
    $maxRetries = 5
    $retry = 0
    while ($retry -lt $maxRetries) {
        try {
            $response = Invoke-RestMethod -Uri "http://localhost:8000/health" -ErrorAction Stop
            Write-Success "Gateway is ready!"
            break
        } catch {
            $retry++
            if ($retry -lt $maxRetries) {
                Write-Info "Waiting... (attempt $retry/$maxRetries)"
                Start-Sleep -Seconds 2
            } else {
                Write-Info "Gateway not yet responding, but services are starting..."
            }
        }
    }

    Write-Host ""
    Write-Success "Stack is up! 🎉"
    Write-Host ""
    Write-Info "Next steps:"
    Write-Info "1. Open http://localhost:3000 in your browser"
    Write-Info "2. Create a prompt in /editor"
    Write-Info "3. Create a flag in /flags"
    Write-Info "4. Test in /playground"
    Write-Host ""
    Write-Info "Commands:"
    Write-Info "  .\scripts\demo.ps1 -Logs     → Follow live logs"
    Write-Info "  .\scripts\demo.ps1 -Down     → Stop services (keep data)"
    Write-Info "  .\scripts\demo.ps1 -Clean    → Stop and remove everything"
    Write-Info "  .\scripts\demo.ps1 -Status   → Show service status"
    Write-Host ""
}
