' Silent entry point for cfo-helper on Windows.
' Detects whether the venv is set up; if not, runs the visible
' bootstrap in a console window. Once setup is done (or on every
' subsequent launch) it kicks off pythonw.exe with no console at all.

Option Explicit

Dim sh, fso, repo
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

' Walk out of dist\windows\ to repo root
repo = fso.GetParentFolderName(fso.GetParentFolderName(WScript.ScriptFullName))
sh.CurrentDirectory = repo

If Not fso.FolderExists(repo & "\logs") Then
    fso.CreateFolder(repo & "\logs")
End If

If Not fso.FileExists(repo & "\.venv\Scripts\pythonw.exe") Then
    ' First-time setup: visible console so user sees install progress.
    sh.Run "cmd /c """ & repo & "\dist\windows\bootstrap.bat""", 1, True
End If

' Silent relaunch (window style 0 = hidden, do not wait).
sh.Run """" & repo & "\.venv\Scripts\pythonw.exe"" """ & repo & "\launcher.py""", 0, False
