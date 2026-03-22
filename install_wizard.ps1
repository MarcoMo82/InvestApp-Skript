#Requires -Version 5.1
<#
.SYNOPSIS
    InvestApp Trading System - Setup Wizard
.DESCRIPTION
    Vollautomatischer Installations-Assistent fuer das InvestApp Trading System.
    Unterstuetzt frische Windows 10/11 Installationen ohne Voraussetzungen.
.NOTES
    Ausfuehren mit: powershell -ExecutionPolicy Bypass -File install_wizard.ps1
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ─────────────────────────────────────────────────────────────
# KONFIGURATION
# ─────────────────────────────────────────────────────────────
$Script:Config = @{
    InstallPath    = "C:\InvestApp"
    SubPath        = "invest_app"
    LogFile        = "C:\InvestApp\install_log.txt"
    MT5Url         = "https://download.mql5.com/cdn/web/metaquotes.software.corp/mt5/mt5setup.exe"
    MT5SetupPath   = "$env:TEMP\mt5setup.exe"
    MT5DefaultPath = "C:\Program Files\MetaTrader 5\terminal64.exe"
    PythonVersion  = "3.11"
    RequiredSpaceGB = 2
    TotalSteps     = 7
}

$Script:Summary = @{
    Python      = $false
    MT5         = $false
    Code        = $false
    VEnv        = $false
    Config      = $false
    DevMode     = $false
    Python_Ver  = ""
    InstallPath = ""
    RepoUrl     = ""
    Errors      = @()
}

# ─────────────────────────────────────────────────────────────
# FARB-HELPER
# ─────────────────────────────────────────────────────────────
function Write-Success { param([string]$Msg) Write-Host $Msg -ForegroundColor Green }
function Write-Info    { param([string]$Msg) Write-Host $Msg -ForegroundColor Cyan }
function Write-Warn    { param([string]$Msg) Write-Host $Msg -ForegroundColor Yellow }
function Write-Err     { param([string]$Msg) Write-Host $Msg -ForegroundColor Red }
function Write-Step    { param([int]$Step, [string]$Msg)
    Write-Host ""
    Write-Host ("─" * 60) -ForegroundColor DarkGray
    Write-Host "  Schritt $Step/$($Script:Config.TotalSteps): $Msg" -ForegroundColor Cyan
    Write-Host ("─" * 60) -ForegroundColor DarkGray
}

# ─────────────────────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────────────────────
function Write-Log {
    param([string]$Msg, [string]$Level = "INFO")
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$timestamp] [$Level] $Msg"
    try {
        $logDir = Split-Path $Script:Config.LogFile -Parent
        if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }
        Add-Content -Path $Script:Config.LogFile -Value $line -Encoding UTF8
    } catch {
        # Log-Schreiben still ignorieren falls Verzeichnis noch nicht existiert
    }
    if ($Level -eq "ERROR") { Write-Err    "  [LOG] $Msg" }
    elseif ($Level -eq "WARN")  { Write-Warn "  [LOG] $Msg" }
}

# ─────────────────────────────────────────────────────────────
# HILFSFUNKTIONEN
# ─────────────────────────────────────────────────────────────
function Ask-YesNo {
    param([string]$Question, [bool]$Default = $true)
    $hint = if ($Default) { "[J/n]" } else { "[j/N]" }
    while ($true) {
        Write-Host "  $Question $hint " -NoNewline -ForegroundColor White
        $input = Read-Host
        if ([string]::IsNullOrWhiteSpace($input)) { return $Default }
        switch ($input.Trim().ToLower()) {
            { $_ -in "j","ja","y","yes" } { return $true  }
            { $_ -in "n","nein","no"   } { return $false }
            default { Write-Warn "  Bitte 'j' oder 'n' eingeben." }
        }
    }
}

function Ask-Input {
    param([string]$Prompt, [string]$Default = "", [bool]$Required = $false)
    while ($true) {
        $hint = if ($Default -ne "") { " [Standard: $Default]" } else { "" }
        Write-Host "  $Prompt$hint : " -NoNewline -ForegroundColor White
        $val = Read-Host
        if ([string]::IsNullOrWhiteSpace($val)) {
            if ($Default -ne "") { return $Default }
            if ($Required) { Write-Warn "  Pflichtfeld — bitte einen Wert eingeben." ; continue }
            return ""
        }
        return $val.Trim()
    }
}

function Ask-SecureInput {
    param([string]$Prompt)
    Write-Host "  $Prompt (Eingabe wird verborgen): " -NoNewline -ForegroundColor White
    $secure = Read-Host -AsSecureString
    return $secure
}

function SecureString-ToPlainText {
    param([System.Security.SecureString]$Secure)
    $ptr = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($Secure)
    try { return [System.Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr) }
    finally { [System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
}

function Reload-Path {
    $env:PATH = [System.Environment]::GetEnvironmentVariable("PATH", "Machine") + ";" +
                [System.Environment]::GetEnvironmentVariable("PATH", "User")
}

function Test-CommandExists {
    param([string]$Command)
    try { Get-Command $Command -ErrorAction Stop | Out-Null ; return $true }
    catch { return $false }
}

function Wait-ProcessWithTimeout {
    param([System.Diagnostics.Process]$Process, [int]$TimeoutSec = 300, [string]$Label = "Prozess")
    $elapsed = 0
    while (-not $Process.HasExited) {
        Start-Sleep -Seconds 5
        $elapsed += 5
        Write-Host "  $Label laeuft... ($elapsed s)" -ForegroundColor DarkGray
        if ($elapsed -ge $TimeoutSec) {
            Write-Warn "  Timeout nach $TimeoutSec Sekunden — Prozess laeuft moeglicherweise noch."
            return $false
        }
    }
    return ($Process.ExitCode -eq 0)
}

# ─────────────────────────────────────────────────────────────
# BANNER
# ─────────────────────────────────────────────────────────────
function Show-Banner {
    Clear-Host
    Write-Host ""
    Write-Host "  ╔══════════════════════════════════════════════════════╗" -ForegroundColor Cyan
    Write-Host "  ║                                                      ║" -ForegroundColor Cyan
    Write-Host "  ║      InvestApp Trading System - Setup Wizard         ║" -ForegroundColor Cyan
    Write-Host "  ║                                                      ║" -ForegroundColor Cyan
    Write-Host "  ║    Automatische Installation & Konfiguration         ║" -ForegroundColor Cyan
    Write-Host "  ║    Version 1.0  |  Windows 10/11                    ║" -ForegroundColor Cyan
    Write-Host "  ║                                                      ║" -ForegroundColor Cyan
    Write-Host "  ╚══════════════════════════════════════════════════════╝" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  Dieser Wizard installiert und konfiguriert das InvestApp" -ForegroundColor White
    Write-Host "  Trading System vollstaendig auf diesem Computer." -ForegroundColor White
    Write-Host ""
    Write-Host "  Log-Datei: $($Script:Config.LogFile)" -ForegroundColor DarkGray
    Write-Host ""
}

# ─────────────────────────────────────────────────────────────
# ADMIN-CHECK & EXECUTION POLICY
# ─────────────────────────────────────────────────────────────
function Test-AdminRights {
    $identity  = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Initialize-ExecutionPolicy {
    try {
        Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
        Write-Log "ExecutionPolicy auf Bypass gesetzt (Prozess-Scope)"
    } catch {
        Write-Log "ExecutionPolicy konnte nicht gesetzt werden: $_" "WARN"
    }
}

# ─────────────────────────────────────────────────────────────
# SCHRITT 1: SYSTEMPRÜFUNG
# ─────────────────────────────────────────────────────────────
function Step1-SystemCheck {
    Write-Step 1 "Systemprüfung"
    Write-Log "Starte Systemprüfung"

    $allOk = $true

    # Admin-Rechte
    Write-Info "  Prüfe Administrator-Rechte..."
    if (Test-AdminRights) {
        Write-Success "  Administrator-Rechte vorhanden ✓"
        Write-Log "Administrator-Rechte: OK"
    } else {
        Write-Warn "  WARNUNG: Kein Administrator!"
        Write-Warn "  Einige Installationen (Python, MT5, Git) benötigen erhöhte Rechte."
        Write-Warn "  Empfehlung: Wizard als Administrator neu starten."
        Write-Warn ""
        Write-Warn "  So starten:"
        Write-Warn "  → Rechtsklick auf PowerShell → 'Als Administrator ausführen'"
        Write-Warn "  → Dann dieses Skript erneut aufrufen"
        Write-Warn ""
        Write-Log "Administrator-Rechte: FEHLEN — Benutzer wurde gewarnt" "WARN"
        $Script:Summary.Errors += "Kein Administrator-Modus"

        if (-not (Ask-YesNo "Trotzdem fortfahren (einige Schritte könnten fehlschlagen)?" $false)) {
            Write-Err "  Abbruch durch Benutzer."
            exit 1
        }
        $allOk = $false
    }

    # Windows-Version
    Write-Info "  Prüfe Windows-Version..."
    try {
        $os = Get-CimInstance Win32_OperatingSystem
        $buildNr = [int]$os.BuildNumber
        $caption = $os.Caption

        if ($buildNr -ge 10240) {
            Write-Success "  $caption (Build $buildNr) ✓"
            Write-Log "Windows-Version: $caption Build $buildNr — OK"
        } else {
            Write-Err "  Nicht unterstützte Windows-Version: $caption (Build $buildNr)"
            Write-Err "  Mindestanforderung: Windows 10"
            Write-Log "Windows-Version nicht unterstützt: $caption Build $buildNr" "ERROR"
            $allOk = $false
        }
    } catch {
        Write-Warn "  Windows-Version konnte nicht ermittelt werden: $_"
        Write-Log "Windows-Version-Prüfung fehlgeschlagen: $_" "WARN"
    }

    # Speicherplatz
    Write-Info "  Prüfe verfügbaren Speicherplatz..."
    try {
        $drive = Split-Path $Script:Config.InstallPath -Qualifier
        $disk  = Get-PSDrive -Name ($drive.TrimEnd(':'))
        $freeGB = [math]::Round($disk.Free / 1GB, 2)
        $minGB  = $Script:Config.RequiredSpaceGB

        if ($freeGB -ge $minGB) {
            Write-Success "  Freier Speicher: $freeGB GB ✓ (Mindest: $minGB GB)"
            Write-Log "Speicherplatz: $freeGB GB — OK"
        } else {
            Write-Err "  Zu wenig Speicher: $freeGB GB frei (mindestens $minGB GB benötigt)"
            Write-Log "Speicherplatz unzureichend: $freeGB GB" "ERROR"
            $Script:Summary.Errors += "Zu wenig Speicherplatz ($freeGB GB)"
            $allOk = $false
        }
    } catch {
        Write-Warn "  Speicherplatz konnte nicht geprüft werden: $_"
        Write-Log "Speicherplatz-Prüfung fehlgeschlagen: $_" "WARN"
    }

    # Internetverbindung
    Write-Info "  Prüfe Internetverbindung..."
    try {
        $ping = Test-Connection -ComputerName "8.8.8.8" -Count 2 -Quiet
        if ($ping) {
            Write-Success "  Internetverbindung verfügbar ✓"
            Write-Log "Internetverbindung: OK"
        } else {
            Write-Err "  Keine Internetverbindung — viele Schritte werden fehlschlagen!"
            Write-Log "Internetverbindung: NICHT VERFÜGBAR" "ERROR"
            $Script:Summary.Errors += "Keine Internetverbindung"
            $allOk = $false
        }
    } catch {
        Write-Warn "  Verbindungstest fehlgeschlagen: $_"
        Write-Log "Ping-Test fehlgeschlagen: $_" "WARN"
    }

    if (-not $allOk) {
        Write-Warn ""
        Write-Warn "  Systemprüfung mit Warnungen abgeschlossen."
        if (-not (Ask-YesNo "Trotzdem fortfahren?" $false)) {
            Write-Err "  Installation abgebrochen."
            exit 1
        }
    } else {
        Write-Success ""
        Write-Success "  Systemprüfung bestanden ✓"
    }

    Write-Log "Systemprüfung abgeschlossen"
}

# ─────────────────────────────────────────────────────────────
# SCHRITT 2: PYTHON INSTALLATION
# ─────────────────────────────────────────────────────────────
function Step2-Python {
    Write-Step 2 "Python 3.11 prüfen / installieren"
    Write-Log "Starte Python-Installation"

    # Prüfen ob Python vorhanden
    $pythonFound = $false
    $pythonExe   = ""

    foreach ($cmd in @("python", "python3", "py")) {
        if (Test-CommandExists $cmd) {
            try {
                $ver = & $cmd --version 2>&1
                if ($ver -match "Python (\d+\.\d+)") {
                    $verNum = [version]$Matches[1]
                    if ($verNum -ge [version]"3.11") {
                        Write-Success "  Python $($verNum.ToString()) gefunden ✓ — überspringe Installation"
                        Write-Log "Python gefunden: $ver"
                        $pythonFound = $true
                        $pythonExe   = $cmd
                        $Script:Summary.Python    = $true
                        $Script:Summary.Python_Ver = $ver.ToString()
                        break
                    } else {
                        Write-Warn "  Python $verNum gefunden, aber Version < 3.11 — Installation empfohlen"
                        Write-Log "Python-Version zu alt: $verNum" "WARN"
                    }
                }
            } catch { }
        }
    }

    if (-not $pythonFound) {
        Write-Info "  Python 3.11+ nicht gefunden."
        if (-not (Ask-YesNo "Python 3.11 jetzt installieren?")) {
            Write-Warn "  Python übersprungen — viele Schritte werden fehlschlagen!"
            Write-Log "Python-Installation vom Benutzer übersprungen" "WARN"
            $Script:Summary.Errors += "Python nicht installiert"
            return
        }

        # winget versuchen
        $installed = $false
        if (Test-CommandExists "winget") {
            Write-Info "  Installiere Python 3.11 via winget..."
            Write-Log "Starte winget-Installation von Python"
            try {
                $proc = Start-Process "winget" -ArgumentList "install --id Python.Python.3.11 --silent --accept-package-agreements --accept-source-agreements" `
                    -Wait -PassThru -NoNewWindow
                if ($proc.ExitCode -eq 0) {
                    Write-Success "  Python via winget installiert ✓"
                    Write-Log "Python via winget installiert"
                    $installed = $true
                } else {
                    Write-Warn "  winget-Installation fehlgeschlagen (Exit: $($proc.ExitCode))"
                    Write-Log "winget Python Exit-Code: $($proc.ExitCode)" "WARN"
                }
            } catch {
                Write-Warn "  winget fehlgeschlagen: $_"
                Write-Log "winget-Fehler: $_" "WARN"
            }
        }

        # Fallback: direkter Download
        if (-not $installed) {
            Write-Info "  winget nicht verfügbar — lade Python direkt von python.org..."
            $pythonUrl      = "https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe"
            $pythonInstaller = "$env:TEMP\python-3.11.9-amd64.exe"

            Write-Info "  Download läuft..."
            Write-Log "Lade Python von $pythonUrl"
            try {
                $ProgressPreference = "SilentlyContinue"
                Invoke-WebRequest -Uri $pythonUrl -OutFile $pythonInstaller -UseBasicParsing
                $ProgressPreference = "Continue"
                Write-Success "  Download abgeschlossen ✓"

                Write-Info "  Starte Python-Installation (bitte warten)..."
                Write-Log "Starte Python-Installer"
                $proc = Start-Process $pythonInstaller `
                    -ArgumentList "/quiet InstallAllUsers=1 PrependPath=1 Include_test=0" `
                    -Wait -PassThru
                if ($proc.ExitCode -eq 0) {
                    Write-Success "  Python installiert ✓"
                    Write-Log "Python-Installer erfolgreich"
                    $installed = $true
                } else {
                    Write-Err "  Python-Installation fehlgeschlagen (Exit: $($proc.ExitCode))"
                    Write-Log "Python-Installer Exit-Code: $($proc.ExitCode)" "ERROR"
                    $Script:Summary.Errors += "Python-Installation fehlgeschlagen"
                }

                Remove-Item $pythonInstaller -Force -ErrorAction SilentlyContinue
            } catch {
                Write-Err "  Python-Download fehlgeschlagen: $_"
                Write-Log "Python-Download-Fehler: $_" "ERROR"
                $Script:Summary.Errors += "Python-Download fehlgeschlagen"
            }
        }

        if ($installed) {
            # PATH neu laden
            Reload-Path

            # Verifikation
            Start-Sleep -Seconds 2
            foreach ($cmd in @("python", "python3", "py")) {
                if (Test-CommandExists $cmd) {
                    try {
                        $ver = & $cmd --version 2>&1
                        if ($ver -match "Python 3\.(1[1-9]|\d{2})") {
                            Write-Success "  Verifikation: $ver ✓"
                            Write-Log "Python-Verifikation: $ver"
                            $Script:Summary.Python    = $true
                            $Script:Summary.Python_Ver = $ver.ToString()
                            break
                        }
                    } catch { }
                }
            }

            if (-not $Script:Summary.Python) {
                Write-Warn "  Python installiert, aber noch nicht im PATH verfügbar."
                Write-Warn "  Bitte neues PowerShell-Fenster öffnen und Wizard neu starten."
                Write-Log "Python im PATH nicht gefunden nach Installation" "WARN"
                $Script:Summary.Errors += "Python nicht im PATH"
            }
        }
    }
}

# ─────────────────────────────────────────────────────────────
# SCHRITT 3: METATRADER 5
# ─────────────────────────────────────────────────────────────
function Step3-MetaTrader {
    Write-Step 3 "MetaTrader 5 prüfen / installieren"
    Write-Log "Starte MT5-Prüfung"

    $mt5Found = $false
    $mt5Path  = ""

    # Registry-Check
    $regPaths = @(
        "HKLM:\SOFTWARE\MetaQuotes Software Corp\MetaTrader 5",
        "HKCU:\SOFTWARE\MetaQuotes Software Corp\MetaTrader 5",
        "HKLM:\SOFTWARE\WOW6432Node\MetaQuotes Software Corp\MetaTrader 5"
    )
    foreach ($rp in $regPaths) {
        if (Test-Path $rp) {
            Write-Log "MT5 Registry-Eintrag gefunden: $rp"
            $mt5Found = $true
            break
        }
    }

    # Pfad-Check
    if (-not $mt5Found) {
        $checkPaths = @(
            $Script:Config.MT5DefaultPath,
            "$env:ProgramFiles\MetaTrader 5\terminal64.exe",
            "${env:ProgramFiles(x86)}\MetaTrader 5\terminal64.exe",
            "$env:LOCALAPPDATA\Programs\MetaTrader 5\terminal64.exe"
        )
        foreach ($p in $checkPaths) {
            if (Test-Path $p) {
                Write-Log "MT5-Pfad gefunden: $p"
                $mt5Found = $true
                $mt5Path  = $p
                break
            }
        }
    }

    if ($mt5Found) {
        Write-Success "  MetaTrader 5 gefunden ✓ — überspringe Installation"
        if ($mt5Path -ne "") { Write-Info "  Pfad: $mt5Path" }
        Write-Log "MT5 bereits installiert"
        $Script:Summary.MT5 = $true
        return
    }

    Write-Info "  MetaTrader 5 nicht gefunden."
    if (-not (Ask-YesNo "MetaTrader 5 jetzt installieren?")) {
        Write-Warn "  MT5 übersprungen — Verbindung zum Broker nicht möglich."
        Write-Log "MT5-Installation vom Benutzer übersprungen" "WARN"
        $Script:Summary.Errors += "MetaTrader 5 nicht installiert"
        return
    }

    Write-Info "  Lade MetaTrader 5 Setup herunter (ca. 6 MB)..."
    Write-Log "Lade MT5 von $($Script:Config.MT5Url)"

    try {
        $ProgressPreference = "SilentlyContinue"
        Invoke-WebRequest -Uri $Script:Config.MT5Url -OutFile $Script:Config.MT5SetupPath -UseBasicParsing
        $ProgressPreference = "Continue"
        Write-Success "  Download abgeschlossen ✓"
    } catch {
        Write-Err "  MT5-Download fehlgeschlagen: $_"
        Write-Log "MT5-Download-Fehler: $_" "ERROR"
        $Script:Summary.Errors += "MT5-Download fehlgeschlagen"
        return
    }

    Write-Info "  Starte MT5-Installation (Silent-Modus, bitte warten)..."
    Write-Log "Starte MT5-Installer"
    try {
        $proc = Start-Process $Script:Config.MT5SetupPath -ArgumentList "/auto" -PassThru
        $ok   = Wait-ProcessWithTimeout -Process $proc -TimeoutSec 300 -Label "MT5-Installation"

        if ($ok) {
            Write-Success "  MetaTrader 5 erfolgreich installiert ✓"
            Write-Log "MT5-Installation erfolgreich"
            $Script:Summary.MT5 = $true
        } else {
            Write-Warn "  MT5-Installer möglicherweise noch aktiv oder fehlgeschlagen."
            Write-Log "MT5-Installer Exit-Problem" "WARN"
        }
    } catch {
        Write-Err "  MT5-Installation fehlgeschlagen: $_"
        Write-Log "MT5-Installer-Fehler: $_" "ERROR"
        $Script:Summary.Errors += "MT5-Installation fehlgeschlagen"
    } finally {
        Remove-Item $Script:Config.MT5SetupPath -Force -ErrorAction SilentlyContinue
    }
}

# ─────────────────────────────────────────────────────────────
# SCHRITT 4: INVESTAPP CODE LADEN
# ─────────────────────────────────────────────────────────────
function Step4-LoadCode {
    Write-Step 4 "InvestApp Code laden"
    Write-Log "Starte Code-Laden"

    Write-Host ""
    Write-Host "  Wie soll der InvestApp-Code geladen werden?" -ForegroundColor White
    Write-Host "  [1] GitHub Repository klonen" -ForegroundColor White
    Write-Host "  [2] Lokaler Pfad (Code bereits vorhanden)" -ForegroundColor White
    Write-Host ""
    Write-Host "  Auswahl [1/2]: " -NoNewline -ForegroundColor White
    $choice = Read-Host

    $targetPath = $Script:Config.InstallPath

    switch ($choice.Trim()) {
        "2" {
            # Lokaler Pfad
            $localPath = Ask-Input "Pfad zum vorhandenen InvestApp-Verzeichnis" "C:\InvestApp" $true

            if (Test-Path $localPath) {
                if ($localPath -ne $targetPath) {
                    Write-Info "  Verzeichnis gefunden. Verwende: $localPath"
                    $Script:Config.InstallPath = $localPath
                } else {
                    Write-Info "  Verzeichnis gefunden: $localPath"
                }
                Write-Success "  Code-Verzeichnis gesetzt: $localPath ✓"
                Write-Log "Lokaler Pfad verwendet: $localPath"
                $Script:Summary.Code        = $true
                $Script:Summary.InstallPath = $localPath
            } else {
                Write-Err "  Verzeichnis nicht gefunden: $localPath"
                Write-Log "Lokaler Pfad nicht gefunden: $localPath" "ERROR"
                $Script:Summary.Errors += "Code-Verzeichnis nicht gefunden"
            }
        }

        default {
            # GitHub klonen
            $repoUrl = Ask-Input "GitHub Repository URL" "" $true
            $Script:Summary.RepoUrl = $repoUrl

            # Git sicherstellen
            if (-not (Test-CommandExists "git")) {
                Write-Info "  Git nicht gefunden — wird installiert..."
                Write-Log "Installiere Git"
                $gitInstalled = $false

                if (Test-CommandExists "winget") {
                    try {
                        $proc = Start-Process "winget" `
                            -ArgumentList "install --id Git.Git --silent --accept-package-agreements --accept-source-agreements" `
                            -Wait -PassThru -NoNewWindow
                        if ($proc.ExitCode -eq 0) {
                            Reload-Path
                            $gitInstalled = Test-CommandExists "git"
                            if ($gitInstalled) {
                                Write-Success "  Git installiert ✓"
                                Write-Log "Git via winget installiert"
                            }
                        }
                    } catch {
                        Write-Log "Git winget-Fehler: $_" "WARN"
                    }
                }

                if (-not $gitInstalled) {
                    Write-Err "  Git-Installation fehlgeschlagen — Code kann nicht geklont werden."
                    Write-Log "Git-Installation fehlgeschlagen" "ERROR"
                    $Script:Summary.Errors += "Git-Installation fehlgeschlagen"
                    return
                }
            } else {
                Write-Success "  Git bereits vorhanden ✓"
                Write-Log "Git bereits installiert"
            }

            # Zielverzeichnis prüfen
            if (Test-Path $targetPath) {
                Write-Warn "  Zielordner $targetPath existiert bereits!"
                if (Ask-YesNo "Vorhandenen Ordner überschreiben (löschen und neu klonen)?" $false) {
                    try {
                        Remove-Item $targetPath -Recurse -Force
                        Write-Info "  Alter Ordner entfernt."
                        Write-Log "Alter Ordner entfernt: $targetPath"
                    } catch {
                        Write-Err "  Konnte Ordner nicht löschen: $_"
                        Write-Log "Ordner-Löschfehler: $_" "ERROR"
                        return
                    }
                } else {
                    Write-Info "  Verwende vorhandenes Verzeichnis."
                    Write-Log "Vorhandenes Verzeichnis wird beibehalten"
                    $Script:Summary.Code        = $true
                    $Script:Summary.InstallPath = $targetPath
                    return
                }
            }

            Write-Info "  Klone Repository nach $targetPath ..."
            Write-Log "git clone $repoUrl $targetPath"
            try {
                & git clone $repoUrl $targetPath 2>&1 | ForEach-Object {
                    Write-Host "    $_" -ForegroundColor DarkGray
                }
                if ($LASTEXITCODE -eq 0) {
                    Write-Success "  Repository erfolgreich geklont ✓"
                    Write-Log "git clone erfolgreich"
                    $Script:Summary.Code        = $true
                    $Script:Summary.InstallPath = $targetPath
                } else {
                    Write-Err "  git clone fehlgeschlagen (Exit: $LASTEXITCODE)"
                    Write-Log "git clone fehlgeschlagen: Exit $LASTEXITCODE" "ERROR"
                    $Script:Summary.Errors += "git clone fehlgeschlagen"
                }
            } catch {
                Write-Err "  Klonen fehlgeschlagen: $_"
                Write-Log "git-clone-Fehler: $_" "ERROR"
                $Script:Summary.Errors += "git clone Fehler: $_"
            }
        }
    }
}

# ─────────────────────────────────────────────────────────────
# SCHRITT 5: PYTHON ENVIRONMENT
# ─────────────────────────────────────────────────────────────
function Step5-VirtualEnv {
    Write-Step 5 "Python Virtual Environment aufsetzen"
    Write-Log "Starte VEnv-Setup"

    if (-not $Script:Summary.Python) {
        Write-Warn "  Python nicht verfügbar — Schritt wird übersprungen."
        Write-Log "VEnv übersprungen: kein Python" "WARN"
        $Script:Summary.Errors += "VEnv nicht erstellt (kein Python)"
        return
    }

    # Projektpfad bestimmen
    $projectPath = $Script:Config.InstallPath
    $subPath     = Join-Path $projectPath $Script:Config.SubPath

    # Prüfe ob invest_app/ Unterordner existiert, sonst direkt InstallPath verwenden
    if (Test-Path $subPath) {
        $workDir = $subPath
    } else {
        $workDir = $projectPath
    }

    if (-not (Test-Path $workDir)) {
        Write-Warn "  Projektordner nicht gefunden: $workDir"
        Write-Warn "  Erstelle Verzeichnis..."
        try {
            New-Item -ItemType Directory -Path $workDir -Force | Out-Null
            Write-Log "Projektordner erstellt: $workDir"
        } catch {
            Write-Err "  Konnte Ordner nicht erstellen: $_"
            Write-Log "Ordner-Erstellfehler: $_" "ERROR"
            $Script:Summary.Errors += "Projektordner fehlt"
            return
        }
    }

    $venvPath = Join-Path $workDir "venv"

    Write-Info "  Projektordner: $workDir"
    Write-Info "  VEnv-Pfad:     $venvPath"
    Write-Log  "Projektordner: $workDir"

    # VEnv erstellen
    Write-Info "  Erstelle Virtual Environment..."
    try {
        & python -m venv $venvPath 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "Exit-Code: $LASTEXITCODE" }
        Write-Success "  Virtual Environment erstellt ✓"
        Write-Log "VEnv erstellt: $venvPath"
    } catch {
        Write-Err "  VEnv-Erstellung fehlgeschlagen: $_"
        Write-Log "VEnv-Erstellfehler: $_" "ERROR"
        $Script:Summary.Errors += "VEnv-Erstellung fehlgeschlagen"
        return
    }

    # pip aktualisieren
    $pipExe = Join-Path $venvPath "Scripts\pip.exe"
    $pythonVEnv = Join-Path $venvPath "Scripts\python.exe"

    Write-Info "  Aktualisiere pip..."
    try {
        & $pythonVEnv -m pip install --upgrade pip --quiet 2>&1 | Out-Null
        Write-Success "  pip aktualisiert ✓"
        Write-Log "pip aktualisiert"
    } catch {
        Write-Warn "  pip-Update fehlgeschlagen (nicht kritisch): $_"
        Write-Log "pip-Update fehlgeschlagen: $_" "WARN"
    }

    # Requirements installieren
    $reqFile = Join-Path $workDir "requirements.txt"
    if (Test-Path $reqFile) {
        Write-Info "  Installiere Python-Pakete aus requirements.txt..."
        Write-Info "  (Dies kann einige Minuten dauern)"
        Write-Log "Starte pip install -r $reqFile"
        try {
            $output = & $pipExe install -r $reqFile 2>&1
            if ($LASTEXITCODE -eq 0) {
                Write-Success "  Pakete erfolgreich installiert ✓"
                Write-Log "pip install abgeschlossen"
                $Script:Summary.VEnv = $true
            } else {
                Write-Warn "  Einige Pakete konnten nicht installiert werden:"
                $output | Where-Object { $_ -match "ERROR|Failed" } | ForEach-Object {
                    Write-Warn "    $_"
                    Write-Log "pip-Fehler: $_" "WARN"
                }
                Write-Warn "  Versuche kritische Pakete einzeln..."

                # Fallback: kritische Pakete manuell
                $criticalPkgs = @("anthropic", "MetaTrader5", "yfinance", "python-dotenv", "requests")
                foreach ($pkg in $criticalPkgs) {
                    try {
                        & $pipExe install $pkg --quiet 2>&1 | Out-Null
                        Write-Success "    $pkg ✓"
                        Write-Log "Paket installiert: $pkg"
                    } catch {
                        Write-Err "    $pkg FEHLER: $_"
                        Write-Log "Paket-Fehler: $pkg — $_" "ERROR"
                        $Script:Summary.Errors += "Paket fehlgeschlagen: $pkg"
                    }
                }
                $Script:Summary.VEnv = $true
            }
        } catch {
            Write-Err "  pip install fehlgeschlagen: $_"
            Write-Log "pip-install-Fehler: $_" "ERROR"
            $Script:Summary.Errors += "pip install fehlgeschlagen"
        }
    } else {
        Write-Warn "  requirements.txt nicht gefunden unter $reqFile"
        Write-Warn "  Installiere Standard-Pakete..."
        Write-Log "requirements.txt fehlt — installiere Standard-Pakete" "WARN"

        $defaultPkgs = @("anthropic", "MetaTrader5", "yfinance", "python-dotenv", "requests", "pandas", "numpy")
        foreach ($pkg in $defaultPkgs) {
            try {
                & $pipExe install $pkg --quiet 2>&1 | Out-Null
                Write-Success "    $pkg ✓"
                Write-Log "Standard-Paket installiert: $pkg"
            } catch {
                Write-Err "    $pkg FEHLER"
                Write-Log "Standard-Paket-Fehler: $pkg" "WARN"
            }
        }
        $Script:Summary.VEnv = $true
    }

    # VEnv-Pfad für spätere Schritte speichern
    $Script:Config["VEnvPath"]     = $venvPath
    $Script:Config["WorkDir"]      = $workDir
    $Script:Config["PythonVEnv"]   = $pythonVEnv
}

# ─────────────────────────────────────────────────────────────
# SCHRITT 6: KONFIGURATION (.env)
# ─────────────────────────────────────────────────────────────
function Step6-Configuration {
    Write-Step 6 "System konfigurieren (.env Datei)"
    Write-Log "Starte Konfiguration"

    $workDir = if ($Script:Config.ContainsKey("WorkDir")) { $Script:Config["WorkDir"] } else { $Script:Config.InstallPath }
    $envFile = Join-Path $workDir ".env"

    # Prüfen ob .env schon existiert
    if (Test-Path $envFile) {
        Write-Info "  .env Datei bereits vorhanden: $envFile"
        if (-not (Ask-YesNo "Bestehende Konfiguration überschreiben?" $false)) {
            Write-Info "  Konfiguration beibehalten — überspringe Schritt 6."
            Write-Log ".env bereits vorhanden — nicht überschrieben"
            $Script:Summary.Config = $true
            return
        }
    }

    Write-Host ""
    Write-Host "  Bitte die folgenden Zugangsdaten eingeben:" -ForegroundColor White
    Write-Host "  (Alle Angaben werden lokal in .env gespeichert — niemals weitergeben!)" -ForegroundColor DarkGray
    Write-Host ""

    # [1/5] Anthropic API Key
    Write-Host "  [1/5] Anthropic API Key" -ForegroundColor Cyan
    Write-Host "        → Key erhältlich unter: https://console.anthropic.com" -ForegroundColor DarkGray
    $anthropicKey = Ask-Input "        Eingabe" "" $false

    Write-Host ""

    # [2/5] MT5 Kontonummer
    Write-Host "  [2/5] MetaTrader 5 Demo-Login (Kontonummer)" -ForegroundColor Cyan
    $mt5Login = Ask-Input "        Kontonummer" "" $false

    Write-Host ""

    # [3/5] MT5 Passwort
    Write-Host "  [3/5] MetaTrader 5 Passwort" -ForegroundColor Cyan
    $mt5PasswordSecure = Ask-SecureInput "        Passwort"
    $mt5Password = SecureString-ToPlainText $mt5PasswordSecure

    Write-Host ""

    # [4/5] MT5 Server
    Write-Host "  [4/5] MetaTrader 5 Server" -ForegroundColor Cyan
    Write-Host "        Beispiele: XM-Demo, ICMarkets-Demo02, Pepperstone-Demo" -ForegroundColor DarkGray
    $mt5Server = Ask-Input "        Server" "XM-Demo" $false

    Write-Host ""

    # [5/5] Handelsmodus
    Write-Host "  [5/5] Handelsmodus" -ForegroundColor Cyan
    Write-Host "        demo = empfohlen für den Start (kein Echtgeld-Risiko)" -ForegroundColor DarkGray
    Write-Host "  [ENTER] für Demo bestätigen oder 'live' eingeben: " -NoNewline -ForegroundColor White
    $tradingMode = Read-Host
    if ([string]::IsNullOrWhiteSpace($tradingMode)) { $tradingMode = "demo" }
    $tradingMode = $tradingMode.Trim().ToLower()

    Write-Host ""

    # .env schreiben
    Write-Info "  Schreibe .env Datei..."
    Write-Log "Schreibe .env: $envFile"

    try {
        $envContent = @"
# InvestApp Trading System - Konfiguration
# Erstellt: $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")
# ACHTUNG: Diese Datei niemals in Git committen!

# Anthropic API
ANTHROPIC_API_KEY=$anthropicKey

# MetaTrader 5
MT5_LOGIN=$mt5Login
MT5_PASSWORD=$mt5Password
MT5_SERVER=$mt5Server

# Handelsmodus: demo oder live
TRADING_MODE=$tradingMode

# Installationspfad
INSTALL_PATH=$($Script:Config.InstallPath)
"@

        Set-Content -Path $envFile -Value $envContent -Encoding UTF8
        Write-Success "  .env Datei erstellt ✓"
        Write-Log ".env Datei geschrieben"

        # .gitignore sicherstellen
        $gitignorePath = Join-Path $workDir ".gitignore"
        $gitignoreEntry = ".env"
        if (Test-Path $gitignorePath) {
            $existingContent = Get-Content $gitignorePath -Raw
            if ($existingContent -notmatch "\.env") {
                Add-Content -Path $gitignorePath -Value "`n# Lokale Konfiguration`n.env"
                Write-Info "  .env zu .gitignore hinzugefügt ✓"
                Write-Log ".env in .gitignore eingetragen"
            }
        } else {
            Set-Content -Path $gitignorePath -Value "# Lokale Konfiguration`n.env`nvenv/`n__pycache__/`n*.pyc" -Encoding UTF8
            Write-Info "  .gitignore erstellt ✓"
            Write-Log ".gitignore erstellt"
        }

        $Script:Summary.Config = $true

    } catch {
        Write-Err "  .env konnte nicht geschrieben werden: $_"
        Write-Log ".env Schreib-Fehler: $_" "ERROR"
        $Script:Summary.Errors += ".env Erstellung fehlgeschlagen"
    }
}

# ─────────────────────────────────────────────────────────────
# SCHRITT 7 (OPTIONAL): ENTWICKLERMODUS
# ─────────────────────────────────────────────────────────────
function Step7-DeveloperMode {
    Write-Step 7 "Entwicklermodus (Optional): Mac ↔ Windows Sync via GitHub"
    Write-Log "Entwicklermodus-Abfrage"

    if (-not (Ask-YesNo "Entwicklermodus aktivieren? (Mac ↔ Windows Sync via GitHub)")) {
        Write-Info "  Entwicklermodus übersprungen."
        Write-Log "Entwicklermodus: übersprungen"
        return
    }

    Write-Info "  Entwicklermodus wird eingerichtet..."
    Write-Log "Starte Entwicklermodus-Setup"

    # Git sicherstellen
    if (-not (Test-CommandExists "git")) {
        Write-Info "  Git nicht gefunden — wird installiert..."
        if (Test-CommandExists "winget") {
            try {
                $proc = Start-Process "winget" `
                    -ArgumentList "install --id Git.Git --silent --accept-package-agreements --accept-source-agreements" `
                    -Wait -PassThru -NoNewWindow
                Reload-Path
                if (-not (Test-CommandExists "git")) {
                    Write-Err "  Git-Installation fehlgeschlagen — Entwicklermodus abgebrochen."
                    Write-Log "Git für Entwicklermodus nicht installierbar" "ERROR"
                    $Script:Summary.Errors += "Git-Installation fehlgeschlagen (Entwicklermodus)"
                    return
                }
                Write-Success "  Git installiert ✓"
                Write-Log "Git für Entwicklermodus installiert"
            } catch {
                Write-Err "  Git-Installation fehlgeschlagen: $_"
                return
            }
        } else {
            Write-Err "  winget nicht verfügbar — Git kann nicht automatisch installiert werden."
            Write-Warn "  Bitte Git manuell von https://git-scm.com installieren."
            return
        }
    } else {
        Write-Success "  Git verfügbar ✓"
    }

    # GitHub-Konfiguration
    Write-Host ""
    $githubUser  = Ask-Input "  GitHub Benutzername" "" $true
    $githubEmail = Ask-Input "  GitHub E-Mail Adresse" "" $true
    $repoUrl     = Ask-Input "  GitHub Repository URL" $Script:Summary.RepoUrl $true

    # Git global konfigurieren
    Write-Info "  Konfiguriere Git (global)..."
    try {
        & git config --global user.name  $githubUser  2>&1 | Out-Null
        & git config --global user.email $githubEmail 2>&1 | Out-Null
        Write-Success "  Git-Konfiguration gesetzt ✓"
        Write-Log "git config: user.name=$githubUser, user.email=$githubEmail"
    } catch {
        Write-Warn "  Git-Konfiguration fehlgeschlagen: $_"
        Write-Log "git config fehlgeschlagen: $_" "WARN"
    }

    # Remote setzen oder Repository klonen
    $installPath = $Script:Config.InstallPath
    if (Test-Path (Join-Path $installPath ".git")) {
        Write-Info "  Git-Repository bereits vorhanden — aktualisiere Remote-URL..."
        try {
            Set-Location $installPath
            & git remote set-url origin $repoUrl 2>&1 | Out-Null
            Write-Success "  Remote-URL aktualisiert ✓"
            Write-Log "git remote set-url: $repoUrl"
        } catch {
            Write-Warn "  Remote-URL konnte nicht gesetzt werden: $_"
            Write-Log "git remote set-url Fehler: $_" "WARN"
        }
    } elseif (-not (Test-Path $installPath)) {
        Write-Info "  Klone Repository nach $installPath ..."
        try {
            & git clone $repoUrl $installPath 2>&1 | ForEach-Object { Write-Host "    $_" -ForegroundColor DarkGray }
            if ($LASTEXITCODE -eq 0) {
                Write-Success "  Repository geklont ✓"
                Write-Log "git clone für Entwicklermodus: $repoUrl"
            }
        } catch {
            Write-Err "  Clone fehlgeschlagen: $_"
            Write-Log "git clone Entwicklermodus-Fehler: $_" "ERROR"
        }
    } else {
        Write-Warn "  Verzeichnis existiert, aber ist kein Git-Repo."
        Write-Info "  Initialisiere Git-Repository..."
        try {
            Set-Location $installPath
            & git init 2>&1 | Out-Null
            & git remote add origin $repoUrl 2>&1 | Out-Null
            Write-Success "  Git-Repository initialisiert ✓"
            Write-Log "git init + remote add"
        } catch {
            Write-Err "  Git-Initialisierung fehlgeschlagen: $_"
        }
    }

    # Sync-Skript erstellen
    $syncBat = Join-Path $installPath "sync_and_start.bat"
    $workDir = if ($Script:Config.ContainsKey("WorkDir")) { $Script:Config["WorkDir"] } else { $installPath }
    $venvActivate = Join-Path $workDir "venv\Scripts\activate.bat"

    Write-Info "  Erstelle sync_and_start.bat ..."
    Write-Log "Erstelle $syncBat"

    try {
        $batContent = @"
@echo off
:: InvestApp - Täglicher Sync und Start
:: Synchronisiert Code von GitHub und startet das System

title InvestApp - Sync und Start
color 0A

echo.
echo  ╔═══════════════════════════════════════╗
echo  ║   InvestApp - Sync und Start          ║
echo  ╚═══════════════════════════════════════╝
echo.

:: In Installationsverzeichnis wechseln
cd /d "$installPath"
if errorlevel 1 (
    echo  FEHLER: Verzeichnis nicht gefunden: $installPath
    pause
    exit /b 1
)

:: Code von GitHub laden
echo  [1/3] Hole aktuellen Code von GitHub...
git pull
if errorlevel 1 (
    echo  WARNUNG: git pull fehlgeschlagen - starte trotzdem mit lokalem Code
)
echo.

:: Virtual Environment aktivieren
echo  [2/3] Aktiviere Python-Umgebung...
call "$venvActivate"
if errorlevel 1 (
    echo  FEHLER: Virtual Environment nicht gefunden
    echo  Bitte install_wizard.ps1 erneut ausfuehren
    pause
    exit /b 1
)
echo.

:: InvestApp starten
echo  [3/3] Starte InvestApp...
cd /d "$workDir"
python main.py
if errorlevel 1 (
    echo.
    echo  FEHLER: InvestApp konnte nicht gestartet werden.
    echo  Prüfe die Fehlermeldung oben.
)

echo.
echo  InvestApp beendet. Druecke eine Taste zum Schliessen...
pause > nul
"@
        Set-Content -Path $syncBat -Value $batContent -Encoding ASCII
        Write-Success "  sync_and_start.bat erstellt: $syncBat ✓"
        Write-Log "sync_and_start.bat erstellt"
    } catch {
        Write-Err "  Batch-Datei konnte nicht erstellt werden: $_"
        Write-Log "Batch-Datei-Fehler: $_" "ERROR"
    }

    # Täglichen Workflow erklären
    Write-Host ""
    Write-Host "  ┌──────────────────────────────────────────────────────┐" -ForegroundColor DarkGray
    Write-Host "  │  TÄGLICHER WORKFLOW (Entwicklermodus)                │" -ForegroundColor White
    Write-Host "  │                                                      │" -ForegroundColor DarkGray
    Write-Host "  │  Auf dem Mac:                                        │" -ForegroundColor White
    Write-Host "  │    → Code bearbeiten                                 │" -ForegroundColor DarkGray
    Write-Host "  │    → git add . && git commit -m 'Update'             │" -ForegroundColor DarkGray
    Write-Host "  │    → git push                                        │" -ForegroundColor DarkGray
    Write-Host "  │                                                      │" -ForegroundColor DarkGray
    Write-Host "  │  Auf dem Windows PC:                                 │" -ForegroundColor White
    Write-Host "  │    → sync_and_start.bat doppelklicken                │" -ForegroundColor DarkGray
    Write-Host "  │    → Pulls automatisch + startet InvestApp           │" -ForegroundColor DarkGray
    Write-Host "  │                                                      │" -ForegroundColor DarkGray
    Write-Host "  │  Shortcut: $syncBat" -ForegroundColor Cyan
    Write-Host "  └──────────────────────────────────────────────────────┘" -ForegroundColor DarkGray
    Write-Host ""

    $Script:Summary.DevMode = $true
    Write-Log "Entwicklermodus erfolgreich eingerichtet"
}

# ─────────────────────────────────────────────────────────────
# ABSCHLUSS & ZUSAMMENFASSUNG
# ─────────────────────────────────────────────────────────────
function Show-Summary {
    Write-Host ""
    Write-Host ("═" * 60) -ForegroundColor Cyan
    Write-Host "  INSTALLATIONS-ZUSAMMENFASSUNG" -ForegroundColor Cyan
    Write-Host ("═" * 60) -ForegroundColor Cyan
    Write-Host ""

    $checkMark = "[OK]"
    $crossMark = "[--]"

    function Show-Item { param([bool]$Status, [string]$Label, [string]$Detail = "")
        if ($Status) {
            Write-Host ("  $checkMark  $Label" + $(if ($Detail) { "  ($Detail)" } else { "" })) -ForegroundColor Green
        } else {
            Write-Host ("  $crossMark  $Label") -ForegroundColor DarkGray
        }
    }

    Show-Item $Script:Summary.Python  "Python 3.11+"       $Script:Summary.Python_Ver
    Show-Item $Script:Summary.MT5     "MetaTrader 5"
    Show-Item $Script:Summary.Code    "InvestApp Code"     $Script:Summary.InstallPath
    Show-Item $Script:Summary.VEnv    "Python VEnv + Pakete"
    Show-Item $Script:Summary.Config  "Konfiguration (.env)"
    Show-Item $Script:Summary.DevMode "Entwicklermodus (Git Sync)"

    if ($Script:Summary.Errors.Count -gt 0) {
        Write-Host ""
        Write-Host "  Warnungen / Fehler:" -ForegroundColor Yellow
        foreach ($err in $Script:Summary.Errors) {
            Write-Host "    ! $err" -ForegroundColor Yellow
        }
    }

    Write-Host ""
    Write-Host ("─" * 60) -ForegroundColor DarkGray
    Write-Host "  Log-Datei: $($Script:Config.LogFile)" -ForegroundColor DarkGray
    Write-Host ("─" * 60) -ForegroundColor DarkGray
    Write-Host ""
}

function Show-PostInstall {
    $workDir = if ($Script:Config.ContainsKey("WorkDir")) { $Script:Config["WorkDir"] } else { $Script:Config.InstallPath }

    # Verbindungstest anbieten
    if ($Script:Summary.MT5 -and $Script:Summary.VEnv) {
        if (Ask-YesNo "MT5-Verbindung jetzt testen?") {
            Write-Info "  Starte Verbindungstest..."
            Write-Log "Starte Verbindungstest"
            $pythonVEnv = if ($Script:Config.ContainsKey("PythonVEnv")) {
                $Script:Config["PythonVEnv"]
            } else {
                "python"
            }
            try {
                $testScript = @"
import MetaTrader5 as mt5
if mt5.initialize():
    info = mt5.terminal_info()
    print(f'MT5 Verbunden: {info.name}')
    mt5.shutdown()
else:
    print(f'MT5 Verbindung fehlgeschlagen: {mt5.last_error()}')
"@
                $tmpScript = "$env:TEMP\mt5_test.py"
                Set-Content -Path $tmpScript -Value $testScript -Encoding UTF8
                & $pythonVEnv $tmpScript 2>&1 | ForEach-Object { Write-Host "    $_" -ForegroundColor Cyan }
                Remove-Item $tmpScript -Force -ErrorAction SilentlyContinue
                Write-Log "Verbindungstest durchgeführt"
            } catch {
                Write-Warn "  Verbindungstest fehlgeschlagen: $_"
                Write-Log "Verbindungstest-Fehler: $_" "WARN"
            }
        }
    }

    Write-Host ""

    # System starten anbieten
    $mainScript = Join-Path $workDir "main.py"
    if (Test-Path $mainScript) {
        if (Ask-YesNo "InvestApp jetzt starten?") {
            Write-Info "  Starte InvestApp..."
            Write-Log "Starte main.py"
            $pythonVEnv = if ($Script:Config.ContainsKey("PythonVEnv")) {
                $Script:Config["PythonVEnv"]
            } else {
                "python"
            }
            try {
                Set-Location $workDir
                & $pythonVEnv $mainScript
            } catch {
                Write-Err "  Start fehlgeschlagen: $_"
                Write-Log "main.py Start fehlgeschlagen: $_" "ERROR"
            }
        }
    } else {
        Write-Warn "  main.py nicht gefunden — System kann nicht automatisch gestartet werden."
        Write-Warn "  Bitte Projektstruktur prüfen: $workDir"
    }

    Write-Host ""
    Write-Host ("═" * 60) -ForegroundColor Cyan
    Write-Host "  HINWEISE FÜR DEN TÄGLICHEN BETRIEB" -ForegroundColor Cyan
    Write-Host ("═" * 60) -ForegroundColor Cyan
    Write-Host ""
    if ($Script:Summary.DevMode) {
        Write-Host "  → Täglich: sync_and_start.bat im InvestApp-Ordner starten" -ForegroundColor White
        Write-Host "    Pfad: $($Script:Config.InstallPath)\sync_and_start.bat" -ForegroundColor DarkGray
    } else {
        $activatePath = if ($Script:Config.ContainsKey("VEnvPath")) {
            "$($Script:Config["VEnvPath"])\Scripts\activate"
        } else {
            "$($Script:Config.InstallPath)\venv\Scripts\activate"
        }
        Write-Host "  → VEnv aktivieren: $activatePath" -ForegroundColor DarkGray
        Write-Host "  → Starten: python main.py" -ForegroundColor DarkGray
    }
    Write-Host ""
    Write-Host "  → Bei Problemen: Log prüfen unter $($Script:Config.LogFile)" -ForegroundColor DarkGray
    Write-Host ""
    Write-Success "  Installation abgeschlossen. Viel Erfolg mit InvestApp!"
    Write-Host ""
}

# ─────────────────────────────────────────────────────────────
# HAUPTPROGRAMM
# ─────────────────────────────────────────────────────────────
function Main {
    # ExecutionPolicy temporär setzen
    Initialize-ExecutionPolicy

    try {
        # Log initialisieren
        $logDir = Split-Path $Script:Config.LogFile -Parent
        if (-not (Test-Path $logDir)) {
            New-Item -ItemType Directory -Path $logDir -Force -ErrorAction SilentlyContinue | Out-Null
        }
        Write-Log "=========================================="
        Write-Log "InvestApp Setup Wizard gestartet"
        Write-Log "Windows: $([System.Environment]::OSVersion.VersionString)"
        Write-Log "PowerShell: $($PSVersionTable.PSVersion)"
        Write-Log "=========================================="

        # Banner anzeigen
        Show-Banner

        Write-Host "  Bereit zum Starten? Alle Schritte können einzeln übersprungen werden." -ForegroundColor White
        Write-Host ""
        if (-not (Ask-YesNo "Installation starten?")) {
            Write-Info "  Abbruch durch Benutzer."
            Write-Log "Installation vom Benutzer abgebrochen"
            exit 0
        }

        # Installationsschritte
        Step1-SystemCheck
        Step2-Python
        Step3-MetaTrader
        Step4-LoadCode
        Step5-VirtualEnv
        Step6-Configuration
        Step7-DeveloperMode

        # Abschluss
        Write-Log "Alle Installationsschritte abgeschlossen"
        Show-Summary
        Show-PostInstall

    } catch {
        Write-Err ""
        Write-Err "  UNERWARTETER FEHLER: $_"
        Write-Err "  Bitte Log prüfen: $($Script:Config.LogFile)"
        Write-Log "FATALER FEHLER: $_" "ERROR"
        Write-Log $_.ScriptStackTrace "ERROR"
    } finally {
        # ExecutionPolicy zurücksetzen ist bei -Scope Process nicht nötig
        # (wird automatisch mit dem Prozess beendet)
        Write-Log "Setup Wizard beendet"
        Write-Host ""
        Write-Host "  Drücke [ENTER] zum Beenden..." -ForegroundColor DarkGray
        Read-Host | Out-Null
    }
}

# Einstiegspunkt
Main
