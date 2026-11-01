@echo off
chcp 65001 >nul 2>nul
cd /d "%~dp0"
title Push to GitHub - demorrtal/proftools

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0push_to_github.ps1"

echo.
pause
