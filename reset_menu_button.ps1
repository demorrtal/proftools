$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $ScriptDir) { $ScriptDir = Get-Location }

Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "    SBROS KNOPKI 'PRILOZHENIE' V TELEGRAM BOT API       " -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan

$envFile = Join-Path $ScriptDir ".env"
if (-not (Test-Path $envFile)) {
    Write-Host "[ERROR] Fayl .env ne nayden!" -ForegroundColor Red
    Read-Host "Nazhmite Enter dlya vykhoda..."
    exit 1
}

$tokenMatch = Select-String -Path $envFile -Pattern "^BOT_TOKEN=(.+)"
if (-not $tokenMatch) {
    Write-Host "[ERROR] BOT_TOKEN ne nayden v .env!" -ForegroundColor Red
    Read-Host "Nazhmite Enter dlya vykhoda..."
    exit 1
}

$botTok = $tokenMatch.Matches[0].Groups[1].Value.Trim().Trim('"').Trim("'")

Write-Host "Otpravka zaprosa v Telegram Bot API..." -ForegroundColor Yellow
try {
    $body = '{"menu_button":{"type":"commands"}}'
    $res = Invoke-RestMethod -Uri "https://api.telegram.org/bot$botTok/setChatMenuButton" -Method Post -ContentType "application/json" -Body $body
    if ($res.ok) {
        Write-Host ""
        Write-Host "========================================================" -ForegroundColor Green
        Write-Host "[USPEKH] Knopka 'Prilozhenie' uspeshno udalena iz bota!" -ForegroundColor Green
        Write-Host "Vmesto nee teper standartnaya knopka 'Menyu' (komandy)." -ForegroundColor Green
        Write-Host "========================================================" -ForegroundColor Green
        Write-Host ""
        Write-Host "Sovet: Esli v prilozhenii Telegram knopka eshche vidna," -ForegroundColor Gray
        Write-Host "prosto zakroyte i otkroyte chat s botom ili otpravte /start." -ForegroundColor Gray
    } else {
        Write-Host "[ERROR] Telegram vernul oshibku: $($res.description)" -ForegroundColor Red
    }
} catch {
    Write-Host "[ERROR] Oshibka zaprosa k Telegram API: $_" -ForegroundColor Red
}

Write-Host ""
Read-Host "Nazhmite Enter dlya vykhoda..."
