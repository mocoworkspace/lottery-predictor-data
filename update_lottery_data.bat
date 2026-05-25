@echo off
chcp 65001 > nul
echo ============================================
echo  宝くじデータ更新ツール
echo ============================================
echo.
echo ブラウザで以下の3つのCSVファイルをダウンロードしてください。
echo ダウンロード後、このウィンドウに戻って Enter を押してください。
echo.
echo [1] ロト6:
echo     https://www.mizuhobank.co.jp/retail/takarakuji/loto/loto6/csv/loto6.csv
echo.
echo [2] ロト7:
echo     https://www.mizuhobank.co.jp/retail/takarakuji/loto/loto7/csv/loto7.csv
echo.
echo [3] ミニロト:
echo     https://www.mizuhobank.co.jp/retail/takarakuji/loto/miniloto/csv/miniloto.csv
echo.

REM ブラウザでCSVダウンロードページを開く
start "" "https://www.mizuhobank.co.jp/retail/takarakuji/loto/loto6/csv/loto6.csv"
timeout /t 2 /nobreak > nul
start "" "https://www.mizuhobank.co.jp/retail/takarakuji/loto/loto7/csv/loto7.csv"
timeout /t 2 /nobreak > nul
start "" "https://www.mizuhobank.co.jp/retail/takarakuji/loto/miniloto/csv/miniloto.csv"

echo.
echo ブラウザが開きました。3つのCSVファイルがダウンロードされたら、
echo ダウンロードフォルダから csv\ フォルダにコピーしてください:
echo.
echo   ダウンロード先: %~dp0csv\
echo.
echo コピー完了後、Enter を押してデータ変換を開始します...
pause > nul

REM csv/ フォルダに必要なファイルがあるか確認
set MISSING=0
if not exist "%~dp0csv\loto6.csv" (
    echo [ERROR] csv\loto6.csv が見つかりません
    set MISSING=1
)
if not exist "%~dp0csv\loto7.csv" (
    echo [ERROR] csv\loto7.csv が見つかりません
    set MISSING=1
)
if not exist "%~dp0csv\miniloto.csv" (
    echo [ERROR] csv\miniloto.csv が見つかりません
    set MISSING=1
)

if "%MISSING%"=="1" (
    echo.
    echo CSVファイルを csv\ フォルダにコピーしてから再実行してください。
    pause
    exit /b 1
)

echo.
echo CSVファイルを検出しました。データ変換を開始します...
echo.

REM lottery.json を生成
cd /d "%~dp0"
python scripts/fetch_lottery.py

if errorlevel 1 (
    echo [ERROR] データ変換に失敗しました。
    pause
    exit /b 1
)

echo.
echo GitHub にプッシュしますか？ (y/n)
set /p PUSH_CONFIRM=
if /i "%PUSH_CONFIRM%"=="y" (
    git add lottery.json
    git diff --staged --quiet || git commit -m "Update lottery data %date%"
    git push
    echo.
    echo GitHub Pages への反映には数分かかります。
) else (
    echo プッシュをスキップしました。手動で git push してください。
)

echo.
echo 完了しました！
pause
