$ErrorActionPreference = 'Stop'
$package = $PSScriptRoot
$app = Split-Path (Split-Path $package -Parent) -Parent
$python = Join-Path $app 'chatbot_venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Existing chatbot Python environment unavailable.' }
$run = (Get-Date -Format 'yyyyMMdd_HHmmss') + '_' + ([guid]::NewGuid().ToString('N').Substring(0,8))
$runs = Join-Path $package 'runs'
New-Item -ItemType Directory -Path $runs -Force | Out-Null
$arguments = '-B "' + (Join-Path $package 'run_pilot.py') + '" --backend native --app "' + $app + '" --output "' + $runs + '" --run-id ' + $run
$process = Start-Process -FilePath $python -ArgumentList $arguments -WorkingDirectory $package -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runs ($run + '.stdout.json')) -RedirectStandardError (Join-Path $runs ($run + '.stderr.log'))
try { $process.PriorityClass = 'BelowNormal' } catch { }
Write-Output ('AXIS unapproved three-fact fixture run: ' + $run)
Write-Output '24 main cases plus bounded source/eligibility/isolation checks. Real BGE query embeddings may briefly delay admin replies. No Qwen, production requests, OCR, document embedding rebuild, activation or restart.'
Write-Output ('Progress: ' + (Join-Path $runs ($run + '\PROGRESS.json')))
