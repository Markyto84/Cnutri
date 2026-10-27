"""Endereços de unidades não podem ocupar rotas da aplicação ou do proxy."""

# Atualizar ao adicionar uma rota fixa no App.jsx ou um prefixo público de infraestrutura.
CODIGOS_RESERVADOS = frozenset({
    "admin", "api", "assets", "cozinha", "entregas", "gestao", "login",
    "sem-unidades", "senha", "src", "ws", "receber",
})


def validar_codigo_unidade(codigo: str) -> str:
    if not any("a" <= caractere <= "z" for caractere in codigo):
        raise ValueError("O endereço da unidade deve conter pelo menos uma letra; não use somente números")
    if codigo in CODIGOS_RESERVADOS:
        raise ValueError(f"O endereço '{codigo}' é reservado pelo sistema. Escolha outro, como unidade-sul")
    return codigo
