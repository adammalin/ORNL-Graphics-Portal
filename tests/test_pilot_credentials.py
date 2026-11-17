"""Credential startup boundaries; synthetic secrets, no real Keychain reads."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backend import pilot_credentials as credentials


class CredentialTests(unittest.TestCase):
    def test_existing_client_id_is_read_without_touching_other_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'config.json'
            original = '{"clientId":"synthetic-client","other":{"keep":true}}\n'
            path.write_text(original)
            self.assertEqual(credentials.client_id_from_config(path), 'synthetic-client')
            self.assertEqual(path.read_text(), original)

    def test_missing_id_is_saved_privately_without_losing_config(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'config.json'
            path.write_text('{"other":{"keep":true}}')
            with patch('builtins.input', return_value='synthetic-client'):
                credentials.client_id_from_config(path)
            self.assertEqual(json.loads(path.read_text()), {'clientId':'synthetic-client','other':{'keep':True}})
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_keychain_read_stays_in_memory_and_never_echoes_secret(self):
        output = io.StringIO()
        with patch.object(credentials, '_MacKeychain') as native, redirect_stdout(output):
            native.return_value.read.return_value = 'synthetic-secret'
            self.assertEqual(credentials.load_secret('synthetic-client'), 'synthetic-secret')
            native.return_value.read.assert_called_once_with('synthetic-client')
            native.return_value.write.assert_not_called()
        self.assertNotIn('synthetic-secret', output.getvalue())

    def test_only_absent_item_triggers_setup_not_denied_keychain(self):
        with patch.object(credentials, 'read_keychain', return_value=None), \
             patch.object(credentials, 'save_keychain', return_value='synthetic-secret') as save:
            self.assertEqual(credentials.load_secret('synthetic-client'), 'synthetic-secret')
            save.assert_called_once_with('synthetic-client')
        with patch.object(credentials, 'read_keychain', side_effect=credentials.CredentialError('denied')), \
             patch.object(credentials, 'save_keychain') as save:
            with self.assertRaises(credentials.CredentialError):
                credentials.load_secret('synthetic-client')
            save.assert_not_called()

    def test_save_uses_hidden_prompt_and_native_api_without_echo(self):
        with patch.object(credentials, '_MacKeychain') as native, \
             patch.object(credentials.sys.stdin, 'isatty', return_value=True), \
             patch.object(credentials.getpass, 'getpass', return_value='synthetic-secret'), \
             redirect_stdout(io.StringIO()) as output:
            native.return_value.read.return_value = 'synthetic-secret'
            self.assertEqual(credentials.save_keychain('synthetic-client'), 'synthetic-secret')
            native.return_value.write.assert_called_once_with('synthetic-client', 'synthetic-secret')
        self.assertNotIn('synthetic-secret', output.getvalue())

    def test_failed_or_noninteractive_save_cannot_fall_back_to_plaintext(self):
        with patch.object(credentials, '_MacKeychain') as native, \
             patch.object(credentials.sys.stdin, 'isatty', return_value=False), \
             redirect_stdout(io.StringIO()):
            with self.assertRaises(credentials.CredentialError): credentials.save_keychain('synthetic-client')
            native.return_value.write.assert_not_called()
        with patch.object(credentials, '_MacKeychain') as native, \
             patch.object(credentials.sys.stdin, 'isatty', return_value=True), \
             patch.object(credentials.getpass, 'getpass', return_value='synthetic-secret'), \
             redirect_stdout(io.StringIO()):
            native.return_value.write.side_effect = credentials.CredentialError('denied')
            with self.assertRaises(credentials.CredentialError): credentials.save_keychain('synthetic-client')

    def test_terminal_without_hidden_input_fails_before_reading_a_secret(self):
        with patch.object(credentials.sys.stdin, 'isatty', return_value=True), \
             patch.object(credentials.getpass, 'getpass', side_effect=credentials.getpass.GetPassWarning('cannot hide')):
            with self.assertRaises(credentials.CredentialError):
                credentials.hidden_secret('Test: ')


if __name__ == '__main__':
    unittest.main()
