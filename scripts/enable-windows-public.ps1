#Requires -RunAsAdministrator
<# Creates only the explicitly requested inbound TCP 2222 rule. #>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$ruleName = 'SSH-Sentinel-Honeypot-TCP2222'
$existing = Get-NetFirewallRule -Name $ruleName -ErrorAction SilentlyContinue
if ($existing) {
    $port = $existing | Get-NetFirewallPortFilter
    if ($existing.Direction -ne 'Inbound' -or $port.Protocol -ne 'TCP' -or $port.LocalPort -ne '2222') {
        throw "An incompatible rule already uses $ruleName; refusing to change it."
    }
    Set-NetFirewallRule -Name $ruleName -Enabled True -Action Allow -Profile Any | Out-Null
} else {
    New-NetFirewallRule -Name $ruleName -DisplayName 'SSH Sentinel honeypot TCP 2222' `
        -Description 'Explicitly enabled internet-facing SSH Sentinel honeypot; dashboard is not exposed.' `
        -Direction Inbound -Action Allow -Protocol TCP -LocalPort 2222 `
        -RemoteAddress Any -Profile Any -Enabled True | Out-Null
}
# Retire only this project's previous TCP 22 rule after enabling the new port.
$oldRule = Get-NetFirewallRule -Name 'SSH-Sentinel-Honeypot-TCP22' -ErrorAction SilentlyContinue
if ($oldRule) {
    $oldPort = $oldRule | Get-NetFirewallPortFilter
    if ($oldRule.Direction -eq 'Inbound' -and $oldPort.Protocol -eq 'TCP' -and $oldPort.LocalPort -eq '22') {
        Disable-NetFirewallRule -Name 'SSH-Sentinel-Honeypot-TCP22' | Out-Null
    }
}
Write-Host 'Enabled the SSH Sentinel TCP 2222 rule and retired its previous TCP 22 rule if present.'
