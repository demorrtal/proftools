<#
.SYNOPSIS
    Автоматическая отправка обновлений бота с Windows на сервер Ubuntu
#>
$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $ScriptDir) { $ScriptDir = Get-Location }
Set-Location $ScriptDir

$ConfigFile = Join-Path $ScriptDir "deploy_config.txt"

Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "        АВТОМАТИЧЕСКИЙ ДЕПЛОЙ / ОБНОВЛЕНИЕ БОТА        " -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host ""

# Чтение или запрос настроек сервера
$ServerIP = ""
$ServerUser = "root"
$RemoteDir = "/opt/telegram_bot"

if (Test-Path $ConfigFile) {
    Get-Content $ConfigFile | ForEach-Object {
        $line = $_.Trim()
        if ($line.StartsWith("SERVER_IP=")) { $ServerIP = $line.Substring(10).Trim() }
        if ($line.StartsWith("SERVER_USER=")) { $ServerUser = $line.Substring(12).Trim() }
        if ($line.StartsWith("REMOTE_DIR=")) { $RemoteDir = $line.Substring(11).Trim() }
    }
}

if (-not $ServerIP) {
    Write-Host "[?] Первый запуск: укажите параметры вашего сервера Ubuntu" -ForegroundColor Yellow
    $ServerIP = Read-Host "👉 Введите IP-адрес сервера"
    $inputUser = Read-Host "👉 Введите пользователя (нажмите Enter для 'root')"
    if ($inputUser) { $ServerUser = $inputUser }
    
    $inputDir = Read-Host "👉 Введите путь к боту на сервере (Enter для '/opt/telegram_bot')"
    if ($inputDir) { $RemoteDir = $inputDir }

    @"
SERVER_IP=$ServerIP
SERVER_USER=$ServerUser
REMOTE_DIR=$RemoteDir
"@ | Set-Content -Path $ConfigFile -Encoding UTF8
    Write-Host "✅ Настройки сохранены в deploy_config.txt" -ForegroundColor Green
    Write-Host ""
}

Write-Host "[1/3] Сервер назначения: $ServerUser@$ServerIP:$RemoteDir" -ForegroundColor Gray

# Список файлов с исходным кодом (БЕЗ venv, без базы данных и без логов)
$FilesToUpload = @(
    "bot.py",
    "run.py",
    "api.py",
    "config.py",
    "database.py",
    "keyboards.py",
    "scheduler.py",
    "requirements.txt",
    "manage.sh",
    "setup_nginx.sh",
    "nginx_proftools.conf"
)

$ValidFiles = @()
foreach ($f in $FilesToUpload) {
    $full = Join-Path $ScriptDir $f
    if (Test-Path $full) {
        $ValidFiles += $full
    }
}

Write-Host "[2/3] Отправка обновленных файлов на сервер через SCP..." -ForegroundColor Yellow
Write-Host "  Файлы: $($FilesToUpload -join ', '), webapp/" -ForegroundColor DarkGray
Write-Host "  (База данных bot_database.db и .env НЕ перезаписываются - ваши данные в безопасности!)" -ForegroundColor DarkCyan

$scpTarget = "${ServerUser}@${ServerIP}:${RemoteDir}/"
& scp.exe $ValidFiles $scpTarget

$webappDir = Join-Path $ScriptDir "webapp"
if (Test-Path $webappDir) {
    & scp.exe -r $webappDir $scpTarget
}
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Ошибка при передаче файлов по SCP!" -ForegroundColor Red
    pause
    exit 1
}

Write-Host "[3/3] Синхронизация и перезапуск службы telegram-bot на сервере..." -ForegroundColor Yellow
$remoteCommand = "cd ${RemoteDir} && (git pull origin main 2>/dev/null || true) && sudo systemctl restart telegram-bot && sleep 1 && sudo systemctl is-active telegram-bot"
& ssh.exe "${ServerUser}@${ServerIP}" $remoteCommand

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "========================================================" -ForegroundColor Green
    Write-Host "🎉 УСПЕШНО! Файлы обновлены, бот перезапущен и работает!" -ForegroundColor Green
    Write-Host "========================================================" -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "⚠️ Файлы загружены, но при перезапуске службы возникла ошибка." -ForegroundColor Yellow
    Write-Host "Проверьте логи командой: ssh $ServerUser@$ServerIP 'sudo journalctl -u telegram-bot -n 20'" -ForegroundColor Gray
}

Write-Host ""
Write-Host "Для повторного обновления просто запустите этот скрипт еще раз." -ForegroundColor Gray
