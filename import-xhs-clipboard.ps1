$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$researchPython = Join-Path $PSScriptRoot '.venv-xhs\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $researchPython)) {
    throw '请先运行 python -m venv .venv-xhs 并在该环境安装 requirements-xhs.txt'
}
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
# Send clipboard content as text on stdin, never as shell code or a process argument.
Get-Clipboard -Raw | & $researchPython -X utf8 xhs_research.py import-curl --stdin --run --by-company --comments --limit 2
exit $LASTEXITCODE
