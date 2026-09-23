import ctypes
import os

root = r"C:/Users/kot00/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/tcl/tcl8.6"
os.environ["TCL_LIBRARY"] = root
dll = ctypes.CDLL(r"C:\Users\kot00\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\DLLs\tcl86t.dll")
dll.Tcl_FindExecutable.argtypes=[ctypes.c_char_p]
dll.Tcl_CreateInterp.restype=ctypes.c_void_p
dll.Tcl_EvalEx.argtypes=[ctypes.c_void_p,ctypes.c_char_p,ctypes.c_int,ctypes.c_int]
dll.Tcl_EvalEx.restype=ctypes.c_int
dll.Tcl_GetStringResult.argtypes=[ctypes.c_void_p]
dll.Tcl_GetStringResult.restype=ctypes.c_char_p
dll.Tcl_FindExecutable(b"python.exe")
i=dll.Tcl_CreateInterp()
for script in ["pwd", "file exists C:/Windows/notepad.exe", "glob -nocomplain C:/Windows/notepad.exe", f"file exists {{{root}/init.tcl}}", f"set ::tcl_library {{{root}}}", f"source {{{root}/init.tcl}}", "set errorInfo"]:
    code=dll.Tcl_EvalEx(i,script.encode(),-1,0)
    print(script,code,dll.Tcl_GetStringResult(i).decode(errors="replace"))
