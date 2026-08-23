@echo off
setlocal EnableExtensions
chcp 65001 >nul
title Steel-Compass 一键启动

pushd "%~dp0" >nul 2>&1
if errorlevel 1 goto :fail

if not exist "docker-compose.yml" (
    echo [错误] 未找到 docker-compose.yml，请从项目根目录运行此脚本。
    goto :fail
)

where docker >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 Docker 命令，请先安装 Docker Desktop 并确保 docker 在 PATH 中。
    goto :fail
)

docker compose version >nul 2>&1
if errorlevel 1 (
    echo [错误] 当前 Docker 不支持 docker compose，请升级 Docker Desktop。
    goto :fail
)

docker info >nul 2>&1
if errorlevel 1 (
    echo [提示] Docker 引擎尚未运行，正在尝试启动 Docker Desktop...
    set "DOCKER_DESKTOP=%ProgramFiles%\Docker\Docker\Docker Desktop.exe"
    if not exist "%DOCKER_DESKTOP%" set "DOCKER_DESKTOP=%ProgramFiles(x86)%\Docker\Docker\Docker Desktop.exe"
    if exist "%DOCKER_DESKTOP%" start "" "%DOCKER_DESKTOP%"
    call :wait_docker
    if errorlevel 1 (
        echo [错误] Docker 引擎未能在规定时间内启动，请确认 Docker Desktop 已正常运行。
        goto :fail
    )
)

if not exist ".env" (
    copy /y ".env.example" ".env" >nul
    if errorlevel 1 (
        echo [错误] 无法创建 .env 文件。
        goto :fail
    )
    echo [首次运行] 已根据 .env.example 创建 .env。
    echo [首次运行] 请填写 POSTGRES_PASSWORD 和 STEEL_COMPASS_BOOTSTRAP_ADMIN_PASSWORD 后重新运行本脚本。
    start "" notepad.exe "%CD%\.env"
    goto :first_run
)

findstr /i /c:"replace-with-" ".env" >nul
if not errorlevel 1 (
    echo [首次运行] .env 中仍有示例密码，请先替换后重新运行本脚本。
    start "" notepad.exe "%CD%\.env"
    goto :first_run
)

echo [1/3] 校验 Docker Compose 配置...
docker compose --env-file ".env" config --quiet
if errorlevel 1 (
    echo [错误] Compose 配置校验失败，请检查 .env 和 Docker Compose 错误信息。
    goto :fail
)

set "BUILD_ARGUMENT="
docker image inspect steel-compass-backend:latest steel-compass-frontend:latest >nul 2>&1
if errorlevel 1 set "BUILD_ARGUMENT=--build"

echo [2/3] 启动 Steel-Compass 容器...
if defined BUILD_ARGUMENT echo [提示] 本地镜像不存在，首次启动将自动构建镜像。
docker compose --env-file ".env" up -d %BUILD_ARGUMENT%
if errorlevel 1 (
    echo [错误] 容器启动失败，请查看上方输出或运行：
    echo        docker compose --env-file .env logs --tail 100 backend frontend caddy
    goto :fail
)

echo [3/3] 等待应用健康检查...
call :wait_health
if errorlevel 1 (
    echo [错误] 应用未在规定时间内通过健康检查，当前容器状态如下：
    docker compose --env-file ".env" ps
    goto :fail
)

docker compose --env-file ".env" ps
echo.
echo [完成] Steel-Compass 已启动： http://127.0.0.1/
start "" "http://127.0.0.1/"
popd
pause
exit /b 0

:wait_docker
for /l %%N in (1,1,30) do (
    docker info >nul 2>&1
    if not errorlevel 1 exit /b 0
    timeout /t 2 /nobreak >nul
)
exit /b 1

:wait_health
for /l %%N in (1,1,45) do (
    curl.exe --noproxy "*" --fail --silent --show-error --max-time 5 http://127.0.0.1/health >nul 2>&1
    if not errorlevel 1 exit /b 0
    timeout /t 2 /nobreak >nul
)
exit /b 1

:first_run
popd
pause
exit /b 2

:fail
popd >nul 2>&1
pause
exit /b 1
