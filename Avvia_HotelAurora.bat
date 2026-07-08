@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
title HotelAurora - avvio

rem --- trova un interprete Python sul PATH (per controllare/installare le
rem     dipendenze: visibile in questa console, cosi un errore si vede) -------
set "PY="
where py >nul 2>nul
if not errorlevel 1 set "PY=py -3"
if not defined PY (
    where python >nul 2>nul
    if not errorlevel 1 set "PY=python"
)
if not defined PY (
    echo [HotelAurora] Python non trovato sul PATH.
    echo Installa Python 3 da https://python.org spuntando
    echo "Add python.exe to PATH" durante l'installazione, poi riprova.
    pause
    exit /b 1
)

rem --- installa Flask se manca (causa piu comune di "non parte su un altro
rem     computer": senza questo controllo pythonw fallisce in silenzio, senza
rem     nessuna finestra, e il browser apre su una porta morta) --------------
%PY% -c "import flask" >nul 2>nul
if errorlevel 1 (
    echo [HotelAurora] Prima esecuzione su questo computer: installo le
    echo dipendenze mancanti...
    %PY% -m pip install --quiet -r requirements.txt
    if errorlevel 1 (
        echo [HotelAurora] Installazione dipendenze fallita. Controlla la
        echo connessione a internet, poi riprova. In alternativa esegui a mano:
        echo   %PY% -m pip install -r requirements.txt
        pause
        exit /b 1
    )
)

rem --- avvia il server in una finestra minimizzata (pythonw se disponibile,
rem     per non far lampeggiare una console; altrimenti l'interprete trovato
rem     sopra) -------------------------------------------------------------
where pythonw >nul 2>nul
if not errorlevel 1 (
    start "HotelAurora server" /min pythonw main.py
) else (
    start "HotelAurora server" /min %PY% main.py
)

rem --- aspetta che il server risponda DAVVERO (fino a 20s) prima di aprire
rem     il browser, invece di un'attesa fissa alla cieca -----------------
set "READY="
for /l %%i in (1,1,20) do (
    powershell -NoProfile -Command ^
      "try { (New-Object Net.Sockets.TcpClient('127.0.0.1',5000)).Close(); exit 0 } catch { exit 1 }" >nul 2>nul
    if not errorlevel 1 (
        set "READY=1"
        goto :ready
    )
    timeout /t 1 /nobreak >nul
)
:ready
if not defined READY (
    echo [HotelAurora] Il server non risponde dopo 20 secondi.
    echo Avvialo a mano per vedere l'errore:   %PY% main.py
    pause
    exit /b 1
)

start "" http://127.0.0.1:5000/
