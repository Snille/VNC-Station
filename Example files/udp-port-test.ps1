param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("listen", "send")]
    [string]$Mode,

    [int]$Port = 50000,

    [string]$TargetIP = "",

    [string]$Message = "UDP test"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Show-FirewallHelp {
    Write-Host ""
    Write-Host "If UDP traffic fails, create an inbound firewall rule (run PowerShell as Administrator):" -ForegroundColor Yellow
    Write-Host "  New-NetFirewallRule -DisplayName 'VNC Station UDP 50000' -Direction Inbound -Protocol UDP -LocalPort 50000 -Action Allow"
    Write-Host ""
    Write-Host "If Python is blocked, allow python.exe in Windows Defender Firewall as well."
}

if ($Mode -eq "listen") {
    $udp = [System.Net.Sockets.UdpClient]::new($Port)
    $endpoint = [System.Net.IPEndPoint]::new([System.Net.IPAddress]::Any, 0)

    Write-Host "Listening on UDP port $Port ..."
    Write-Host "Waiting for one packet. Press Ctrl+C to quit."

    try {
        $bytes = $udp.Receive([ref]$endpoint)
        $text = [System.Text.Encoding]::UTF8.GetString($bytes)
        Write-Host ("Received from {0}:{1} -> {2}" -f $endpoint.Address, $endpoint.Port, $text) -ForegroundColor Green

        $ackText = "ACK from $env:COMPUTERNAME"
        $ackBytes = [System.Text.Encoding]::UTF8.GetBytes($ackText)
        [void]$udp.Send($ackBytes, $ackBytes.Length, $endpoint)
        Write-Host ("Sent ACK back to {0}:{1}" -f $endpoint.Address, $endpoint.Port)
    }
    catch {
        Write-Error $_
        Show-FirewallHelp
        exit 1
    }
    finally {
        $udp.Dispose()
    }

    exit 0
}

if (-not $TargetIP) {
    Write-Error "TargetIP is required in send mode. Example: .\udp-port-test.ps1 -Mode send -TargetIP 192.168.1.50"
    exit 1
}

$sender = [System.Net.Sockets.UdpClient]::new()
$sender.Client.ReceiveTimeout = 5000
$targetEndpoint = [System.Net.IPEndPoint]::new([System.Net.IPAddress]::Parse($TargetIP), $Port)
$listenEndpoint = [System.Net.IPEndPoint]::new([System.Net.IPAddress]::Any, 0)

try {
    $payload = [System.Text.Encoding]::UTF8.GetBytes($Message)
    [void]$sender.Send($payload, $payload.Length, $targetEndpoint)
    Write-Host ("Sent to {0}:{1} -> {2}" -f $TargetIP, $Port, $Message)

    $ackBytes = $sender.Receive([ref]$listenEndpoint)
    $ackText = [System.Text.Encoding]::UTF8.GetString($ackBytes)
    Write-Host ("Received reply from {0}:{1} -> {2}" -f $listenEndpoint.Address, $listenEndpoint.Port, $ackText) -ForegroundColor Green
}
catch {
    Write-Error "No reply received or UDP failed."
    Show-FirewallHelp
    exit 1
}
finally {
    $sender.Dispose()
}

exit 0

