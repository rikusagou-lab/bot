@echo off
rem ------------------------------------------------------------
rem  Discord Bot 起動スクリプト(落ちても自動で再起動する)
rem  使い方: このファイルを bot.py と同じフォルダに置いてダブルクリック
rem ------------------------------------------------------------
cd /d %~dp0

:loop
echo [%date% %time%] Botを起動します...
python main.py

echo [%date% %time%] Botが停止しました。5秒後に再起動します...
timeout /t 5 /nobreak > nul
goto loop
