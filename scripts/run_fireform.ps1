param(
    [switch]$Build,
    [switch]$PullModel,
    [switch]$SmokeTest,
    [int]$Port = 8000
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Push-Location $repoRoot

try {
    Write-Host "==> Starting FireForm automation from $repoRoot" -ForegroundColor Cyan

    if ($Build) {
        Write-Host "==> Building Docker images" -ForegroundColor Yellow
        docker compose build
    }

    Write-Host "==> Ensuring containers are up" -ForegroundColor Yellow
    docker compose up -d

    Write-Host "==> Initializing database" -ForegroundColor Yellow
    docker compose exec app python3 -m api.db.init_db

    $shouldPull = $PullModel
    if (-not $shouldPull) {
        Write-Host "==> Checking if mistral model is already available" -ForegroundColor Yellow
        $modelList = docker compose exec ollama ollama list | Out-String
        if ($modelList -notmatch "(?im)^mistral") {
            $shouldPull = $true
        }
    }

    if ($shouldPull) {
        Write-Host "==> Pulling mistral model (this may take several minutes on first run)" -ForegroundColor Yellow
        docker compose exec ollama ollama pull mistral
    }

    Write-Host "==> Starting FastAPI server inside app container (background)" -ForegroundColor Yellow
    $startApiCmd = "pkill -f 'uvicorn api.main:app' >/dev/null 2>&1 || true; python3 -m uvicorn api.main:app --host 0.0.0.0 --port $Port > /tmp/fireform-api.log 2>&1"
    docker compose exec -d app sh -lc $startApiCmd

    Write-Host "==> Waiting for API to become ready on port $Port" -ForegroundColor Yellow
    $apiDocsUrl = "http://localhost:$Port/docs"
    $isReady = $false
    for ($i = 1; $i -le 30; $i++) {
        try {
            $response = Invoke-WebRequest -Uri $apiDocsUrl -Method Get -UseBasicParsing -TimeoutSec 5
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 400) {
                $isReady = $true
                break
            }
        }
        catch {
            # Retry until timeout while the service is booting.
        }
        Start-Sleep -Seconds 2
    }

    if (-not $isReady) {
        throw "API did not become ready. Check logs with: docker compose exec app sh -lc 'tail -n 200 /tmp/fireform-api.log'"
    }

    if ($SmokeTest) {
        Write-Host "==> Running automated API smoke test" -ForegroundColor Yellow
        $smokeTestScript = @'
import json
import requests

base = "http://localhost:8000"

template_payload = {
    "name": "Auto Test Template",
    "pdf_path": "./src/inputs/file.pdf",
    "fields": {
        "textbox_0_0": "",
        "textbox_0_1": "",
        "textbox_0_2": "",
        "textbox_0_3": "",
        "textbox_0_4": "",
        "textbox_0_5": "",
        "textbox_0_6": ""
    }
}

fill_payload = {
    "template_id": 0,
    "input_text": "Hi. The employee name is John Doe. Job title is managing director. Department supervisor is Jane Doe. Phone is 123456. Email is jdoe@ucsc.edu. Signature is John Doe. Date is 01/02/2005."
}

r = requests.post(f"{base}/templates/create", json=template_payload, timeout=900)
r.raise_for_status()
created = r.json()
fill_payload["template_id"] = created["id"]

r = requests.post(f"{base}/forms/fill", json=fill_payload, timeout=900)
r.raise_for_status()
filled = r.json()

print(json.dumps({
    "template": created,
    "filled": filled
}, indent=2))
'@

        $tmpSmokeFile = Join-Path $env:TEMP "fireform_smoke_test.py"
        Set-Content -Path $tmpSmokeFile -Value $smokeTestScript -Encoding UTF8
        docker compose cp $tmpSmokeFile app:/tmp/fireform_smoke_test.py
        docker compose exec app python3 /tmp/fireform_smoke_test.py
        if ($LASTEXITCODE -ne 0) {
            throw "Smoke test failed. Inspect API logs with: docker compose exec app sh -lc 'tail -n 200 /tmp/fireform-api.log'"
        }
        Remove-Item -Path $tmpSmokeFile -Force -ErrorAction SilentlyContinue
    }

    Write-Host "" 
    Write-Host "FireForm is ready." -ForegroundColor Green
    Write-Host "Swagger UI: $apiDocsUrl" -ForegroundColor Green
    Write-Host "API logs: docker compose exec app sh -lc 'tail -n 200 /tmp/fireform-api.log'" -ForegroundColor Green
    Write-Host "Stop everything: docker compose down" -ForegroundColor Green
}
finally {
    Pop-Location
}
