"""Configuração do QR. O fluxo manual é coberto em test_recebimento_nutricao.py."""
import unittest
from pydantic import ValidationError
from app.core.config import Settings


class ConfiguracaoQRTest(unittest.TestCase):
    def test_endereco_publico_exige_origem_http_valida_sem_credenciais_ou_parametros(self):
        argumentos = {'_env_file': None, 'JWT_SECRET': 'TESTE-SEM-SEGREDO-' * 3, 'APP_ENV': 'test'}
        valido = Settings(**argumentos, URL_RECEBIMENTO_PUBLICA='https://cnutri.empresa.local/')
        self.assertEqual(valido.URL_RECEBIMENTO_PUBLICA, 'https://cnutri.empresa.local')
        for url in ('file:///teste', 'http://usuario:senha@servidor.local', 'https://servidor.local/admin',
            'https://servidor.local?token=1', 'http://servidor.local:abc', 'http://servidor.local:0'):
            with self.assertRaises(ValidationError):
                Settings(**argumentos, URL_RECEBIMENTO_PUBLICA=url)
