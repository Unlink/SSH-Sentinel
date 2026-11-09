<# Starts/stops only this repository's native TCP proxy. No administrator rights needed. #>
[CmdletBinding()]
param([switch]$Stop)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$projectRoot = Split-Path -Parent $PSScriptRoot
$proxyScript = Join-Path $PSScriptRoot 'windows_proxy.py'
$runtimeDirectory = Join-Path $projectRoot '.superpowers'
$identityFile = Join-Path $runtimeDirectory 'windows-proxy.json'
$python = Join-Path $projectRoot '.venv/Scripts/pythonw.exe'

# Stop remains usable after Python is upgraded or the venv is removed.
$proxyProcess = $null
if (Test-Path -LiteralPath $identityFile) {
    $identity = Get-Content -LiteralPath $identityFile -Raw | ConvertFrom-Json
    $proxyPid = 0
    if ([int]::TryParse([string]$identity.processId, [ref]$proxyPid) -and $proxyPid -gt 0) {
        $candidate = Get-CimInstance Win32_Process -Filter "ProcessId=$proxyPid"
        if ($candidate -and $candidate.CommandLine -and
            $candidate.CommandLine.Contains($proxyScript) -and
            $candidate.ExecutablePath -eq $identity.executablePath -and
            $candidate.CreationDate.ToUniversalTime().Ticks -eq ([datetime]$identity.created).ToUniversalTime().Ticks) {
            $proxyProcess = $candidate
        }
    }
}
if ($Stop) {
    if ($proxyProcess) { Stop-Process -Id $proxyProcess.ProcessId -ErrorAction Stop }
    Remove-Item -LiteralPath $identityFile -Force -ErrorAction SilentlyContinue
    Write-Host 'Stopped this repository''s native proxy.'
    return
}
if ($proxyProcess) {
    $listener = @(Get-NetTCPConnection -State Listen -LocalPort 2222 -ErrorAction SilentlyContinue |
        Where-Object { $_.OwningProcess -eq $proxyProcess.ProcessId })
    if ($listener.Count -gt 0) { Write-Host 'Native proxy is already listening on TCP 2222.'; return }
    throw 'A proxy process exists without its listener. Stop it using -Stop and retry.'
}
if (-not (Test-Path -LiteralPath $python)) {
    throw 'Create the Windows .venv first: py -3 -m venv .venv. The proxy uses only the Python standard library.'
}
$basePython = & (Join-Path $projectRoot '.venv/Scripts/python.exe') -c "import sys; from pathlib import Path; print(Path(sys._base_executable).with_name('pythonw.exe'))"
if ($LASTEXITCODE -ne 0) { throw 'Could not resolve the native Python runtime.' }
if (@(Get-NetTCPConnection -State Listen -LocalPort 2222 -ErrorAction SilentlyContinue).Count -gt 0) {
    throw 'TCP 2222 is occupied by another process. Refusing to stop it.'
}
New-Item -ItemType Directory -Path $runtimeDirectory -Force | Out-Null
$process = $null
try {
    $process = Start-Process -FilePath $python -ArgumentList @(('"' + $proxyScript + '"')) `
        -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $runtimeDirectory 'windows-proxy.stdout.log') `
        -RedirectStandardError (Join-Path $runtimeDirectory 'windows-proxy.stderr.log')
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        $process.Refresh()
        if ($process.HasExited) { throw 'Native proxy exited. See .superpowers/windows-proxy.stderr.log.' }
        $listeners = @(Get-NetTCPConnection -State Listen -LocalPort 2222 -ErrorAction SilentlyContinue)
        foreach ($listener in $listeners) {
            $owner = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)"
            if ($owner -and $owner.CommandLine -and $owner.CommandLine.Contains($proxyScript) -and
                ($owner.ProcessId -eq $process.Id -or $owner.ParentProcessId -eq $process.Id) -and
                ($owner.ExecutablePath -eq $python -or $owner.ExecutablePath -eq $basePython)) {
                # Persist actual socket owner, including birth time to reject reused PIDs.
                @{processId=$owner.ProcessId; executablePath=$owner.ExecutablePath;
                  created=$owner.CreationDate.ToUniversalTime().ToString('o')} |
                    ConvertTo-Json | Set-Content -LiteralPath $identityFile
                Write-Host 'Native proxy listening on 0.0.0.0:2222.'
                return
            }
        }
        Start-Sleep -Milliseconds 100
    }
    throw 'Native proxy did not start listening in time.'
} catch {
    if ($process) {
        # A venv launcher may have a child before it owns a listening socket.
        $children = @(Get-CimInstance Win32_Process -Filter "ParentProcessId=$($process.Id)")
        foreach ($child in $children) {
            if ($child.CommandLine -and $child.CommandLine.Contains($proxyScript) -and
                ($child.ExecutablePath -eq $python -or $child.ExecutablePath -eq $basePython)) {
                Stop-Process -Id $child.ProcessId -ErrorAction SilentlyContinue
            }
        }
        Stop-Process -Id $process.Id -ErrorAction SilentlyContinue
    }
    Remove-Item -LiteralPath $identityFile -Force -ErrorAction SilentlyContinue
    throw
}
