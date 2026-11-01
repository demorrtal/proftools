@echo off
chcp 65001 >nul 2>nul
cd /d "%~dp0"
title Telegram Bot Deployer

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0update_server.ps1"

echo.
pause
