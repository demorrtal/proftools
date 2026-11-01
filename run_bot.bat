@echo off
chcp 65001 >nul 2>nul
cd /d "%~dp0"
title Telegram Task Bot

echo ========================================================
echo           Telegram Task Bot Launcher
echo ========================================================
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_bot.ps1"
set PS_EXIT=%errorlevel%

echo.
echo ========================================================
echo The program has stopped.
echo ========================================================
echo.
pause
