# -*- coding: utf-8 -*-
<#
打包脚本：生成无黑框单文件 exe。
用法（在项目根目录执行）:
    powershell -ExecutionPolicy Bypass -File build\build_exe.ps1
产物:
    dist\Capix.exe
说明:
    --onefile    单文件，便于分享
    --noconsole  无控制台黑框（GUI 程序）
    --icon       程序/文件图标（由 make_icon.py 从 jpeg 转来的 ico）
    --add-data   把 assets\icon.ico 与 assets\ui\*.png 打进包内，供运行时加载
#>
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root

$ico = Join-Path $root 'assets\icon.ico'
$uidir = Join-Path $root 'assets\ui'
$data = "$ico;assets"
$uidata = "$uidir;assets/ui"

Write-Host "==> 1/3 生成程序图标 assets\icon.ico"
py build\make_icon.py

Write-Host "==> 2/3 生成工具条图标 assets\ui"
py build\make_ui_icons.py

Write-Host "==> 3/3 PyInstaller 打包"
py -m PyInstaller --noconfirm --clean --onefile --noconsole `
  --name Capix `
  --icon $ico `
  --add-data $data `
  --add-data $uidata `
  --collect-submodules capix `
  --distpath dist --workpath build\_work --specpath build `
  app.py

Write-Host "==> 完成: $root\dist\Capix.exe"