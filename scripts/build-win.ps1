<#
.SYNOPSIS
    Build DeskSearch on Windows (PowerShell equivalent of scripts/build.sh).

.DESCRIPTION
    Produces any of:
      wheel     — Python wheel in dist/pypi/ (includes the built React UI)
      backend   — standalone PyInstaller binary in dist/desksearch-backend/
      electron  — Windows NSIS installer + unpacked app in dist/electron/
      ui        — React UI in src/ui/dist (also copied to src/desksearch/ui_dist)
      test      — pytest run

    The electron target depends on the backend target, so it runs it first.

.PARAMETER Target
    wheel | backend | electron | ui | test | all   (default: wheel)

.PARAMETER SkipTests
    Do not run pytest before packaging.

.EXAMPLE
    pwsh -File scripts/build-win.ps1 electron
    pwsh -File scripts/build-win.ps1 all -SkipTests
#>
[CmdletBinding()]
param(
    [ValidateSet('wheel', 'backend', 'electron', 'ui', 'test', 'all')]
    [string]$Target = 'wheel',

    [switch]$SkipTests
)

# Native tools (npm, pyinstaller) write progress and warnings to stderr; with
# ErrorActionPreference = 'Stop' PowerShell turns those into terminating errors.
# Keep 'Continue' and gate on $LASTEXITCODE instead.
$ErrorActionPreference = 'Continue'
$ProgressPreference = 'SilentlyContinue'

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$VenvPython = Join-Path $RepoRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $VenvPython)) {
    throw "Virtualenv not found at .venv. Create it first:  python -m venv .venv; .\.venv\Scripts\python.exe -m pip install -e `".[dev]`""
}

function Write-Step($message) { Write-Host "`n=== $message ===" -ForegroundColor Cyan }
function Write-Ok($message)   { Write-Host "OK  $message" -ForegroundColor Green }

<#
.SYNOPSIS
    Run a native command and fail the build on a non-zero exit code.

.DESCRIPTION
    npm and pyinstaller report progress/warnings on stderr, which PowerShell
    would surface as errors. Output is streamed through untouched and only the
    exit code decides success.
#>
function Invoke-Native {
    param(
        [Parameter(Mandatory)][string]$Command,
        [Parameter(ValueFromRemainingArguments)][string[]]$Arguments
    )
    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Command $($Arguments -join ' ') failed with exit code $LASTEXITCODE"
    }
}

function Build-Ui {
    Write-Step 'Building React UI'
    Push-Location (Join-Path $RepoRoot 'src\ui')
    try {
        Invoke-Native npm ci
        Invoke-Native npm run build
    } finally { Pop-Location }

    # The served bundle lives inside the Python package so both the wheel and
    # the PyInstaller build pick it up.
    $uiDist = Join-Path $RepoRoot 'src\ui\dist'
    $pkgUi = Join-Path $RepoRoot 'src\desksearch\ui_dist'
    Remove-Item -Recurse -Force $pkgUi -ErrorAction SilentlyContinue
    Copy-Item -Recurse $uiDist $pkgUi
    Write-Ok 'UI built and copied to src/desksearch/ui_dist'
}

function Build-Backend {
    Write-Step 'Building standalone backend (PyInstaller)'
    Invoke-Native $VenvPython -m pip install pyinstaller --quiet

    if (-not (Test-Path (Join-Path $RepoRoot 'src\ui\dist'))) {
        Write-Host 'src/ui/dist missing — building UI first' -ForegroundColor Yellow
        Build-Ui
    }

    Invoke-Native $VenvPython -m PyInstaller desksearch.spec --clean --noconfirm

    $exe = Join-Path $RepoRoot 'dist\desksearch-backend\desksearch-backend.exe'
    if (-not (Test-Path $exe)) { throw "Backend executable not produced: $exe" }
    Write-Ok "Backend at $exe"
}

function Build-Wheel {
    Write-Step 'Building Python wheel'
    Invoke-Native $VenvPython -m pip install build --quiet
    Invoke-Native $VenvPython -m build --wheel --outdir dist/pypi
    Write-Ok 'Wheel in dist/pypi/'
}

function Build-Electron {
    Write-Step 'Building Electron Windows app'
    Build-Backend

    Push-Location (Join-Path $RepoRoot 'electron')
    try {
        Invoke-Native npm ci

        # No signing certificate in local builds — mirrors CI behaviour.
        $env:CSC_IDENTITY_AUTO_DISCOVERY = 'false'
        Invoke-Native npm run dist:win
    } finally { Pop-Location }

    Write-Ok 'Installer in dist/electron/'
}

function Invoke-Tests {
    Write-Step 'Running test suite'
    Invoke-Native $VenvPython -m pytest tests/ --tb=short -q
    Write-Ok 'Tests passed'
}

if (-not $SkipTests -and $Target -ne 'ui') { Invoke-Tests }

switch ($Target) {
    'ui'       { Build-Ui }
    'wheel'    { Build-Ui; Build-Wheel }
    'backend'  { Build-Backend }
    'electron' { Build-Ui; Build-Electron }
    'test'     { }   # already ran above
    'all'      { Build-Ui; Build-Wheel; Build-Electron }
}

Write-Host "`n=== Done ===" -ForegroundColor Cyan
Get-ChildItem -Path (Join-Path $RepoRoot 'dist') -ErrorAction SilentlyContinue |
    Select-Object Name, @{n = 'SizeMB'; e = {
        if ($_.PSIsContainer) {
            [math]::Round((Get-ChildItem $_.FullName -Recurse -File |
                Measure-Object Length -Sum).Sum / 1MB, 1)
        } else { [math]::Round($_.Length / 1MB, 2) }
    } } | Format-Table -AutoSize
