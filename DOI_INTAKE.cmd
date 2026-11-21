@echo off
setlocal
pushd "%~dp0" || exit /b 2
if defined SSA_DOI_PYTHON goto explicit_python
py -3 -m companions.doi_intake %*
goto finished
:explicit_python
"%SSA_DOI_PYTHON%" -m companions.doi_intake %*
:finished
set "DOI_EXIT=%ERRORLEVEL%"
popd
exit /b %DOI_EXIT%
