"""Fixed-purpose macOS Keychain storage. Never passes secrets through shell argv."""
import ctypes as C
import json
import sys
from threading import Lock

SERVICE = b'com.advancore.supplier.santa-fms'
ACCOUNT = b'supplier-login'
LOCK = Lock()

class VaultUnavailable(Exception):
    pass

class SupplierKeychain:
    def __init__(self, service=SERVICE):
        if sys.platform != 'darwin':
            raise VaultUnavailable('macOS Keychain is required.')
        self.service = service
        self.sec = C.CDLL('/System/Library/Frameworks/Security.framework/Security')
        self.cf = C.CDLL('/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation')
        self.cf.CFRelease.argtypes = [C.c_void_p]
        self.cf.CFRelease.restype = None
        self.sec.SecKeychainFindGenericPassword.argtypes = [C.c_void_p,C.c_uint32,C.c_char_p,C.c_uint32,C.c_char_p,C.c_void_p,C.c_void_p,C.POINTER(C.c_void_p)]
        self.sec.SecKeychainAddGenericPassword.argtypes = [C.c_void_p,C.c_uint32,C.c_char_p,C.c_uint32,C.c_char_p,C.c_uint32,C.c_void_p,C.c_void_p]
        self.sec.SecKeychainItemModifyAttributesAndData.argtypes = [C.c_void_p,C.c_void_p,C.c_uint32,C.c_void_p]
        self.sec.SecKeychainItemDelete.argtypes = [C.c_void_p]
        for name in ('SecKeychainFindGenericPassword','SecKeychainAddGenericPassword','SecKeychainItemModifyAttributesAndData','SecKeychainItemDelete'):
            getattr(self.sec,name).restype = C.c_int32

    def _find(self):
        item=C.c_void_p()
        status=self.sec.SecKeychainFindGenericPassword(None,len(self.service),self.service,len(ACCOUNT),ACCOUNT,None,None,C.byref(item))
        if status == -25300:return None
        if status != 0:raise VaultUnavailable('Keychain access unavailable. Unlock your login Keychain and retry.')
        return item

    def exists(self):
        with LOCK:
            item=self._find()
            if item is None:return False
            self.cf.CFRelease(item)
            return True

    def save(self, username, password):
        # A single Keychain item keeps username/password replacement atomic.
        encoded=json.dumps({'username':username,'password':password},ensure_ascii=False).encode()
        buffer=C.create_string_buffer(encoded)
        try:
            with LOCK:
                item=self._find()
                if item is None:
                    status=self.sec.SecKeychainAddGenericPassword(None,len(self.service),self.service,len(ACCOUNT),ACCOUNT,len(encoded),buffer,None)
                else:
                    try:status=self.sec.SecKeychainItemModifyAttributesAndData(item,None,len(encoded),buffer)
                    finally:self.cf.CFRelease(item)
                if status != 0:raise VaultUnavailable('Credentials were not saved. Check macOS Keychain access and retry.')
        finally:
            C.memset(buffer,0,len(buffer))

    def remove(self):
        with LOCK:
            item=self._find()
            if item is None:return
            try:
                if self.sec.SecKeychainItemDelete(item) != 0:
                    raise VaultUnavailable('Credentials could not be removed. Check macOS Keychain access.')
            finally:self.cf.CFRelease(item)
