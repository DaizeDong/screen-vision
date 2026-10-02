"""An explicitly launched, synthetic native window for the interactive gate."""
import argparse
import ctypes
from ctypes import wintypes as W


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--title', required=True)
    args = parser.parse_args()
    user = ctypes.windll.user32
    kernel = ctypes.windll.kernel32
    result_type = ctypes.c_ssize_t
    wndproc = ctypes.WINFUNCTYPE(result_type, W.HWND, W.UINT, W.WPARAM, W.LPARAM)

    class WindowClass(ctypes.Structure):
        _fields_ = [('style', W.UINT), ('proc', wndproc), ('class_extra', ctypes.c_int),
                    ('window_extra', ctypes.c_int), ('instance', W.HINSTANCE),
                    ('icon', W.HICON), ('cursor', W.HANDLE), ('background', W.HBRUSH),
                    ('menu_name', W.LPCWSTR), ('class_name', W.LPCWSTR)]

    kernel.GetModuleHandleW.restype = W.HMODULE
    user.DefWindowProcW.restype = result_type
    user.DefWindowProcW.argtypes = [W.HWND, W.UINT, W.WPARAM, W.LPARAM]
    user.CreateWindowExW.restype = W.HWND
    user.CreateWindowExW.argtypes = [W.DWORD, W.LPCWSTR, W.LPCWSTR, W.DWORD,
                                    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                    W.HWND, W.HMENU, W.HINSTANCE, W.LPVOID]
    user.SetWindowTextW.argtypes = [W.HWND, W.LPCWSTR]
    user.ShowWindow.argtypes = [W.HWND, ctypes.c_int]
    user.UpdateWindow.argtypes = [W.HWND]
    display = None
    digits = ''

    @wndproc
    def callback(hwnd, message, wparam, lparam):
        nonlocal digits
        if message == 0x0111 and wparam & 0xffff == 7:
            digits += '7'
            user.SetWindowTextW(display, digits)
            return 0
        if message == 0x0002:
            user.PostQuitMessage(0)
            return 0
        return user.DefWindowProcW(hwnd, message, wparam, lparam)

    instance = kernel.GetModuleHandleW(None)
    cls = WindowClass(proc=callback, instance=instance, background=6, class_name=args.title)
    if not user.RegisterClassW(ctypes.byref(cls)):
        raise ctypes.WinError()
    window = user.CreateWindowExW(0, args.title, args.title, 0x00CF0000,
                                  100, 100, 360, 240, None, None, instance, None)
    if not window:
        raise ctypes.WinError()
    user.CreateWindowExW(0, 'BUTTON', 'Seven', 0x50000000,
                        20, 20, 120, 50, window, 7, instance, None)
    display = user.CreateWindowExW(0, 'STATIC', '0', 0x50000000,
                                   20, 100, 220, 40, window, 8, instance, None)
    user.ShowWindow(window, 5)
    user.UpdateWindow(window)
    message = W.MSG()
    while user.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
        user.TranslateMessage(ctypes.byref(message))
        user.DispatchMessageW(ctypes.byref(message))


if __name__ == '__main__':
    main()
