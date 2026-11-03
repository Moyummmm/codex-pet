"""Desktop proxy discovery respects configured settings and environment."""
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from PyQt6.QtCore import QProcessEnvironment
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from codex_pet.codex_client import _linux_system_proxy


class ProxyTest(unittest.TestCase):
    def test_explicit_environment_takes_precedence(self):
        env = QProcessEnvironment()
        env.insert('https_proxy', 'http://existing:1234')
        with patch('codex_pet.codex_client.shutil.which') as which:
            _linux_system_proxy(env)
        which.assert_not_called()
        self.assertEqual(env.value('https_proxy'), 'http://existing:1234')

    def test_kde_manual_and_direct(self):
        values = {'ProxyType': '1', 'ReversedException': 'false', 'httpProxy': 'http://proxy:8080',
                  'httpsProxy': 'http://proxy:8080', 'NoProxyFor': 'localhost,example.org'}
        def run(args, **kwargs):
            return SimpleNamespace(stdout=values[args[-1]])
        with patch.dict(os.environ, {'XDG_CURRENT_DESKTOP': 'KDE'}), \
             patch('codex_pet.codex_client.shutil.which', return_value='/usr/bin/kreadconfig6'), \
             patch('codex_pet.codex_client.subprocess.run', side_effect=run):
            env = QProcessEnvironment()
            _linux_system_proxy(env)
            self.assertEqual(env.value('https_proxy'), 'http://proxy:8080')
            self.assertEqual(env.value('no_proxy'), 'localhost,example.org')
            values['ProxyType'] = '0'
            direct = QProcessEnvironment()
            _linux_system_proxy(direct)
            self.assertFalse(direct.contains('https_proxy'))

    def test_gnome_manual(self):
        values = {'mode': "'manual'", 'host': "'proxy'", 'port': '8080', 'ignore-hosts': "['localhost']"}
        def run(args, **kwargs):
            return SimpleNamespace(stdout=values[args[-1]])
        with patch.dict(os.environ, {'XDG_CURRENT_DESKTOP': 'GNOME'}), \
             patch('codex_pet.codex_client.shutil.which', return_value='/usr/bin/gsettings'), \
             patch('codex_pet.codex_client.subprocess.run', side_effect=run):
            env = QProcessEnvironment()
            _linux_system_proxy(env)
            self.assertEqual(env.value('https_proxy'), 'http://proxy:8080')
            self.assertEqual(env.value('no_proxy'), 'localhost')


if __name__ == '__main__':
    unittest.main()
