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

# Сброс кнопки меню в Telegram API на стандартное меню команд
try {
    $envFile = Join-Path $ScriptDir ".env"
    if (Test-Path $envFile) {
        $tokenMatch = Select-String -Path $envFile -Pattern "^BOT_TOKEN=(.+)"
        if ($tokenMatch) {
            $botTok = $tokenMatch.Matches[0].Groups[1].Value.Trim().Trim('"').Trim("'")
            if ($botTok -and $botTok -notmatch "1234567890") {
                $body = '{"menu_button":{"type":"commands"}}'
                $res = Invoke-RestMethod -Uri "https://api.telegram.org/bot$botTok/setChatMenuButton" -Method Post -ContentType "application/json" -Body $body -ErrorAction SilentlyContinue
                if ($res.ok) {
                    Write-Host "[OK] Knopka 'Prilozhenie' sbroshena v Telegram API na standartnoe 'Menyu'!" -ForegroundColor Green
                }
            }
        }
    }
} catch {}

# Сохранение ветки miniapp-version перед откатом
& $GitCmd branch miniapp-version 2>$null

# Очистка корня от дубликатов файлов Mini App (они сохранены в miniapp_backup/)
$miniappFiles = @("api.py", "run.py", "setup_nginx.sh", "nginx_proftools.conf")
foreach ($mf in $miniappFiles) {
    $src = Join-Path $ScriptDir $mf
    $bak = Join-Path $ScriptDir "miniapp_backup\$mf"
    if ((Test-Path $src) -and (Test-Path $bak)) {
        Remove-Item $src -Force -ErrorAction SilentlyContinue
    }
}
$webappDir = Join-Path $ScriptDir "webapp"
$webappBak = Join-Path $ScriptDir "miniapp_backup\webapp"
if ((Test-Path $webappDir) -and (Test-Path $webappBak)) {
    Remove-Item $webappDir -Recurse -Force -ErrorAction SilentlyContinue
}

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
$defaultMsg = "Save miniapp_backup and restore classic Telegram bot with topics"
Write-Host "Vvedite opisanie kommita (ili nazhmite Enter dlya '$defaultMsg'):" -ForegroundColor Gray
$userMsg = Read-Host "> "
if ([string]::IsNullOrWhiteSpace($userMsg)) {
    $commitMsg = $defaultMsg
} else {
    $commitMsg = $userMsg.Trim()
}

& $GitCmd add -A .
& $GitCmd commit -m "$commitMsg"

# 5. Push на GitHub
Write-Host ""
Write-Host "[4/4] Otpravka na GitHub: $RepoUrl ..." -ForegroundColor Yellow
& $GitCmd branch -M main
& $GitCmd push -u origin main
& $GitCmd push origin miniapp-version 2>$null

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "========================================================" -ForegroundColor Green
    Write-Host "[USPEKH] Vse fayly uspeshno vygruzheny na GitHub!" -ForegroundColor Green
    Write-Host "https://github.com/demorrtal/proftools" -ForegroundColor Cyan
    Write-Host "========================================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "Na servere Ubuntu obnovite bota komandoy:" -ForegroundColor Gray
    Write-Host "  cd /opt/telegram_bot && git fetch origin && git reset --hard origin/main && sudo systemctl restart telegram-bot" -ForegroundColor White
} else {
    Write-Host ""
    Write-Host "========================================================" -ForegroundColor Red
    Write-Host "[VNIMANIE] Oshibka pri otpravke na GitHub." -ForegroundColor Red
    Write-Host "========================================================" -ForegroundColor Red
    Write-Host "Vozmozhno, trebuetsya voyti v GitHub (Sign in with browser)." -ForegroundColor Yellow
}

Write-Host ""
Read-Host "Nazhmite Enter dlya vykhoda..."
