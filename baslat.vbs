' Konsol penceresi göstermeden Asistan'ı başlatır.
Set fso = CreateObject("Scripting.FileSystemObject")
kok = fso.GetParentFolderName(WScript.ScriptFullName)
Set sh = CreateObject("WScript.Shell")
sh.Run "powershell.exe -NoProfile -ExecutionPolicy Bypass -File """ & kok & "\baslat.ps1""", 0, False
