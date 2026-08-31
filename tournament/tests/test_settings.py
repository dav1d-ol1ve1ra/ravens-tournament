import importlib.util
import os
from pathlib import Path
from unittest.mock import patch

from django.test import SimpleTestCase


SETTINGS_PATH = Path(__file__).resolve().parents[2] / 'config' / 'settings.py'


def load_settings_for_debug(debug):
    environment = {
        'DJANGO_DEBUG': 'true' if debug else 'false',
        'DJANGO_SECRET_KEY': 'test-only-secret-key',
        'DJANGO_ALLOWED_HOSTS': 'testserver',
    }
    with patch.dict(os.environ, environment):
        spec = importlib.util.spec_from_file_location(
            f'config_settings_debug_{debug}',
            SETTINGS_PATH,
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


class ProductionSecuritySettingsTests(SimpleTestCase):
    def test_debug_false_enables_proxy_aware_ssl_redirect(self):
        production = load_settings_for_debug(False)

        self.assertTrue(production.SECURE_SSL_REDIRECT)
        self.assertEqual(
            production.SECURE_PROXY_SSL_HEADER,
            ('HTTP_X_FORWARDED_PROTO', 'https'),
        )

    def test_debug_true_does_not_force_ssl_redirect(self):
        development = load_settings_for_debug(True)

        self.assertFalse(getattr(development, 'SECURE_SSL_REDIRECT', False))
        self.assertIsNone(getattr(development, 'SECURE_PROXY_SSL_HEADER', None))
