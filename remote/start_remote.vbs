' [deskpet] Starts the phone remote (remote_server.py) with no window. Put in the Startup folder by install_remote.ps1.
Option Explicit
Dim sh, fso, here, py
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
here = fso.GetParentFolderName(WScript.ScriptFullName)
py = "pythonw.exe"
If Not fso.FileExists(py) Then py = "pythonw.exe"
sh.Run """" & py & """ """ & here & "\remote_server.py""", 0, False
