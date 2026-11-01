# Telegram Task Bot Launcher for Windows PowerShell
$ErrorActionPreference = "Continue"
$Host.UI.RawUI.WindowTitle = "Telegram Task Bot"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $ScriptDir) { $ScriptDir = Get-Location }
Set-Location $ScriptDir

function Show-Header {
    Clear-Host
    Write-Host "========================================================" -ForegroundColor Cyan
    Write-Host "           TELEGRAM TASK BOT LAUNCHER" -ForegroundColor Cyan
    Write-Host "========================================================" -ForegroundColor Cyan
    Write-Host ""
}

function Find-Python {
    $candidates = @(
        "python",
        "py",
        "python3",
        "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python310\python.exe",
        "C:\Program Files\Python313\python.exe",
        "C:\Program Files\Python312\python.exe",
        "C:\Program Files\Python311\python.exe",
        "C:\Program Files\Python310\python.exe"
    )

    foreach ($c in $candidates) {
        if ($c.Contains("\") -and (-not (Test-Path $c))) { continue }
        try {
            $testOut = & $c --version 2>&1
            if ($testOut -match "Python \d+\.\d+") {
                return @{
                    Command = $c
                    Version = $testOut.ToString().Trim()
                }
            }
        } catch {
            # Candidate failed, continue to next
        }
    }
    return $null
}

Show-Header

# Step 1: Detect Python
$pythonInfo = $null
while (-not $pythonInfo) {
    Write-Host "[1/4] Checking Python installation..." -ForegroundColor Yellow
    $pythonInfo = Find-Python

    if (-not $pythonInfo) {
        Write-Host ""
        Write-Host "========================================================" -ForegroundColor Red
        Write-Host "  [ERROR] PYTHON IS NOT INSTALLED ON THIS COMPUTER!" -ForegroundColor Red
        Write-Host "========================================================" -ForegroundColor Red
        Write-Host ""
        Write-Host "To run this bot, you must install Python (version 3.10, 3.11, or newer)." -ForegroundColor White
        Write-Host ""
        Write-Host "Steps to install:" -ForegroundColor Yellow
        Write-Host "  1. Download Python from the official site:" -ForegroundColor White
        Write-Host "     https://www.python.org/downloads/" -ForegroundColor Cyan
        Write-Host "  2. Run the downloaded installer." -ForegroundColor White
        Write-Host "  3. IMPORTANT: On the first screen of the installer, check the box:" -ForegroundColor Yellow
        Write-Host "     [X] 'Add python.exe to PATH'  (at the bottom)" -ForegroundColor Green
        Write-Host "  4. Click 'Install Now'." -ForegroundColor White
        Write-Host ""
        
        Write-Host "Opening download page in your browser..." -ForegroundColor Gray
        try { Start-Process "https://www.python.org/downloads/" } catch {}

        Write-Host ""
        Write-Host "After installation is finished, press Enter to re-check." -ForegroundColor Yellow
        $resp = Read-Host "Press Enter to re-check Python (or Ctrl+C to exit)"
        Show-Header
    }
}

Write-Host "[1/4] Python found: $($pythonInfo.Version) ($($pythonInfo.Command))" -ForegroundColor Green

# Step 2: Check .env and Token
Write-Host ""
Write-Host "[2/4] Checking configuration (.env)..." -ForegroundColor Yellow

if (-not (Test-Path ".env")) {
    if (Test-Path ".env.example") {
        Copy-Item ".env.example" ".env"
        Write-Host "  [+] Created .env file from .env.example" -ForegroundColor Green
    }
}

$hasValidToken = $false
while (-not $hasValidToken) {
    if (Test-Path ".env") {
        $envContent = Get-Content ".env" -Raw
        if ($envContent -match "BOT_TOKEN=([0-9]{8,12}:[a-zA-Z0-9_-]{30,})") {
            $hasValidToken = $true
            Write-Host "[2/4] Valid BOT_TOKEN found in .env!" -ForegroundColor Green
            break
        }
    }

    Write-Host ""
    Write-Host "========================================================" -ForegroundColor Yellow
    Write-Host "  [ATTENTION] TELEGRAM BOT TOKEN REQUIRED!" -ForegroundColor Yellow
    Write-Host "========================================================" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "1. Open Telegram and message @BotFather (https://t.me/BotFather)" -ForegroundColor White
    Write-Host "2. Send /newbot and follow instructions to get your API Token." -ForegroundColor White
    Write-Host "3. Paste your token into the .env file." -ForegroundColor White
    Write-Host ""
    Write-Host "Opening .env in Notepad now..." -ForegroundColor Cyan
    try { Start-Process notepad.exe ".env" } catch {}
    Write-Host ""
    Read-Host "After you save your token in .env (Ctrl+S), press Enter to continue"
}

# Step 3: Setup Virtual Environment (venv)
Write-Host ""
Write-Host "[3/4] Checking virtual environment (venv)..." -ForegroundColor Yellow

$venvPython = "$ScriptDir\venv\Scripts\python.exe"

if (-not (Test-Path $venvPython)) {
    Write-Host "  [*] Creating venv (this takes a few seconds)..." -ForegroundColor Cyan
    & $pythonInfo.Command -m venv "$ScriptDir\venv"
    if (-not (Test-Path $venvPython)) {
        Write-Host "  [ERROR] Failed to create virtual environment!" -ForegroundColor Red
        Read-Host "Press Enter to exit..."
        exit 1
    }
    Write-Host "  [+] Virtual environment created successfully!" -ForegroundColor Green
} else {
    Write-Host "  [+] Virtual environment exists." -ForegroundColor Green
}

# Step 4: Install Dependencies
Write-Host ""
Write-Host "[4/4] Checking dependencies (pyTelegramBotAPI, python-dotenv)..." -ForegroundColor Yellow
& $venvPython -m pip install -r requirements.txt --quiet
if ($LASTEXITCODE -ne 0) {
    Write-Host "  [*] Retrying package installation with verbose output..." -ForegroundColor Yellow
    & $venvPython -m pip install -r requirements.txt
}

# Verify import
$importCheck = & $venvPython -c "import telebot, dotenv; print('READY')" 2>&1
if ($importCheck -notmatch "READY") {
    Write-Host "  [ERROR] Failed to import telebot! Output: $importCheck" -ForegroundColor Red
    Read-Host "Press Enter to exit..."
    exit 1
}
Write-Host "  [+] Dependencies ready!" -ForegroundColor Green

# Step 5: Run Bot with Auto-Restart Loop
Write-Host ""
Write-Host "========================================================" -ForegroundColor Green
Write-Host "       TELEGRAM BOT IS RUNNING! Press Ctrl+C to stop." -ForegroundColor Green
Write-Host "========================================================" -ForegroundColor Green
Write-Host ""

while ($true) {
    & $venvPython bot.py
    $exitCode = $LASTEXITCODE
    Write-Host ""
    Write-Host "[WARNING] Bot process exited with code $exitCode." -ForegroundColor Yellow
    Write-Host "Restarting in 5 seconds... (Close this window to stop completely)" -ForegroundColor Gray
    Start-Sleep -Seconds 5
}
