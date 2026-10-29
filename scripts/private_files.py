"""Exclusive private files: POSIX 0600 or a protected Windows owner/SYSTEM DACL.

On Windows the DACL is supplied to CreateFileW at creation, before any secret is
written. chmod/stat mode bits on that platform do not describe NTFS permissions.
"""
import os
from pathlib import Path


if os.name == 'nt':
    import ctypes as ct
    from ctypes import wintypes as wt
    import msvcrt

    kernel = ct.WinDLL('kernel32', use_last_error=True)
    security = ct.WinDLL('advapi32', use_last_error=True)
    ptr = ct.c_void_p

    class SecurityAttributes(ct.Structure):
        _fields_ = [('length', wt.DWORD), ('descriptor', ptr), ('inherit', wt.BOOL)]

    class AclHeader(ct.Structure):
        _fields_ = [('revision', wt.BYTE), ('reserved', wt.BYTE), ('size', wt.WORD),
                    ('count', wt.WORD), ('reserved2', wt.WORD)]

    kernel.GetCurrentProcess.restype = wt.HANDLE
    kernel.CloseHandle.argtypes = [wt.HANDLE]
    kernel.CloseHandle.restype = wt.BOOL
    kernel.LocalFree.argtypes = [ptr]
    kernel.LocalFree.restype = ptr
    kernel.CreateFileW.argtypes = [wt.LPCWSTR, wt.DWORD, wt.DWORD,
                                  ct.POINTER(SecurityAttributes), wt.DWORD, wt.DWORD, wt.HANDLE]
    kernel.CreateFileW.restype = wt.HANDLE
    security.OpenProcessToken.argtypes = [wt.HANDLE, wt.DWORD, ct.POINTER(wt.HANDLE)]
    security.OpenProcessToken.restype = wt.BOOL
    security.GetTokenInformation.argtypes = [wt.HANDLE, ct.c_int, ptr, wt.DWORD, ct.POINTER(wt.DWORD)]
    security.GetTokenInformation.restype = wt.BOOL
    security.ConvertSidToStringSidW.argtypes = [ptr, ct.POINTER(ptr)]
    security.ConvertSidToStringSidW.restype = wt.BOOL
    security.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [wt.LPCWSTR, wt.DWORD, ct.POINTER(ptr), ptr]
    security.ConvertStringSecurityDescriptorToSecurityDescriptorW.restype = wt.BOOL
    security.GetNamedSecurityInfoW.argtypes = [wt.LPCWSTR, ct.c_int, wt.DWORD,
                                             ct.POINTER(ptr), ptr, ct.POINTER(ptr), ptr, ct.POINTER(ptr)]
    security.GetNamedSecurityInfoW.restype = wt.DWORD
    security.GetSecurityDescriptorControl.argtypes = [ptr, ct.POINTER(wt.WORD), ct.POINTER(wt.DWORD)]
    security.GetSecurityDescriptorControl.restype = wt.BOOL
    security.GetAce.argtypes = [ptr, wt.DWORD, ct.POINTER(ptr)]
    security.GetAce.restype = wt.BOOL

    def _sid_text(sid):
        text = ptr()
        if not security.ConvertSidToStringSidW(sid, ct.byref(text)):
            raise ct.WinError(ct.get_last_error())
        try:
            return ct.wstring_at(text)
        finally:
            kernel.LocalFree(text)

    def _user_sid():
        token = wt.HANDLE()
        if not security.OpenProcessToken(kernel.GetCurrentProcess(), 0x0008, ct.byref(token)):
            raise ct.WinError(ct.get_last_error())
        try:
            length = wt.DWORD()
            security.GetTokenInformation(token, 1, None, 0, ct.byref(length))
            data = ct.create_string_buffer(length.value)
            if not security.GetTokenInformation(token, 1, data, length, ct.byref(length)):
                raise ct.WinError(ct.get_last_error())
            return _sid_text(ct.cast(data, ct.POINTER(ptr))[0])
        finally:
            kernel.CloseHandle(token)

    def _create_windows(path):
        descriptor = ptr()
        sddl = f'D:P(A;;FA;;;{_user_sid()})(A;;FA;;;SY)'
        if not security.ConvertStringSecurityDescriptorToSecurityDescriptorW(sddl, 1, ct.byref(descriptor), None):
            raise ct.WinError(ct.get_last_error())
        try:
            attributes = SecurityAttributes(ct.sizeof(SecurityAttributes), descriptor, False)
            handle = kernel.CreateFileW(str(path), 0xC0000000, 0, ct.byref(attributes), 1, 0x80, None)
            if handle == ptr(-1).value:
                raise ct.WinError(ct.get_last_error())
            try:
                fd = msvcrt.open_osfhandle(handle, os.O_RDWR | os.O_BINARY)
            except BaseException:
                kernel.CloseHandle(handle)
                raise
            os.set_inheritable(fd, False)
            return fd
        finally:
            kernel.LocalFree(descriptor)

    def _private_windows(path):
        descriptor, dacl, owner = ptr(), ptr(), ptr()
        error = security.GetNamedSecurityInfoW(str(path), 1, 0x00000005,
                                              ct.byref(owner), None, ct.byref(dacl), None, ct.byref(descriptor))
        if error:
            raise ct.WinError(error)
        try:
            control, revision = wt.WORD(), wt.DWORD()
            if not security.GetSecurityDescriptorControl(descriptor, ct.byref(control), ct.byref(revision)):
                raise ct.WinError(ct.get_last_error())
            sid = _user_sid()
            if not dacl or not control.value & 0x1000 or not owner or _sid_text(owner) != sid:
                return False
            header = ct.cast(dacl, ct.POINTER(AclHeader)).contents
            principals = set()
            for index in range(header.count):
                ace = ptr()
                if not security.GetAce(dacl, index, ct.byref(ace)):
                    raise ct.WinError(ct.get_last_error())
                # Only explicit ACCESS_ALLOWED_ACE entries for owner/SYSTEM.
                if ct.c_ubyte.from_address(ace.value).value != 0 or ct.c_ubyte.from_address(ace.value + 1).value & 0x10:
                    return False
                principals.add(_sid_text(ace.value + 8))
            return sid in principals and principals.issubset({sid, 'S-1-5-18'})
        finally:
            kernel.LocalFree(descriptor)


def create_private(path):
    """Return an owned, non-inheritable read/write fd; never replace any file."""
    path = Path(path).absolute()
    if os.name == 'nt':
        return _create_windows(path)
    return os.open(path, os.O_RDWR | os.O_CREAT | os.O_EXCL, 0o600)


def is_private(path):
    path = Path(path).absolute()
    if path.is_symlink() or not path.is_file():
        return False
    if os.name == 'nt':
        return _private_windows(path)
    return path.stat().st_mode & 0o077 == 0
