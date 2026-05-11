$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
$pip = Join-Path $projectRoot ".venv\Scripts\pip.exe"
$pyinstaller = Join-Path $projectRoot ".venv\Scripts\pyinstaller.exe"
$helperTargetDir = Join-Path $projectRoot "zotero-plugin\native\win"
$helperTarget = Join-Path $helperTargetDir "outline-helper.exe"
$releaseDir = Join-Path $projectRoot "dist\release"
$xpiSource = Join-Path $projectRoot "dist\pdf-outline-builder-for-zotero.xpi"
$releaseXpi = Join-Path $releaseDir "zotero-pdf-outline-builder-windows-v0.1.2.xpi"
$updatesPath = Join-Path $releaseDir "updates.json"

if (-not (Test-Path -LiteralPath $python)) {
  throw "Missing virtual environment Python: $python. Run RUN_ME.bat or create .venv first."
}

& $pip install -e $projectRoot pyinstaller | Out-Host

Remove-Item -LiteralPath (Join-Path $projectRoot "build\outline-helper") -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath (Join-Path $projectRoot "dist\outline-helper.exe") -Force -ErrorAction SilentlyContinue

Push-Location $projectRoot
try {
  & $pyinstaller `
    --noconfirm `
    --clean `
    --onefile `
    --name outline-helper `
    --paths "$projectRoot\src" `
    "$projectRoot\zotero-plugin\native\run_outline.py"
} finally {
  Pop-Location
}

New-Item -ItemType Directory -Force -Path $helperTargetDir | Out-Null
Copy-Item -LiteralPath (Join-Path $projectRoot "dist\outline-helper.exe") -Destination $helperTarget -Force

$env:PDF_OUTLINE_RELEASE = "1"
try {
  powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $projectRoot "zotero-plugin\scripts\build-xpi.ps1")
} finally {
  Remove-Item Env:\PDF_OUTLINE_RELEASE -ErrorAction SilentlyContinue
}

New-Item -ItemType Directory -Force -Path $releaseDir | Out-Null
Copy-Item -LiteralPath $xpiSource -Destination $releaseXpi -Force

$hash = (Get-FileHash -LiteralPath $releaseXpi -Algorithm SHA256).Hash.ToLowerInvariant()
$updates = @{
  addons = @{
    "zotero-pdf-outline-builder@xfl031129.github.io" = @{
      updates = @(
        @{
          version = "0.1.2"
          update_link = "https://github.com/xfl031129/zotero-pdf-outline-builder/releases/download/v0.1.2/zotero-pdf-outline-builder-windows-v0.1.2.xpi"
          update_hash = "sha256:$hash"
          applications = @{
            zotero = @{
              strict_min_version = "6.999"
              strict_max_version = "9.0.*"
            }
          }
        }
      )
    }
  }
} | ConvertTo-Json -Depth 10
Set-Content -LiteralPath $updatesPath -Value $updates -Encoding UTF8

Write-Host "Built release XPI: $releaseXpi"
Write-Host "SHA256: $hash"
Write-Host "Update manifest template: $updatesPath"
