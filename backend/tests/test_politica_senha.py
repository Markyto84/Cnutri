"""Limites e composição das senhas novas, sem dados da instalação."""
import re
import unittest

from app.core.politica_senha import gerar_senha_temporaria, validar_senha
from app.schemas.schemas import TrocaSenhaCreate, UsuarioCreate, UsuarioUpdate


class PoliticaSenhaTest(unittest.TestCase):
    def test_limites_composicao_e_edicao_sem_redefinir_senha(self):
        for senha in ("Teste1!?", "NovaSenha12!", "TESTE1!?", "Ábcdef1!"):
            with self.subTest(senha=senha):
                self.assertEqual(validar_senha(senha), senha)
                self.assertEqual(TrocaSenhaCreate(senha_atual="SenhaLegadaMuitoLonga@2026", nova_senha=senha).nova_senha, senha)
                self.assertEqual(UsuarioCreate(nome="Pessoa Teste", nome_usuario="pessoa", perfil="COPEIRA", filial_ids=[1], senha=senha).senha, senha)
        for senha in ("Ab1!xyz", "Ab1!abcdefghi", "abcdef1!", "Abcdefg1", "ABCDEF!@", "Teste12 ", "Téste123"):
            with self.subTest(senha=senha), self.assertRaises(ValueError):
                validar_senha(senha)
        self.assertIsNone(UsuarioUpdate(nome="Pessoa", nome_usuario="pessoa", perfil="COPEIRA", filial_ids=[1]).senha)

    def test_senhas_temporarias_geradas_respeitam_regra_e_nao_sao_fixas(self):
        senhas = {gerar_senha_temporaria() for _ in range(100)}
        self.assertEqual(len(senhas), 100)
        for senha in senhas:
            self.assertEqual(len(senha), 12)
            self.assertRegex(senha, r"[A-Z]")
            self.assertRegex(senha, r"[0-9]")
            self.assertTrue(re.search(r"[^\w\s]|_", senha))
            self.assertEqual(validar_senha(senha), senha)
