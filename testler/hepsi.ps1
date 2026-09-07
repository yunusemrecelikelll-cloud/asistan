# Tum backend testlerini calistirir.
#   .\testler\hepsi.ps1
$kok = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$py = Join-Path $kok '.venv\Scripts\python.exe'
$env:PYTHONIOENCODING = 'utf-8'
$basarisiz = 0
Get-ChildItem (Join-Path $kok 'testler\test_*.py') | ForEach-Object {
    Write-Host "`n=== $($_.Name) ===" -ForegroundColor Cyan
    & $py $_.FullName
    if ($LASTEXITCODE -ne 0) { $basarisiz++ }
}
Write-Host ""
if ($basarisiz -eq 0) {
    Write-Host "Tum test dosyalari gecti." -ForegroundColor Green
} else {
    Write-Host "$basarisiz test dosyasi basarisiz." -ForegroundColor Red
}
exit $basarisiz
