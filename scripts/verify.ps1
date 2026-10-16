$ErrorActionPreference = 'Stop'
$repoPath = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $repoPath '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Create .venv and install code/requirements-dev.txt first.' }
Push-Location $repoPath
try {
    # A new confined directory avoids shared Windows pytest-temp permission issues.
    $testDirectory = Join-Path $repoPath ('code/.scratch/verify-' + [guid]::NewGuid().ToString())
    New-Item -ItemType Directory -Path $testDirectory | Out-Null
    & $pythonPath -m pytest code/tests -q -p no:cacheprovider --basetemp (Join-Path $testDirectory 'run')
    if ($LASTEXITCODE -ne 0) { throw 'Python checks failed.' }
    & node --test code/tests/review_page.test.cjs
    if ($LASTEXITCODE -ne 0) { throw 'Review-page interaction checks failed.' }
    & git diff --check
    if ($LASTEXITCODE -ne 0) { throw 'Diff whitespace check failed.' }
} finally {
    Pop-Location
}
