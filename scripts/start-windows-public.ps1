<#
.SYNOPSIS
Applies Docker Desktop VM isolation before starting the honeypot on TCP 2222.
.DESCRIPTION
Run again after every Docker Desktop/VM restart. The public sensor uses
restart=no so it cannot restart before the VM firewall has been reapplied.
Starts a native Windows proxy; does not modify Windows firewall policy or unrelated containers.
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$projectRoot = Split-Path -Parent $PSScriptRoot
$dockerCommand = (Get-Command docker -ErrorAction Stop).Source
$composeFiles = @('compose', '-f', (Join-Path $projectRoot 'docker-compose.yml'), '-f', (Join-Path $projectRoot 'compose.windows-public.yml'))

function Invoke-Docker {
    param([string[]]$DockerArguments)
    & $dockerCommand @DockerArguments
    if ($LASTEXITCODE -ne 0) { throw "Docker command failed (exit $LASTEXITCODE). Public startup aborted." }
}

if ((& $dockerCommand context show) -ne 'desktop-linux') {
    throw 'This helper targets the desktop-linux Docker Desktop context only.'
}

# This profile and the VM firewall are deliberately fixed to the default subnet.
$resolved = & $dockerCommand @composeFiles config --format json
if ($LASTEXITCODE -ne 0) { throw 'Compose configuration could not be resolved.' }
$configuration = $resolved | ConvertFrom-Json
if ($configuration.networks.'sensor-net'.ipam.config[0].subnet -ne '172.30.222.0/24') {
    throw 'This deployment requires SENSOR_SUBNET=172.30.222.0/24. Adjust and audit the firewall before changing it.'
}
if ($configuration.services.web.ports[0].host_ip -ne '127.0.0.1') {
    throw 'The dashboard must remain bound to 127.0.0.1.'
}

if ($configuration.services.sensor.ports[0].host_ip -ne '127.0.0.1' -or
    $configuration.services.sensor.ports[0].published -ne '2223' -or
    $configuration.services.sensor.environment.SENTINEL_PROXY_PROTOCOL -ne 'true') {
    throw 'The trusted PROXY backend must be bound only to 127.0.0.1:2223 with mandatory PROXY parsing.'
}

# Permit migration from our older Docker-public binding, or our own native proxy.
$listeners = @(Get-NetTCPConnection -State Listen -LocalPort 2222 -ErrorAction SilentlyContinue)
if ($listeners.Count -gt 0) {
    $ownPorts = & $dockerCommand compose -f (Join-Path $projectRoot 'docker-compose.yml') ps sensor --format json
    if ($LASTEXITCODE -ne 0) { throw 'Could not inspect sensor bindings.' }
    $currentSensor = $ownPorts | ConvertFrom-Json
    $ownBinding = @($currentSensor.Publishers | Where-Object {
        $_.URL -eq '0.0.0.0' -and $_.PublishedPort -eq 2222 -and $_.TargetPort -eq 2222
    })
    if ($ownBinding.Count -eq 0) {
        $proxyScript = Join-Path $PSScriptRoot 'windows_proxy.py'
        foreach ($listener in $listeners) {
            $process = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)"
            if (-not $process -or -not $process.CommandLine -or -not $process.CommandLine.Contains($proxyScript)) {
                throw 'Port 2222 is occupied by another process. No existing server will be stopped.'
            }
        }
    }
}

Invoke-Docker -DockerArguments @('build', '-f', (Join-Path $projectRoot 'docker/Dockerfile.firewall'), '-t', 'ssh-sentinel-firewall:local', $projectRoot)
# Stop only this project's sensor; the dashboard and other containers are untouched.
Invoke-Docker -DockerArguments ($composeFiles + @('stop', 'sensor'))

$firewallArguments = @('run', '--rm', '--user', '0:0', '--network', 'host',
    '--cap-drop', 'ALL', '--cap-add', 'NET_ADMIN', '--security-opt', 'no-new-privileges',
    '--read-only', '--tmpfs', '/run:size=1m,noexec,nosuid,nodev',
    'ssh-sentinel-firewall:local', '172.30.222.0/24')
Invoke-Docker -DockerArguments $firewallArguments

# A failed firewall command exits above, leaving the public sensor stopped.
Invoke-Docker -DockerArguments ($composeFiles + @('up', '-d', '--build', '--wait'))
& (Join-Path $PSScriptRoot 'start-windows-proxy.ps1')
Write-Host 'Native proxy on 0.0.0.0:2222; trusted backend on 127.0.0.1:2223; dashboard on 127.0.0.1:8080.'
Write-Host 'Verify the live egress checks in docs/windows-public.md before accepting internet traffic.'
Write-Host 'Run this helper again after restarting Docker Desktop. Do not use the override directly.'
