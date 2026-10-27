; Initialize global variable
a = nil
; $env:Path += ";C:\Users\a1257241\AppData\Local\Microsoft\WinGet\Packages\OpenJS.NodeJS_Microsoft.Winget.Source_8wekyb3d8bbwe\node-v26.8.1-win-x64" to load claude inwindows
procedure( start_server()
  ; Always kill server before starting
  if( a == t then
    pyKillServer()
    println("Killed existing server")
  )

  let( (pid_str fid)
    pid_str = sprintf(nil "%d" ipcGetPid())
    println(strcat("Starting server with PID: " pid_str))
    load("/home/a1257241/Python_3.11.2/venv/lib/python3.11/site-packages/skillbridge/server/python_server.il")
    load("/home/a0543072/Share/runPython.il")
    pyStartServer(?id pid_str)
    ; Write PID to file so Python scripts can connect with the correct ID
    fid = outfile("/tmp/virtuoso_pid.txt")
    fprintf(fid "%s" pid_str)
    close(fid)
    a = t  ; Mark server as started
    println("Server started successfully")
  )
)

; Always restart server
start_server()

; Run Python script
pyRunScript("/db/iif/new_temp/LLM_PCELL/my_codes/test.py")
;pyRunScript("/db/iif/new_temp/LLM_PCELL/my_codes/test1.py")