@echo off
chcp 65001 >nul 2>&1
title DeepSeek Proxy
echo ========================================
echo    DeepSeek Proxy Smart Launcher
echo ========================================
echo.
echo [INFO] Auto-injecting proxy config...
echo [INFO] Press Ctrl+C or close window to restore config
echo.

py start_proxy_with_config.py

if errorlevel 1 (
    python start_proxy_with_config.py
)

echo.
echo [INFO] Proxy stopped, config restored.
pause
