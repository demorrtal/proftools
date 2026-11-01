@echo off
chcp 65001 >nul 2>nul
cd /d "%~dp0"
title Reset Menu Button - Telegram Bot

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0reset_menu_button.ps1"

echo.
pause
