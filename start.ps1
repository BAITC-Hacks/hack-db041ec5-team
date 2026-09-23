param([switch]$Demo)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$pythonExe = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonExe)) { throw 'Создайте .venv и установите requirements-lock.txt по README.md' }
if ($Demo) { $env:MONEYGRAPH_DEMO = '1' }
& $pythonExe -m streamlit run app.py --server.address 127.0.0.1
