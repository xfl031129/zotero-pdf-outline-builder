$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$pluginRoot = Join-Path $projectRoot "zotero-plugin"
$distDir = Join-Path $projectRoot "dist"
$xpiPath = Join-Path $distDir "pdf-outline-builder-for-zotero.xpi"

function ConvertTo-JSString([string] $value) {
  return $value.Replace("\", "\\").Replace('"', '\"')
}

$pythonPath = Join-Path $projectRoot ".venv\Scripts\python.exe"
$helperScript = Join-Path $pluginRoot "native\run_outline.py"
$projectSrc = Join-Path $projectRoot "src"
$releaseMode = $env:PDF_OUTLINE_RELEASE -eq "1"

if (-not (Test-Path -LiteralPath $pythonPath)) {
  throw "Python not found: $pythonPath. Run the normal setup first."
}

$configPath = Join-Path $pluginRoot "chrome\content\config.js"
if ($releaseMode) {
  $config = @"
var PDFOutlineBuilderConfig = {
  useBundledHelper: true,
  bundledHelper: "native/win/outline-helper.exe",
  minConfidence: 0.30,
  force: true
};
"@
} else {
  $config = @"
var PDFOutlineBuilderConfig = {
  pythonPath: "$(ConvertTo-JSString $pythonPath)",
  helperScript: "$(ConvertTo-JSString $helperScript)",
  projectSrc: "$(ConvertTo-JSString $projectSrc)",
  minConfidence: 0.30,
  force: true
};
"@
}
Set-Content -LiteralPath $configPath -Value $config -Encoding UTF8

New-Item -ItemType Directory -Force -Path $distDir | Out-Null
Remove-Item -LiteralPath $xpiPath -Force -ErrorAction SilentlyContinue

& $pythonPath (Join-Path $pluginRoot "scripts\build_xpi.py") $pluginRoot $xpiPath
Write-Host "Built $xpiPath"
