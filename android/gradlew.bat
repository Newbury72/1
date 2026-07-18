@echo off
REM Gradle start up script for Windows (cmd)
REM Placeholder wrapper script that expects gradle-wrapper.jar in gradle\wrapper

setlocal
set APP_HOME=%~dp0
set CLASSPATH=%APP_HOME%gradle\wrapper\gradle-wrapper.jar

if not exist "%CLASSPATH%" (
  echo gradle-wrapper.jar not found in %APP_HOME%gradle\wrapper.
  echo Run "gradle wrapper" on a machine with Gradle to generate the wrapper jar, or open the project in Android Studio to create the wrapper.
  exit /b 1
)

@echo off
REM Self-contained Windows wrapper: download Gradle 8.4 and run it
setlocal enabledelayedexpansion
set APP_HOME=%~dp0
set GRADLE_VERSION=8.4
set DIST_DIR=%APP_HOME%gradle\wrapper\gradle-%GRADLE_VERSION%
set ZIP=%APP_HOME%gradle\wrapper\gradle-%GRADLE_VERSION%-all.zip
set DIST_URL=https://services.gradle.org/distributions/gradle-%GRADLE_VERSION%-all.zip

if not exist "%DIST_DIR%" (
  echo Gradle %GRADLE_VERSION% not found, downloading...
  if not exist "%APP_HOME%gradle\wrapper" mkdir "%APP_HOME%gradle\wrapper"
  where curl >nul 2>&1
  if %ERRORLEVEL%==0 (
    curl -L -o "%ZIP%" "%DIST_URL%"
  ) else (
    where wget >nul 2>&1
    if %ERRORLEVEL%==0 (
      wget -O "%ZIP%" "%DIST_URL%"
    ) else (
      echo Neither curl nor wget found. Install one or generate the wrapper on another machine.
      exit /b 1
    )
  )
  powershell -Command "Expand-Archive -Force -LiteralPath '%ZIP%' -DestinationPath '%APP_HOME%gradle\\wrapper'"
)

"%DIST_DIR%\bin\gradle.bat" %*
