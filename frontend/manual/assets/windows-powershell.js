// The same CMD routines are embedded in the installer and generated config / restore scripts.
// Probe before any mutation; never retry an already-started configuration with another engine.
export const windowsPowerShellDiscovery = String.raw`
:HUIMA_FIND_PS
set "HUIMA_PS="
if exist "%SystemRoot%\Sysnative\WindowsPowerShell\v1.0\powershell.exe" call :HUIMA_TRY_PS "%SystemRoot%\Sysnative\WindowsPowerShell\v1.0\powershell.exe"
if not defined HUIMA_PS if exist "%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" call :HUIMA_TRY_PS "%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
if not defined HUIMA_PS if exist "%ProgramW6432%\PowerShell\7\pwsh.exe" call :HUIMA_TRY_PS "%ProgramW6432%\PowerShell\7\pwsh.exe"
if not defined HUIMA_PS if exist "%ProgramFiles%\PowerShell\7\pwsh.exe" call :HUIMA_TRY_PS "%ProgramFiles%\PowerShell\7\pwsh.exe"
if not defined HUIMA_PS for /f "delims=" %%P in ('"%SystemRoot%\System32\where.exe" powershell.exe 2^>nul') do call :HUIMA_TRY_PS "%%P"
if not defined HUIMA_PS for /f "delims=" %%P in ('"%SystemRoot%\System32\where.exe" pwsh.exe 2^>nul') do call :HUIMA_TRY_PS "%%P"
exit /b

:HUIMA_TRY_PS
if defined HUIMA_PS exit /b
"%~1" -NoLogo -NoProfile -Command "if ($PSVersionTable.PSVersion -lt [version]'5.1') { exit 1 }; ConvertTo-Json @{ok=$true} | Out-Null; exit 0" >nul 2>&1
if not errorlevel 1 set "HUIMA_PS=%~1"
exit /b
`;
