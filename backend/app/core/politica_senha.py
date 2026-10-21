"""Regra para senhas novas; a verificação de senhas existentes permanece independente."""
import secrets
import string
import unicodedata

MIN_SENHA = 8
MAX_SENHA = 12
REGRA_SENHA = "Use de 8 a 12 caracteres, com pelo menos uma letra maiúscula, um número e um caractere especial."


def validar_senha(senha: str | None) -> str | None:
    if senha is not None and (
        not MIN_SENHA <= len(senha) <= MAX_SENHA
        or not any(unicodedata.category(c) == "Lu" for c in senha)
        or not any(c in string.digits for c in senha)
        or not any(not c.isalnum() and not c.isspace() for c in senha)
    ):
        raise ValueError(REGRA_SENHA)
    return senha


def gerar_senha_temporaria() -> str:
    grupos = (string.ascii_uppercase, string.ascii_lowercase, string.digits, "!@#$%&*?+-_")
    caracteres = [secrets.choice(grupo) for grupo in grupos]
    alfabeto = "".join(grupos)
    caracteres.extend(secrets.choice(alfabeto) for _ in range(MAX_SENHA - len(caracteres)))
    secrets.SystemRandom().shuffle(caracteres)
    return "".join(caracteres)
