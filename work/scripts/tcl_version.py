import ctypes

dll = ctypes.CDLL(r"C:\Users\kot00\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\DLLs\tcl86t.dll")
major = ctypes.c_int()
minor = ctypes.c_int()
patch = ctypes.c_int()
kind = ctypes.c_int()
dll.Tcl_GetVersion(ctypes.byref(major), ctypes.byref(minor), ctypes.byref(patch), ctypes.byref(kind))
print(major.value, minor.value, patch.value, kind.value)
