@echo off
chcp 65001

echo ====================================================
echo   ArXiv EMRI Daily Digest 启动中...
echo   当前时间: %date% %time%
echo ====================================================

python "daily_paper.py"

if %ERRORLEVEL% equ 0 (
    echo.
    echo [成功] EMRI 论文筛选与邮件推送已完成。
) else (
    echo.
    echo [错误] 脚本运行出错，请检查 DeepSeek / SMTP 配置和网络。
)

echo.
echo 窗口将在 10 秒后自动关闭...
timeout /t 10
