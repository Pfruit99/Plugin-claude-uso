# Crea un acceso directo en Inicio para abrir el widget con Windows, sin consola.
$dir = $PSScriptRoot
$pyw = (Get-Command pythonw -ErrorAction Stop).Source
$lnk = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup\ClaudeWidget.lnk"
$s = (New-Object -ComObject WScript.Shell).CreateShortcut($lnk)
$s.TargetPath = $pyw
$s.Arguments = "`"$dir\widget.pyw`""
$s.WorkingDirectory = $dir
$s.WindowStyle = 7
$s.Save()
Write-Host "Acceso directo creado: $lnk"
