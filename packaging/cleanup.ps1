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
    ".pyinstaller",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "htmlcov"
)

foreach ($name in $targets) {
    $path = Join-Path $RepoRoot $name
    if (Test-Path $path) {
        try {
            Remove-Item -Recurse -Force $path
            Write-Host "Removed $name"
        }
        catch {
            Write-Warning ("Failed to remove {0}: {1}" -f $name, $_.Exception.Message)
        }
    }
}

# Remove generated spec files.
Get-ChildItem -Path $RepoRoot -Filter "*.spec" -File -ErrorAction SilentlyContinue | ForEach-Object {
    try {
        Remove-Item -Force $_.FullName
        Write-Host ("Removed " + $_.Name)
    }
    catch {
        Write-Warning ("Failed to remove {0}: {1}" -f $_.Name, $_.Exception.Message)
    }
}

# Remove Python cache folders recursively.
Get-ChildItem -Path $RepoRoot -Recurse -Directory -Force -ErrorAction SilentlyContinue | Where-Object {
    $_.Name -eq "__pycache__"
} | ForEach-Object {
    try {
        Remove-Item -Recurse -Force $_.FullName
        Write-Host ("Removed " + $_.FullName)
    }
    catch {
        Write-Warning ("Failed to remove {0}: {1}" -f $_.FullName, $_.Exception.Message)
    }
}

if ($Deep) {
    $venvPath = Join-Path $RepoRoot ".venv"
    if (Test-Path $venvPath) {
        try {
            Remove-Item -Recurse -Force $venvPath
            Write-Host "Removed .venv (Deep mode)"
        }
        catch {
            Write-Warning ("Failed to remove .venv: {0}" -f $_.Exception.Message)
        }
    }
}

Write-Host "Cleanup complete." -ForegroundColor Green
