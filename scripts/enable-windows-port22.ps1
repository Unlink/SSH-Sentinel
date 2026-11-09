#Requires -RunAsAdministrator
<# Creates only the explicitly requested inbound TCP 22 rule. #>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$ruleName = 'SSH-Sentinel-Honeypot-TCP22'
$existing = Get-NetFirewallRule -Name $ruleName -ErrorAction SilentlyContinue
if ($existing) {
    $port = $existing | Get-NetFirewallPortFilter
    if ($existing.Direction -ne 'Inbound' -or $port.Protocol -ne 'TCP' -or $port.LocalPort -ne '22') {
        throw "An incompatible rule already uses $ruleName; refusing to change it."
    }
    Set-NetFirewallRule -Name $ruleName -Enabled True -Action Allow -Profile Any | Out-Null
} else {
    New-NetFirewallRule -Name $ruleName -DisplayName 'SSH Sentinel honeypot TCP 22' `
        -Description 'Explicitly enabled internet-facing SSH Sentinel honeypot; dashboard is not exposed.' `
        -Direction Inbound -Action Allow -Protocol TCP -LocalPort 22 `
        -RemoteAddress Any -Profile Any -Enabled True | Out-Null
}
Write-Host 'Enabled the SSH-Sentinel-Honeypot-TCP22 inbound rule. No other firewall rule was changed.'
