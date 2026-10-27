@echo off
setlocal

set "ROOT=%~dp0.."

for %%P in (
  CONstrainer
  FileExplorer
  ProParams
) do (
  echo.
  if exist "%ROOT%\add-ins\%%P\client\package.json" (
    echo Building %%P...
    call "%ROOT%\add-ins\%%P\scripts\build_add_in.bat"
    if errorlevel 1 (
      echo Failed to build add-in for %%P.
      exit /b 1
    )
  ) else (
    echo Skipping %%P: Python only, nothing to build.
  )
)

echo.
echo All add-ins built.
endlocal
