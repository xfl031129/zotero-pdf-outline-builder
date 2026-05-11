. "$PSScriptRoot\common.ps1"

$repoRoot = Get-RepoRoot
Set-Location $repoRoot
$python = Ensure-PythonEnv -RepoRoot $repoRoot

$sample = Join-Path $repoRoot "examples\sample-paper.pdf"
$output = Join-Path $repoRoot "examples\sample-paper.outlined.pdf"
$debug = Join-Path $repoRoot "examples\sample-paper.debug.pdf"

Write-Host ""
Write-Host "Running tests..."
& $python -m pytest -q

Write-Host ""
Write-Host "Dry run sample PDF..."
& $python -m zotero_pdf_outline_builder $sample --dry-run

Write-Host ""
Write-Host "Writing sample outlined PDF..."
& $python -m zotero_pdf_outline_builder $sample -o $output --force --debug-pdf $debug

Write-Host ""
Write-Host "Checking written outline..."
& $python -c "import fitz, sys; doc = fitz.open(sys.argv[1]); print(doc.get_toc(simple=True)); doc.close()" $output

Write-Host ""
Write-Host "Done."
Write-Host "Output:"
Write-Host $output
Write-Host "Debug PDF:"
Write-Host $debug
