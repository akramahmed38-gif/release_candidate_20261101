param([int]$Port = 8765)
$ErrorActionPreference = 'Stop'
$releaseRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$stageRoot = Join-Path $releaseRoot 'admin_staging'
$python = 'D:\FawryChatbotPreparation\Scripts\python.exe'
& $python -B -X utf8 (Join-Path $stageRoot 'prepare.py')
if ($LASTEXITCODE -ne 0) { throw 'Staging preparation failed; application was not started.' }
$privateRoot = Join-Path $stageRoot '.private'
$ownerSid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value
& icacls.exe $privateRoot /inheritance:r /grant:r "*${ownerSid}:(OI)(CI)F" '*S-1-5-18:(OI)(CI)F' /Q | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Cannot secure private staging state.' }
$runningFile = Join-Path $stageRoot 'RUNNING.json'
if (Test-Path -LiteralPath $runningFile) {
    $running = Get-Content -LiteralPath $runningFile -Raw | ConvertFrom-Json
    $expectedScript = [System.IO.Path]::GetFullPath((Join-Path $stageRoot 'run_admin.py'))
    if ($running.environment -ne 'isolated_admin_staging' -or $running.script -ne $expectedScript -or $running.url -ne "http://127.0.0.1:${Port}" -or $running.run_id -notmatch '^[a-f0-9]{32}$') { throw 'Existing staging receipt ownership mismatch.' }
    $existing = Get-Process -Id $running.pid -ErrorAction SilentlyContinue
    if ($existing) {
        $health = Invoke-RestMethod -Uri ($running.url + '/health') -TimeoutSec 3
        if ($health.environment -ne 'isolated_admin_staging') { throw 'Existing process identity mismatch.' }
        Write-Output ('Existing isolated admin: ' + $running.url)
        return
    }
    # A workstation restart removes the process but preserves its receipt.
    # Archive that exact validated receipt; never kill a process or reset state.
    $archiveRoot = Join-Path $stageRoot 'state\stale_receipts'
    New-Item -ItemType Directory -Path $archiveRoot -Force | Out-Null
    $archivePath = [System.IO.Path]::GetFullPath((Join-Path $archiveRoot ($running.run_id + '_' + [guid]::NewGuid().ToString('N') + '.json')))
    if (-not $archivePath.StartsWith([System.IO.Path]::GetFullPath($stageRoot) + '\', [System.StringComparison]::OrdinalIgnoreCase)) { throw 'Receipt archive escaped staging.' }
    Move-Item -LiteralPath $runningFile -Destination $archivePath
    Write-Output 'Archived a stopped staging receipt; retained account and knowledge state.'
}
$listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $Port)
try { $listener.Start() } finally { $listener.Stop() }
$logsRoot = Join-Path $stageRoot 'logs'
New-Item -ItemType Directory -Path $logsRoot -Force | Out-Null
$env:FAWRY_STAGING_PORT = [string]$Port
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$stdout = Join-Path $logsRoot ("startup_${stamp}.out.log")
$stderr = Join-Path $logsRoot ("startup_${stamp}.err.log")
$ownedProcess = Start-Process -FilePath $python -ArgumentList @('-u','-B','-X','utf8',(Join-Path $stageRoot 'run_admin.py')) -WorkingDirectory $releaseRoot -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
Remove-Item Env:FAWRY_STAGING_PORT
$deadline = (Get-Date).AddSeconds(45)
do {
    Start-Sleep -Milliseconds 300
    $ownedProcess.Refresh()
    if ($ownedProcess.HasExited) { throw ('Staging stopped during initialization. Inspect private startup logs at ' + $logsRoot) }
    try {
        $health = Invoke-RestMethod -Uri ("http://127.0.0.1:${Port}/health") -TimeoutSec 2
        if ($health.environment -eq 'isolated_admin_staging' -and $health.production -eq $false) {
            Write-Output ("Isolated existing HR admin is running: http://127.0.0.1:${Port}/")
            Write-Output ('Staging account setup required: ' + $health.owner_setup_required)
            return
        }
    } catch { }
} while ((Get-Date) -lt $deadline)
throw 'Staging health deadline reached; no readiness claimed. Inspect owned process and logs.'
