param(
    [string]$Python = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$VersionFile = Join-Path $RepoRoot "app\constants.py"
$VersionMatch = Select-String -Path $VersionFile -Pattern 'APP_VERSION\s*=\s*"([^"]+)"'

if (-not $VersionMatch) {
    throw "Could not determine APP_VERSION from $VersionFile"
}

$AppVersion = $VersionMatch.Matches[0].Groups[1].Value
$ZipName = "VNC-Station-Controller-$AppVersion.zip"
$ZipPath = Join-Path $RepoRoot "dist\$ZipName"

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
New-Item -ItemType Directory -Force -Path (Join-Path $DistRoot "manual") | Out-Null
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

$UpdatesSrc = Join-Path $RepoRoot "Updates.md"
if (Test-Path $UpdatesSrc) {
    Copy-Item -Force -Path $UpdatesSrc -Destination (Join-Path $DistRoot "Updates.md")
}
else {
    Write-Warning "Updates.md not found in repo root; copy it manually to dist."
}

$ManualSrc = Join-Path $RepoRoot "manual"
$ManualDst = Join-Path $DistRoot "manual"
if (Test-Path $ManualSrc) {
    Copy-Item -Path (Join-Path $ManualSrc "*") -Destination $ManualDst -Recurse -Force
}
else {
    Write-Warning "manual folder not found in repo root; empty folder created in dist."
}

# Runtime folders are created empty in the build output so operators can add their own files later.
$PositionsSrc = Join-Path $RepoRoot "vnc-positions"
$PositionsDst = Join-Path $DistRoot "vnc-positions"
if (-not (Test-Path $PositionsSrc)) {
    Write-Warning "vnc-positions folder not found in repo root; empty folder created in dist."
}

$SetupsSrc = Join-Path $RepoRoot "vnc-setups"
$SetupsDst = Join-Path $DistRoot "vnc-setups"
if (-not (Test-Path $SetupsSrc)) {
    Write-Warning "vnc-setups folder not found in repo root; empty folder created in dist."
}

$ViewSrc = Join-Path $RepoRoot "vnc-view"
if (-not (Test-Path $ViewSrc)) {
    Write-Warning "vnc-view folder not found in repo root; empty folder created in dist."
}

$ControlSrc = Join-Path $RepoRoot "vnc-control"
if (-not (Test-Path $ControlSrc)) {
    Write-Warning "vnc-control folder not found in repo root; empty folder created in dist."
}

if (Test-Path $ZipPath) {
    Remove-Item -Force $ZipPath
}

Compress-Archive -Path $DistRoot -DestinationPath $ZipPath -CompressionLevel Optimal

Write-Host ("Build complete. See " + $DistRoot) -ForegroundColor Green
Write-Host ("Zip package created: " + $ZipPath) -ForegroundColor Green
