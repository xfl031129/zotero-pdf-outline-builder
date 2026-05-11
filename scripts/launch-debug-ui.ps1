. "$PSScriptRoot\common.ps1"

$repoRoot = Get-RepoRoot
Set-Location $repoRoot
$python = Ensure-PythonEnv -RepoRoot $repoRoot

Write-Host ""
Write-Host "Starting drag-and-drop debug UI..."
Write-Host "Close this window to stop the local server."
& $python -m zotero_pdf_outline_builder.debug_server

