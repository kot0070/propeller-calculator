import ctypes
import os

os.environ["TCL_LIBRARY"] = "C:/Users/kot00/Documents/Codex/2026-08-05/propeller-calculator-professional-ua-v3-windows/work/tcl_runtime/tcl8.6"
dll = ctypes.CDLL(r"C:\Users\kot00\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\DLLs\tcl86t.dll")
dll.Tcl_FindExecutable.argtypes = [ctypes.c_char_p]
dll.Tcl_CreateInterp.restype = ctypes.c_void_p
dll.Tcl_Init.argtypes = [ctypes.c_void_p]
dll.Tcl_Init.restype = ctypes.c_int
dll.Tcl_GetStringResult.argtypes = [ctypes.c_void_p]
dll.Tcl_GetStringResult.restype = ctypes.c_char_p
dll.Tcl_FindExecutable(b"python.exe")
interp = dll.Tcl_CreateInterp()
dll.Tcl_EvalEx.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int, ctypes.c_int]
dll.Tcl_EvalEx.restype = ctypes.c_int
dll.Tcl_EvalEx(interp, b"info body tclInit", -1, 0)
print("preBody", dll.Tcl_GetStringResult(interp).decode("utf-8", errors="replace"))
code = dll.Tcl_Init(interp)
print("code", code)
print("result", dll.Tcl_GetStringResult(interp).decode("utf-8", errors="replace"))
dll.Tcl_EvalEx(interp, b"set errorInfo", -1, 0)
print("errorInfo", dll.Tcl_GetStringResult(interp).decode("utf-8", errors="replace"))
dll.Tcl_EvalEx(interp, b"info body tclInit", -1, 0)
print("tclInitBody", dll.Tcl_GetStringResult(interp).decode("utf-8", errors="replace"))
