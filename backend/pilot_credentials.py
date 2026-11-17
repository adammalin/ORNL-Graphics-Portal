"""Local launcher credentials. Never put the secret in arguments, config or logs."""
import argparse
import ctypes
import getpass
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import warnings

SERVICE = 'ORNL Graphics Portal - Smartsheet OAuth DEV'
APP_SETTINGS = 'https://app.smartsheet.com/'


class CredentialError(RuntimeError):
    pass


def client_id_from_config(path):
    path = Path(path)
    value = json.loads(path.read_text())
    client_id = value.get('clientId', '')
    if not client_id:
        client_id = input('Smartsheet App client ID (not the secret): ').strip()
        if not re.fullmatch(r'[A-Za-z0-9_-]{8,200}', client_id):
            raise CredentialError('Enter the App client ID from the existing Smartsheet Developer Tools app.')
        value['clientId'] = client_id
        # Store only the public identifier; retain every other private setting.
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, delete=False) as stream:
                temporary = stream.name
                os.fchmod(stream.fileno(), 0o600)
                json.dump(value, stream, indent=2)
                stream.write('\n')
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            if temporary and os.path.exists(temporary):
                os.unlink(temporary)
    if not isinstance(client_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{8,200}', client_id):
        raise CredentialError('The configured Smartsheet App client ID is invalid.')
    return client_id


class _MacKeychain:
    """macOS Security framework bridge; secrets never cross a process boundary."""
    def __init__(self, keychain=None):
        if sys.platform != 'darwin':
            raise CredentialError('Keychain storage requires macOS. Use --secret-source prompt elsewhere.')
        self.keychain = keychain
        self.security = ctypes.CDLL('/System/Library/Frameworks/Security.framework/Security')
        self.core = ctypes.CDLL('/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation')
        pointer, uint = ctypes.c_void_p, ctypes.c_uint32
        signatures = {
            'SecKeychainFindGenericPassword': [pointer,uint,ctypes.c_char_p,uint,ctypes.c_char_p,ctypes.POINTER(uint),ctypes.POINTER(pointer),ctypes.POINTER(pointer)],
            'SecKeychainAddGenericPassword': [pointer,uint,ctypes.c_char_p,uint,ctypes.c_char_p,uint,pointer,ctypes.POINTER(pointer)],
            'SecKeychainItemModifyAttributesAndData': [pointer,pointer,uint,pointer],
            'SecKeychainItemFreeContent': [pointer,pointer],
        }
        for name, args in signatures.items():
            function = getattr(self.security, name)
            function.argtypes, function.restype = args, ctypes.c_int32
        self.core.CFRelease.argtypes = [pointer]
        self.core.CFRelease.restype = None

    def read(self, client_id):
        service, account = SERVICE.encode(), client_id.encode()
        length, data = ctypes.c_uint32(), ctypes.c_void_p()
        status = self.security.SecKeychainFindGenericPassword(self.keychain, len(service), service,
            len(account), account, ctypes.byref(length), ctypes.byref(data), None)
        if status == -25300:  # errSecItemNotFound only; cancellation must fail closed.
            return None
        if status:
            raise CredentialError('Keychain access was cancelled or unavailable (macOS status '+str(status)+'). Unlock your login Keychain and retry; no credential was replaced.')
        try:
            return ctypes.string_at(data, length.value).decode('utf-8')
        finally:
            self.security.SecKeychainItemFreeContent(None, data)

    def write(self, client_id, secret):
        service, account, password = SERVICE.encode(), client_id.encode(), secret.encode()
        item = ctypes.c_void_p()
        status = self.security.SecKeychainFindGenericPassword(self.keychain, len(service), service,
            len(account), account, None, None, ctypes.byref(item))
        try:
            if status == -25300:
                status = self.security.SecKeychainAddGenericPassword(self.keychain, len(service), service,
                    len(account), account, len(password), password, None)
            elif status == 0:
                status = self.security.SecKeychainItemModifyAttributesAndData(item, None, len(password), password)
            if status:
                raise CredentialError('The App secret was not saved (macOS status '+str(status)+'). Retry after unlocking Keychain. No server was started.')
        finally:
            if item:
                self.core.CFRelease(item)


def read_keychain(client_id):
    secret = _MacKeychain().read(client_id)
    if secret is not None and not secret.strip():
        raise CredentialError('The saved Keychain item is empty. Run save-pilot-credentials.command to replace it.')
    return secret


def hidden_secret(prompt):
    if not sys.stdin.isatty():
        raise CredentialError('Open this launcher in Terminal for hidden secret entry.')
    secret = ''
    while not secret.strip():
        try:
            with warnings.catch_warnings():
                warnings.simplefilter('error', getpass.GetPassWarning)
                secret = getpass.getpass(prompt)
        except getpass.GetPassWarning:
            raise CredentialError('This Terminal cannot hide input. Cancelled without reading or saving a secret; open a normal local Terminal and retry.') from None
        if not secret.strip():
            print('No secret received. Paste it and press Return; nothing has started yet.', flush=True)
    return secret


def save_keychain(client_id):
    keychain = _MacKeychain()
    print("ONE-TIME SETUP: save the App secret in this Mac's login Keychain.", flush=True)
    print('Find it at '+APP_SETTINGS+' > Account > Developer Tools > ORNL Graphics Portal - DEV Pilot > View/Edit.', flush=True)
    print('Copy App secret, not an API token. Paste at the hidden prompt and press Return.', flush=True)
    print('No characters or dots appear. macOS may ask to unlock Keychain or permit this Python launcher.', flush=True)
    secret = hidden_secret('Smartsheet App secret (hidden; saved in macOS Keychain): ')
    keychain.write(client_id, secret)
    if keychain.read(client_id) != secret:
        raise CredentialError('Keychain verification failed. No server was started; retry setup.')
    print('App secret saved in macOS Keychain. Future launches retrieve it automatically.', flush=True)
    return secret


def load_secret(client_id, source='keychain'):
    if source == 'keychain':
        secret = read_keychain(client_id)
        if secret is None:
            return save_keychain(client_id)
        print('App ID loaded from private config; App secret loaded from macOS Keychain.', flush=True)
        return secret
    print('Memory-only mode: the App secret will NOT be saved for next time.', flush=True)
    return hidden_secret('Smartsheet App secret (hidden; not saved): ')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', default='.local/pilot-config.json')
    args = parser.parse_args()
    client_id = client_id_from_config(args.config)
    save_keychain(client_id)


if __name__ == '__main__':
    try:
        main()
    except (CredentialError, OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
