"""Validação sem consultas DNS e sem aceitar nomes, listas ou cabeçalhos."""
from email_validator import EmailNotValidError, validate_email


def normalizar_email(valor):
    if not isinstance(valor, str) or any(ord(c) < 32 or ord(c) == 127 for c in valor):
        raise ValueError("Informe um único e-mail válido, como nome@empresa.com")
    try:
        return validate_email(valor.strip(), check_deliverability=False, allow_smtputf8=False).ascii_email
    except EmailNotValidError:
        raise ValueError("Informe um único e-mail válido, como nome@empresa.com") from None
