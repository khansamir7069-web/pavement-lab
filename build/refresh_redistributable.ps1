$ErrorActionPreference = "Stop"
$src = "E:\myclaud project\1\pavement_lab\dist\PavementLab"
$zip = "E:\myclaud project\1\PavementLab-Windows.zip"
$desktop = [Environment]::GetFolderPath('Desktop')
$shortcut_path = Join-Path $desktop "Pavement Lab.lnk"

if (-not (Test-Path "$src\PavementLab.exe")) {
    throw "PavementLab.exe not found at $src — run a rebuild first."
}

if (Test-Path $zip) { Remove-Item $zip -Force }
Compress-Archive -Path $src -DestinationPath $zip -CompressionLevel Optimal
$zip_size = [math]::Round((Get-Item $zip).Length / 1MB, 1)
Write-Output "Zip: $zip ($zip_size MB)"

$WshShell = New-Object -ComObject WScript.Shell
$shortcut = $WshShell.CreateShortcut($shortcut_path)
$shortcut.TargetPath = "$src\PavementLab.exe"
$shortcut.WorkingDirectory = $src
$shortcut.Description = "Pavement Lab — Marshall Mix Design"
$shortcut.Save()
Write-Output "Shortcut: $shortcut_path"

$exe_size = [math]::Round((Get-Item "$src\PavementLab.exe").Length / 1MB, 1)
$bundle_size = [math]::Round(((Get-ChildItem $src -Recurse | Measure-Object -Property Length -Sum).Sum) / 1MB, 0)
Write-Output "EXE: $src\PavementLab.exe ($exe_size MB)"
Write-Output "Bundle: $bundle_size MB"
