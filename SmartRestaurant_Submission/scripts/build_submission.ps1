param([string]$OutputName = 'SmartRestaurant_Submission')
$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
if ($OutputName -notmatch '^SmartRestaurant_Submission(?:_[A-Za-z0-9_-]+)?$') { throw 'Output must be a named submission directory inside project.' }
$pythonPath = Join-Path $projectRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { $pythonPath = 'python' }
& $pythonPath (Join-Path $PSScriptRoot 'submission_builder.py') --output-name $OutputName
if ($LASTEXITCODE -ne 0) { throw 'Submission build failed; original project was not removed.' }
