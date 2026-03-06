param(
    [string]$Python = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

if (-not $Python) {
    $Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
}

if (-not (Test-Path $Python)) {
    throw "Python executable not found at $Python. Activate/create .venv first, or pass -Python <path-to-python.exe>."
}

& $Python -m pip install --upgrade pyinstaller
if ($LASTEXITCODE -ne 0) { throw "Failed to install/upgrade pyinstaller." }
& $Python -m pip install --upgrade pillow
if ($LASTEXITCODE -ne 0) { throw "Failed to install/upgrade pillow." }

& $Python -m PyInstaller `
    --noconfirm `
    --clean `
    --windowed `
    --name VNC-Station-Controller `
    --icon (Join-Path $RepoRoot "app\images\icon.png") `
    --add-data ((Join-Path $RepoRoot "app\images") + ";app\images") `
    --add-data ((Join-Path $RepoRoot "app\sounds") + ";app\sounds") `
    --add-data ((Join-Path $RepoRoot "default.json") + ";.") `
    (Join-Path $RepoRoot "app\main.py")
if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed." }

$DistRoot = Join-Path $RepoRoot "dist\VNC-Station-Controller"

if (-not (Test-Path $DistRoot)) {
    throw "Expected dist folder not found: $DistRoot"
}

# Ensure runtime folders exist in distribution.
New-Item -ItemType Directory -Force -Path (Join-Path $DistRoot "vnc-view") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $DistRoot "vnc-control") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $DistRoot "vnc-positions") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $DistRoot "vnc-setups") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $DistRoot "logs") | Out-Null

# Copy required runtime files next to the launcher executable.
$ViewerSrc = Join-Path $RepoRoot "tvnviewer.exe"
if (Test-Path $ViewerSrc) {
    Copy-Item -Force -Path $ViewerSrc -Destination (Join-Path $DistRoot "tvnviewer.exe")
}
else {
    Write-Warning "tvnviewer.exe not found in repo root; copy it manually to dist."
}

$DefaultSrc = Join-Path $RepoRoot "default.json"
if (Test-Path $DefaultSrc) {
    Copy-Item -Force -Path $DefaultSrc -Destination (Join-Path $DistRoot "default.json")
}
else {
    Write-Warning "default.json not found in repo root; copy it manually to dist."
}

# Copy available position presets to distribution (optional runtime content).
$PositionsSrc = Join-Path $RepoRoot "vnc-positions"
$PositionsDst = Join-Path $DistRoot "vnc-positions"
if (Test-Path $PositionsSrc) {
    Get-ChildItem -Path $PositionsSrc -Filter "*.json" -File -ErrorAction SilentlyContinue | ForEach-Object {
        Copy-Item -Force -Path $_.FullName -Destination (Join-Path $PositionsDst $_.Name)
    }
}
else {
    Write-Warning "vnc-positions folder not found in repo root; empty folder created in dist."
}

# Copy available setup presets to distribution (optional runtime content).
$SetupsSrc = Join-Path $RepoRoot "vnc-setups"
$SetupsDst = Join-Path $DistRoot "vnc-setups"
if (Test-Path $SetupsSrc) {
    Get-ChildItem -Path $SetupsSrc -Filter "*.json" -File -ErrorAction SilentlyContinue | ForEach-Object {
        Copy-Item -Force -Path $_.FullName -Destination (Join-Path $SetupsDst $_.Name)
    }
}
else {
    Write-Warning "vnc-setups folder not found in repo root; empty folder created in dist."
}

# Copy available view/control files to distribution (optional runtime content).
$ViewSrc = Join-Path $RepoRoot "vnc-view"
$ViewDst = Join-Path $DistRoot "vnc-view"
if (Test-Path $ViewSrc) {
    Get-ChildItem -Path $ViewSrc -File -ErrorAction SilentlyContinue | Where-Object {
        $_.Extension -in @(".json", ".vnc")
    } | ForEach-Object {
        Copy-Item -Force -Path $_.FullName -Destination (Join-Path $ViewDst $_.Name)
    }
}
else {
    Write-Warning "vnc-view folder not found in repo root; empty folder created in dist."
}

$ControlSrc = Join-Path $RepoRoot "vnc-control"
$ControlDst = Join-Path $DistRoot "vnc-control"
if (Test-Path $ControlSrc) {
    Get-ChildItem -Path $ControlSrc -File -ErrorAction SilentlyContinue | Where-Object {
        $_.Extension -in @(".json", ".vnc")
    } | ForEach-Object {
        Copy-Item -Force -Path $_.FullName -Destination (Join-Path $ControlDst $_.Name)
    }
}
else {
    Write-Warning "vnc-control folder not found in repo root; empty folder created in dist."
}

Write-Host ("Build complete. See " + $DistRoot) -ForegroundColor Green
