@echo off
rem KnoxMap one-time setup. Safe to run again.
setlocal
cd /d "%~dp0"
rem UTF-8 for every file Python reads and writes, whatever the PC's code page.
rem On a Korean or Japanese Windows the default one cannot hold all of KnoxMap's text.
set PYTHONUTF8=1

rem Prefer the py launcher; "python" on a fresh Windows can be the Microsoft
rem Store stub, which opens the Store instead of running anything. Either way
rem the version check below is what decides.
rem
rem The check is 3.10 or newer AND 64-bit: a 32-bit Python can only use about
rem 2 GB however much memory the PC has, and a town-sized map needs more than
rem that - it dies halfway through with "MemoryError". A 32-bit one is kept as
rem PY32 in case this really is a 32-bit Windows, where it is all there is.
set PY=
set PY32=
if exist ".python\tools\python.exe" set PY=".python\tools\python.exe"
if not defined PY where py >nul 2>nul && py -3 -c "import sys; sys.exit(sys.version_info < (3, 10) or sys.maxsize <= 2**32)" >nul 2>nul && set PY=py -3
if not defined PY python -c "import sys; sys.exit(sys.version_info < (3, 10) or sys.maxsize <= 2**32)" >nul 2>nul && set PY=python
if not defined PY where py >nul 2>nul && py -3 -c "import sys; sys.exit(sys.version_info < (3, 10))" >nul 2>nul && set PY32=py -3
if not defined PY if not defined PY32 python -c "import sys; sys.exit(sys.version_info < (3, 10))" >nul 2>nul && set PY32=python
if not defined PY call :portable_python || goto :fail

rem An environment built by a 32-bit Python stays 32-bit, so a copy set up
rem before this check is made again with the one found above.
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -c "import sys; sys.exit(sys.maxsize <= 2**32)" >nul 2>nul || call :rebuild_venv
)

if not exist ".venv\Scripts\python.exe" (
  echo Creating the Python environment...
  %PY% -m venv .venv || goto :fail
)
echo Installing Python packages...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt || goto :fail

".venv\Scripts\python.exe" knoxmap_setup.py || goto :fail
echo.
if not "%KNOXMAP_NO_PAUSE%"=="1" pause
exit /b 0

:fail
echo.
echo Setup stopped with an error - see the messages above.
if not "%KNOXMAP_NO_PAUSE%"=="1" pause
exit /b 1

:rebuild_venv
rem Only worth doing when what we have now is 64-bit; on a 32-bit Windows the
rem environment is as good as it gets.
%PY% -c "import sys; sys.exit(sys.maxsize <= 2**32)" >nul 2>nul || exit /b 0
echo The Python environment is 32-bit, which runs out of memory on a big map.
echo Making it again with 64-bit Python...
rmdir /s /q ".venv"
exit /b 0

:portable_python
echo 64-bit Python 3.10 or newer was not found - downloading a private copy (about 14 MB)...

rem Download using native Windows curl
curl.exe -sL "https://api.nuget.org/v3-flatcontainer/python/3.13.7/python.3.13.7.nupkg" -o ".python.zip" || goto :no_portable

rem Verify the hash using native certutil
set "EXPECTED_HASH=e74272a824e23702dfb5f3e11c3660ceabac7487e3366d4551391db5cd762853"
set "ACTUAL_HASH="
for /f "skip=1 tokens=* usebackq" %%H in (`certutil -hashfile ".python.zip" SHA256`) do (
    if not defined ACTUAL_HASH set "ACTUAL_HASH=%%H"
)
rem Remove spaces from certutil output
set "ACTUAL_HASH=%ACTUAL_HASH: =%"

if /I not "%ACTUAL_HASH%"=="%EXPECTED_HASH%" (
    echo The Python download did not match its fingerprint.
    del ".python.zip"
    goto :no_portable
)

rem Extract using native tar
if exist ".python" rmdir /s /q ".python"
mkdir ".python"
tar.exe -xf ".python.zip" -C ".python" || goto :no_portable
del ".python.zip"

if not exist ".python\tools\python.exe" goto :no_portable
".python\tools\python.exe" -c "import sys; sys.exit(sys.maxsize <= 2**32)" >nul 2>nul || goto :no_portable
set PY=".python\tools\python.exe"
exit /b 0

:no_portable
rem It could not be downloaded, or it will not run here (a 32-bit Windows).
if defined PY32 (
  echo Carrying on with the 32-bit Python on this PC. Maps of more than a few
  echo square kilometres may run out of memory.
  set PY=%PY32%
  exit /b 0
)
exit /b 1
