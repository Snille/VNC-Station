param(
    [switch]$Deep
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Write-Host "Repo root: $RepoRoot"

# Safe cleanup targets (generated artifacts only).
$targets = @(
    "build",
    "dist",
    "logs",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "htmlcov"
)

foreach ($name in $targets) {
    $path = Join-Path $RepoRoot $name
    if (Test-Path $path) {
        Remove-Item -Recurse -Force $path
        Write-Host "Removed $name"
    }
}

# Remove generated spec files.
Get-ChildItem -Path $RepoRoot -Filter "*.spec" -File -ErrorAction SilentlyContinue | ForEach-Object {
    Remove-Item -Force $_.FullName
    Write-Host ("Removed " + $_.Name)
}

# Remove Python cache folders recursively.
Get-ChildItem -Path $RepoRoot -Recurse -Directory -Force -ErrorAction SilentlyContinue | Where-Object {
    $_.Name -eq "__pycache__"
} | ForEach-Object {
    Remove-Item -Recurse -Force $_.FullName
    Write-Host ("Removed " + $_.FullName)
}

if ($Deep) {
    $venvPath = Join-Path $RepoRoot ".venv"
    if (Test-Path $venvPath) {
        Remove-Item -Recurse -Force $venvPath
        Write-Host "Removed .venv (Deep mode)"
    }
}

Write-Host "Cleanup complete." -ForegroundColor Green

