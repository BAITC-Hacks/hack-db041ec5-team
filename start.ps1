param([switch]$Demo, [switch]$Check, [switch]$NoBrowser, [switch]$Web)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$pythonExe = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonExe)) {
    Write-Host 'Creating Python environment...'
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3.12 -m venv .venv
    } elseif (Get-Command python -ErrorAction SilentlyContinue) {
        & python -m venv .venv
    } else {
        throw 'Install Python 3.12 (enable Add Python to PATH), then run START.cmd again.'
    }
    if ($LASTEXITCODE -ne 0) { throw 'Could not create Python environment.' }
}
$ErrorActionPreference = 'Continue'
& $pythonExe -c "import pandas, numpy, scipy, networkx, pyarrow, yaml, streamlit, pyvis, altair, pytest; from importlib.metadata import version; from pathlib import Path; assert all(version(line.split('==')[0]) == line.split('==')[1] for line in Path('requirements-lock.txt').read_text().splitlines() if '==' in line)" 2>$null
$needInstall = $LASTEXITCODE -ne 0
$ErrorActionPreference = 'Stop'
& $pythonExe -c "import importlib.util, sys; sys.exit(0 if importlib.util.find_spec('pip') else 1)"
if ($LASTEXITCODE -ne 0) {
    & $pythonExe -m ensurepip --upgrade
    if ($LASTEXITCODE -ne 0) { throw 'Could not install pip. Recreate .venv using Python 3.12.' }
}
if ($needInstall) {
    Write-Host 'Installing dependencies. Internet may be required...'
    & $pythonExe -m pip install -r requirements-lock.txt
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed. Check the connection and retry.' }
}
if ($Check) {
    & $pythonExe -X utf8 -m pytest -q --durations=5
    exit $LASTEXITCODE
}
if ($Web) {
    Write-Host 'Web app: http://127.0.0.1:8600 (Ctrl+C to stop)'
    if (-not $NoBrowser) { Start-Process 'http://127.0.0.1:8600' }
    & $pythonExe -X utf8 -m uvicorn api.index:app --host 127.0.0.1 --port 8600
    exit $LASTEXITCODE
}
$env:MONEYGRAPH_DEMO = if ($Demo) { '1' } else { '0' }
$env:MONEYGRAPH_OUTPUT_DIR = Join-Path $PSScriptRoot 'output\current'
$env:MONEYGRAPH_DATA_DIR = Join-Path $PSScriptRoot 'data'
$env:PYTHONUTF8 = '1'
if (-not $Demo -and ((Test-Path 'data\nodes.parquet') -or (Test-Path 'data\data\nodes.parquet'))) {
    Write-Host 'Analyzing local data. Please wait...'
    & $pythonExe -X utf8 run.py --data data --out output/current --config config.yaml
    if ($LASTEXITCODE -ne 0) { throw 'Analysis failed. Check the input files and the error above.' }
}
$headless = if ($NoBrowser) { 'true' } else { 'false' }
& $pythonExe -m streamlit run app.py --server.address 127.0.0.1 --server.headless $headless --browser.gatherUsageStats false
exit $LASTEXITCODE
