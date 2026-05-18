@echo off
chcp 65001 >nul
title DeepSeek Proxy 智能启动工具
echo ========================================
echo    DeepSeek Proxy 智能配置启动工具
echo ========================================
echo.
echo [提示] 启动时将自动注入代理配置
echo [提示] 关闭窗口或 Ctrl+C 将自动还原配置
echo.

:: 尝试使用 py 启动 (Windows Python Launcher), 如果失败则尝试 python
py start_proxy_with_config.py || python start_proxy_with_config.py

echo.
echo 服务器已停止，配置已还原。
pause
