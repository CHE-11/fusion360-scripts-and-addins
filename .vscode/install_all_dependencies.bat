@echo off
setlocal EnableExtensions

set "ROOT=%~dp0.."

for %%P in (
  CONstrainer
  FileExplorer
  ProParams
) do (
  echo.
  if exist "%ROOT%\add-ins\%%P\client\package.json" (
    echo Installing dependencies for %%P...
    call "%ROOT%\add-ins\%%P\scripts\install_dependencies.bat"
    if errorlevel 1 (
      echo Failed to install dependencies for %%P.
      exit /b 1
    )
  ) else (
    echo Skipping %%P: no client package to install.
  )
)

echo.
echo All dependencies installed.
endlocal
