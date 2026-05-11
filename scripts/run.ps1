. "$PSScriptRoot\common.ps1"

$repoRoot = Get-RepoRoot
Set-Location $repoRoot
$python = Ensure-PythonEnv -RepoRoot $repoRoot

Write-Host ""
Write-Host "Zotero PDF Outline Builder"
Write-Host "=========================="
Write-Host "1. Dry run sample PDF"
Write-Host "2. Dry run my PDF or folder"
Write-Host "3. Create outlined PDF from one PDF"
Write-Host "4. Batch create outlined PDFs from a folder"
Write-Host "5. Run tests"
Write-Host "6. Launch drag-and-drop debug UI"
Write-Host ""

$choice = Read-Host "Choose 1-6"

switch ($choice) {
    "1" {
        & $python -m zotero_pdf_outline_builder (Join-Path $repoRoot "examples\sample-paper.pdf") --dry-run
    }
    "2" {
        $target = Normalize-UserPath (Read-Host "Paste PDF file path or folder path")
        if (-not (Test-Path $target)) {
            throw "Path does not exist: $target"
        }
        $recursive = Read-Host "Recursive folder scan? y/N"
        if ($recursive -match "^(y|yes)$") {
            & $python -m zotero_pdf_outline_builder $target --recursive --dry-run
        } else {
            & $python -m zotero_pdf_outline_builder $target --dry-run
        }
    }
    "3" {
        $target = Normalize-UserPath (Read-Host "Paste one PDF file path")
        if (-not (Test-Path $target)) {
            throw "Path does not exist: $target"
        }
        $item = Get-Item $target
        if ($item.PSIsContainer) {
            throw "This option needs one PDF file, not a folder."
        }
        $output = Join-Path $item.DirectoryName ($item.BaseName + ".outlined" + $item.Extension)
        & $python -m zotero_pdf_outline_builder $item.FullName -o $output
        Write-Host ""
        Write-Host "Output:"
        Write-Host $output
    }
    "4" {
        $target = Normalize-UserPath (Read-Host "Paste folder path")
        if (-not (Test-Path $target)) {
            throw "Path does not exist: $target"
        }
        $outputDir = Join-Path $repoRoot "outlined-output"
        $recursive = Read-Host "Recursive folder scan? Y/n"
        if ($recursive -match "^(n|no)$") {
            & $python -m zotero_pdf_outline_builder $target --output-dir $outputDir
        } else {
            & $python -m zotero_pdf_outline_builder $target --recursive --output-dir $outputDir
        }
        Write-Host ""
        Write-Host "Output folder:"
        Write-Host $outputDir
    }
    "5" {
        & $python -m pytest -q
    }
    "6" {
        & $python -m zotero_pdf_outline_builder.debug_server
    }
    default {
        throw "Unknown choice: $choice"
    }
}
