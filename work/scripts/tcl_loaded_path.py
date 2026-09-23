import ctypes
import _tkinter

kernel32 = ctypes.windll.kernel32
kernel32.GetModuleHandleW.restype = ctypes.c_void_p
handle = kernel32.GetModuleHandleW("tcl86t.dll")
buffer = ctypes.create_unicode_buffer(32768)
kernel32.GetModuleFileNameW(ctypes.c_void_p(handle), buffer, len(buffer))
print(buffer.value)
print(_tkinter.TCL_VERSION, _tkinter.TK_VERSION)
