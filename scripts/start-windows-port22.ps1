<#
.SYNOPSIS
Applies Docker Desktop VM isolation before starting the honeypot on TCP 22.
.DESCRIPTION
Run again after every Docker Desktop/VM restart. The public sensor uses
restart=no so it cannot restart before the VM firewall has been reapplied.
Does not modify Windows firewall policy or any unrelated container.
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$projectRoot = Split-Path -Parent $PSScriptRoot
$dockerCommand = (Get-Command docker -ErrorAction Stop).Source
$composeFiles = @('compose', '-f', (Join-Path $projectRoot 'docker-compose.yml'), '-f', (Join-Path $projectRoot 'compose.windows-port22.yml'))

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

$listeners = @(Get-NetTCPConnection -State Listen -LocalPort 22 -ErrorAction SilentlyContinue)
if ($listeners.Count -gt 0) {
    $ownPorts = & $dockerCommand compose -f (Join-Path $projectRoot 'docker-compose.yml') ps sensor --format json
    if ($LASTEXITCODE -ne 0) { throw 'Could not inspect the current sensor port bindings.' }
    $currentSensor = $ownPorts | ConvertFrom-Json
    $ownBinding = @($currentSensor.Publishers | Where-Object {
        $_.URL -eq '0.0.0.0' -and $_.PublishedPort -eq 22 -and $_.TargetPort -eq 2222
    })
    if ($ownBinding.Count -eq 0) {
        throw 'Port 22 is already occupied. No existing SSH server will be stopped.'
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
Write-Host 'Honeypot listening on 0.0.0.0:22; dashboard remains on 127.0.0.1:8080.'
Write-Host 'Verify the live egress checks in docs/windows-port22.md before accepting internet traffic.'
Write-Host 'Run this helper again after restarting Docker Desktop. Do not use the override directly.'
