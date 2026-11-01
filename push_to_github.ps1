# Telegram Bot Push to GitHub
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $ScriptDir) { $ScriptDir = Get-Location }
Set-Location $ScriptDir

$Host.UI.RawUI.WindowTitle = "Push to GitHub - demorrtal/proftools"

Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "       VYGRUZKA BOTA NA GITHUB (demorrtal/proftools)   " -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host ""

# 1. Поиск git.exe
$GitCmd = $null
$candidates = @(
    "C:\Program Files\Git\cmd\git.exe",
    "C:\Program Files\Git\bin\git.exe",
    "$env:LOCALAPPDATA\Programs\Git\cmd\git.exe",
    "git"
)

foreach ($c in $candidates) {
    if ($c.Contains("\")) {
        if (Test-Path $c) {
            $GitCmd = $c
            break
        }
    } else {
        try {
            $test = & $c --version 2>&1
            if ($test -match "git version") {
                $GitCmd = $c
                break
            }
        } catch {}
    }
}

if (-not $GitCmd) {
    Write-Host "[ERROR] Git ne nayden! Ustanovite Git s https://git-scm.com/" -ForegroundColor Red
    Write-Host ""
    Read-Host "Nazhmite Enter dlya vykhoda..."
    exit 1
}

Write-Host "[1/4] Git nayden: $GitCmd" -ForegroundColor Gray

# 2. Настройка remote
$RepoUrl = "https://github.com/demorrtal/proftools.git"
$currentRemote = & $GitCmd remote get-url origin 2>$null
if (-not $currentRemote) {
    & $GitCmd remote add origin $RepoUrl
} elseif ($currentRemote -ne $RepoUrl) {
    & $GitCmd remote set-url origin $RepoUrl
}

# 3. Проверка статуса
Write-Host ""
Write-Host "[2/4] Proverka izmeneniy v proekte..." -ForegroundColor Yellow
$status = & $GitCmd status -s
if (-not $status) {
    Write-Host "[INFO] Net novykh izmeneniy dlya otpravki." -ForegroundColor Green
    Write-Host ""
    $answer = Read-Host "Povtorit otpravku poslednego kommita na GitHub? (y/n) [n]"
    if ($answer -ne "y" -and $answer -ne "yes") {
        Write-Host "Gotovo." -ForegroundColor Gray
        Read-Host "Nazhmite Enter dlya vykhoda..."
        exit 0
    }
} else {
    Write-Host "Naydeny izmenennye fayly:" -ForegroundColor Cyan
    & $GitCmd status -s
}

# 4. Ввод сообщения для коммита
Write-Host ""
Write-Host "[3/4] Sozdanie kommita..." -ForegroundColor Yellow
$defaultMsg = "Update bot " + (Get-Date -Format "yyyy-MM-dd HH:mm")
Write-Host "Vvedite opisanie kommita (ili nazhmite Enter dlya '$defaultMsg'):" -ForegroundColor Gray
$userMsg = Read-Host "> "
if ([string]::IsNullOrWhiteSpace($userMsg)) {
    $commitMsg = $defaultMsg
} else {
    $commitMsg = $userMsg.Trim()
}

& $GitCmd add .
& $GitCmd commit -m "$commitMsg"

# 5. Push на GitHub
Write-Host ""
Write-Host "[4/4] Otpravka na GitHub: $RepoUrl ..." -ForegroundColor Yellow
& $GitCmd branch -M main
& $GitCmd push -u origin main

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "========================================================" -ForegroundColor Green
    Write-Host "[USPEKH] Vse fayly uspeshno vygruzheny na GitHub!" -ForegroundColor Green
    Write-Host "https://github.com/demorrtal/proftools" -ForegroundColor Cyan
    Write-Host "========================================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "Na servere Ubuntu obnovite bota komandoy:" -ForegroundColor Gray
    Write-Host "  ./manage.sh update" -ForegroundColor White
} else {
    Write-Host ""
    Write-Host "========================================================" -ForegroundColor Red
    Write-Host "[VNIMANIE] Oshibka pri otpravke na GitHub." -ForegroundColor Red
    Write-Host "========================================================" -ForegroundColor Red
    Write-Host "Vozmozhno, trebuetsya voyti v GitHub (Sign in with browser)." -ForegroundColor Yellow
}

Write-Host ""
Read-Host "Nazhmite Enter dlya vykhoda..."
