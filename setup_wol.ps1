#Requires -Version 5.1
<#
.SYNOPSIS
  Prepare this Windows PC for Wake-on-LAN (clap wake from a second device).
#>
$ErrorActionPreference = "Continue"
Write-Host ""
Write-Host "=== Jarvis Wake-on-LAN setup (run on the PC you want to clap-wake) ===" -ForegroundColor Cyan
Write-Host ""

# --- List adapters ---
$adapters = Get-NetAdapter | Where-Object { $_.MacAddress -and $_.Status -ne "Disabled" }
if (-not $adapters) {
    Write-Host "No network adapters found." -ForegroundColor Red
    exit 1
}

Write-Host "Network adapters:" -ForegroundColor Yellow
$rows = @()
foreach ($a in $adapters) {
    $ip = $null
    try {
        $ip = (Get-NetIPAddress -InterfaceIndex $a.ifIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue |
            Select-Object -First 1 -ExpandProperty IPAddress)
    } catch {}
    $mac = ($a.MacAddress -replace "-", ":").ToUpperInvariant()
    $rows += [pscustomobject]@{ Name = $a.Name; Mac = $mac; Ip = $ip; Status = $a.Status }
    Write-Host ("  {0,-24} MAC {1,-17} {2,-16} {3}" -f $a.Name, $mac, $a.Status, $(if ($ip) { $ip } else { "-" }))
}

$real = $rows | Where-Object { $_.Ip -and ($_.Ip -notlike "169.254.*") }
$chosenRow = ($real | Where-Object { $_.Name -match "Ethernet" } | Select-Object -First 1)
if (-not $chosenRow) { $chosenRow = ($real | Select-Object -First 1) }
if (-not $chosenRow) { $chosenRow = ($rows | Where-Object { $_.Status -eq "Up" } | Select-Object -First 1) }
if (-not $chosenRow) { $chosenRow = $rows | Select-Object -First 1 }

$chosen = @{ Name = $chosenRow.Name; Mac = $chosenRow.Mac; Ip = $chosenRow.Ip }
Write-Host ""
Write-Host "Selected MAC: $($chosen.Mac)  ($($chosen.Name))" -ForegroundColor Green

# --- Enable magic-packet wake on the adapter ---
try {
    Enable-NetAdapterPowerManagement -Name $chosen.Name -WakeOnMagicPacket Enabled -ErrorAction Stop
    Write-Host "Wake on magic packet: ENABLED on $($chosen.Name)" -ForegroundColor Green
} catch {
    Write-Host "Could not toggle WakeOnMagicPacket via PowerShell (may still work from device manager): $_" -ForegroundColor Yellow
}

# Device Manager style wake flags
try {
    $pnps = Get-PnpDevice -Class Net -Status OK -ErrorAction SilentlyContinue
    foreach ($d in $pnps) {
        try {
            powercfg /deviceenablewake "$($d.FriendlyName)" 2>$null | Out-Null
        } catch {}
    }
} catch {}

# --- Fast Startup breaks WOL on many PCs ---
Write-Host ""
Write-Host "Disabling Fast Startup (required for reliable WOL)..." -ForegroundColor Yellow
try {
    Set-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\Power" `
        -Name "HiberbootEnabled" -Value 0 -Type DWord -Force
    Write-Host "Fast Startup: OFF" -ForegroundColor Green
} catch {
    Write-Host "Need Administrator to disable Fast Startup. Re-run this script as Admin." -ForegroundColor Red
}

# --- Enable Bluetooth wake ---
Write-Host ""
Write-Host "Enabling Bluetooth wake devices..." -ForegroundColor Yellow
try {
    Get-PnpDevice -Class Bluetooth -Status OK -ErrorAction SilentlyContinue | ForEach-Object {
        try { powercfg /deviceenablewake $_.FriendlyName 2>$null | Out-Null } catch {}
    }
    Write-Host "Bluetooth wake: armed (where the driver allows it)" -ForegroundColor Green
} catch {
    Write-Host "Bluetooth wake arm skipped: $_" -ForegroundColor Yellow
}

$btMac = $null
try {
    $btAdapter = Get-NetAdapter | Where-Object { $_.Name -match "Bluetooth" -and $_.MacAddress } | Select-Object -First 1
    if ($btAdapter) {
        $btMac = ($btAdapter.MacAddress -replace "-", ":").ToUpperInvariant()
        Write-Host "Bluetooth adapter MAC: $btMac" -ForegroundColor Green
    }
} catch {}

# --- Write MAC into Jarvis configs ---
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$cfgDir = Join-Path $root "config"
$clapCfg = Join-Path $cfgDir "clap_wol.json"
$settings = Join-Path $cfgDir "settings.json"

$broadcast = "255.255.255.255"
if ($chosen.Ip -match "^(\d+)\.(\d+)\.(\d+)\.\d+$") {
    $broadcast = "$($Matches[1]).$($Matches[2]).$($Matches[3]).255"
}

if (Test-Path $clapCfg) {
    try {
        $j = Get-Content $clapCfg -Raw | ConvertFrom-Json
        $j | Add-Member -NotePropertyName transports -NotePropertyValue @("wifi", "bluetooth") -Force
        $j.target_mac = $chosen.Mac
        $j | Add-Member -NotePropertyName wifi_mac -NotePropertyValue $chosen.Mac -Force
        $j.broadcast = $broadcast
        if ($btMac) {
            $j | Add-Member -NotePropertyName bluetooth_mac -NotePropertyValue $btMac -Force
        }
        ($j | ConvertTo-Json -Depth 5) | Set-Content -Path $clapCfg -Encoding UTF8
        Write-Host "Updated config/clap_wol.json" -ForegroundColor Green
    } catch {
        Write-Host "Could not update clap_wol.json: $_" -ForegroundColor Yellow
    }
}

if (Test-Path $settings) {
    try {
        $s = Get-Content $settings -Raw | ConvertFrom-Json
        $s | Add-Member -NotePropertyName wol_mac -NotePropertyValue $chosen.Mac -Force
        $s | Add-Member -NotePropertyName wol_broadcast -NotePropertyValue $broadcast -Force
        if ($btMac) {
            $s | Add-Member -NotePropertyName bluetooth_mac -NotePropertyValue $btMac -Force
        }
        ($s | ConvertTo-Json -Depth 8) | Set-Content -Path $settings -Encoding UTF8
        Write-Host "Updated config/settings.json" -ForegroundColor Green
    } catch {
        Write-Host "Could not update settings.json: $_" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "=== BIOS (do this once) ===" -ForegroundColor Cyan
Write-Host "  Reboot → enter BIOS/UEFI → enable:"
Write-Host "    - Wake on LAN / Power on by PCI-E / ErP ready = Disabled"
Write-Host "  Save & exit."
Write-Host ""
Write-Host "=== Clap device (second always-on machine) ===" -ForegroundColor Cyan
Write-Host "  Default: wakes over Wi-Fi AND Bluetooth."
Write-Host "  1. Copy this folder (or clap_wol_agent.py + config/clap_wol.json)"
Write-Host "  2. On that device:  pip install numpy sounddevice"
Write-Host "  3. Run:  python clap_wol_agent.py"
Write-Host "     Only Wi-Fi:       python clap_wol_agent.py --transport wifi"
Write-Host "     Only Bluetooth:  python clap_wol_agent.py --transport bluetooth"
Write-Host "     BT headset mic:  python clap_wol_agent.py --mic bluetooth"
Write-Host "  4. On this PC say to Jarvis:  standby for clap"
Write-Host "  5. Double-clap → PC wakes"
Write-Host ""
Write-Host "Test from another device on the same LAN:" -ForegroundColor Yellow
Write-Host "  python test_wol.py --transport both"
Write-Host ""
Write-Host "Wi-Fi MAC:       $($chosen.Mac)" -ForegroundColor Green
Write-Host "Broadcast:       $broadcast" -ForegroundColor Green
if ($btMac) { Write-Host "Bluetooth MAC:  $btMac" -ForegroundColor Green }
Write-Host ""
