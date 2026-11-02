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
    $existing = Get-Process -Id $running.pid -ErrorAction SilentlyContinue
    if ($existing) {
        $health = Invoke-RestMethod -Uri ($running.url + '/health') -TimeoutSec 3
        if ($health.environment -ne 'isolated_admin_staging') { throw 'Existing process identity mismatch.' }
        Write-Output ('Existing isolated admin: ' + $running.url)
        return
    }
    throw 'Stale running receipt requires inspection; no process was replaced.'
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
