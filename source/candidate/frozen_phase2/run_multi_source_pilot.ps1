$ErrorActionPreference = 'Stop'
$package = $PSScriptRoot

# BUNDLE_BOOTSTRAP
if (-not (Test-Path -LiteralPath (Join-Path $package 'run_phase2.py'))) {
    $bundle = Join-Path $package 'PHASE2_PACKAGE.zip'
    if ((Get-FileHash -LiteralPath $bundle -Algorithm SHA256).Hash.ToLowerInvariant() -ne 'ed62d2cb2b31765acfdf2790399220d3f36cca9b5fb43c2329a35c040476eb1b') { throw 'Isolated bundle fingerprint mismatch.' }
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [System.IO.Compression.ZipFile]::ExtractToDirectory($bundle, $package)
}

$app = Split-Path (Split-Path $package -Parent) -Parent
$python = Join-Path $app 'chatbot_venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Existing chatbot Python unavailable.' }
$pins = Get-Content -LiteralPath (Join-Path $package 'PACKAGE_PINS.json') -Raw | ConvertFrom-Json
foreach ($entry in $pins.PSObject.Properties) {
    $path = Join-Path $package $entry.Name
    if ((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $entry.Value) { throw 'Isolated package fingerprint mismatch.' }
}
$run = (Get-Date -Format 'yyyyMMdd_HHmmss') + '_' + ([guid]::NewGuid().ToString('N').Substring(0,8))
$runs = Join-Path $package 'runs'
New-Item -ItemType Directory -Path $runs -Force | Out-Null
$arguments = '-B "' + (Join-Path $package 'run_phase2.py') + '" --backend native --app "' + $app + '" --output "' + $runs + '" --run-id ' + $run
$process = Start-Process -FilePath $python -ArgumentList $arguments -WorkingDirectory $package -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runs ($run + '.stdout.json')) -RedirectStandardError (Join-Path $runs ($run + '.stderr.log'))
try { $process.PriorityClass = 'BelowNormal' } catch { }
Write-Output ('Phase 2 unapproved fixture run: ' + $run)
Write-Output '50 fixed main requests (including 24 frozen Phase 1 regressions), two setup turns and six integrity checks. Three source units, ten facts. Real query embeddings may briefly delay admin replies. No Qwen, OCR, document embeddings, production requests, activation or restart.'
Write-Output ('Progress: ' + (Join-Path $runs ($run + '\PROGRESS.json')))
