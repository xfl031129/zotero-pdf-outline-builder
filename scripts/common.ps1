$ErrorActionPreference = "Stop"
$env:PYTHONIOENCODING = "utf-8"

function Get-RepoRoot {
    return (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}

function Get-VenvPython {
    param([string] $RepoRoot)
    return Join-Path $RepoRoot ".venv\Scripts\python.exe"
}

function Ensure-PythonEnv {
    param([string] $RepoRoot)

    $python = Get-VenvPython -RepoRoot $RepoRoot
    if (-not (Test-Path $python)) {
        Write-Host "Creating local Python environment..."
        python -m venv (Join-Path $RepoRoot ".venv")
    }

    if (-not (Test-Path $python)) {
        throw "Could not find venv Python at $python"
    }

    Write-Host "Installing dependencies..."
    & $python -m pip install -r (Join-Path $RepoRoot "requirements.txt") pytest | Out-Host
    & $python -m pip install -e $RepoRoot | Out-Host

    return $python
}

function Normalize-UserPath {
    param([string] $PathText)

    if (-not $PathText) {
        return ""
    }

    return $PathText.Trim().Trim('"').Trim("'")
}
