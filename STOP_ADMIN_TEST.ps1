$ErrorActionPreference = 'Stop'
$releaseRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$stageRoot = Join-Path $releaseRoot 'admin_staging'
$receiptPath = Join-Path $stageRoot 'RUNNING.json'
if (-not (Test-Path -LiteralPath $receiptPath)) { Write-Output 'No staging running receipt.'; return }
$receipt = Get-Content -LiteralPath $receiptPath -Raw | ConvertFrom-Json
$expectedScript = [System.IO.Path]::GetFullPath((Join-Path $stageRoot 'run_admin.py'))
if ($receipt.environment -ne 'isolated_admin_staging' -or $receipt.script -ne $expectedScript -or $receipt.url -notmatch '^http://127\.0\.0\.1:\d+$') { throw 'Owned staging receipt validation failed.' }
[System.IO.File]::WriteAllText((Join-Path $stageRoot '.private\stop-request'), [string]$receipt.run_id, [System.Text.UTF8Encoding]::new($false))
$deadline = (Get-Date).AddSeconds(15)
while ((Get-Date) -lt $deadline -and (Get-Process -Id $receipt.pid -ErrorAction SilentlyContinue)) { Start-Sleep -Milliseconds 250 }
if (Get-Process -Id $receipt.pid -ErrorAction SilentlyContinue) { throw 'Graceful staging shutdown not confirmed; no unrelated process was terminated.' }
Write-Output 'Owned isolated staging application stopped.'
