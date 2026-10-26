# Módulo de assinatura

**Situação atual: coleta suspensa no fluxo de Entregas, por solicitação do usuário.**
A copeira finaliza pelo botão Realizar entrega, sem recebedor ou assinatura.
Veja [entrega direta](ENTREGA-DIRETA.md).

O código reutilizável fica preservado para futuras atualizações e reativação.
Ele reúne captura, validação dos traços e geração do comprovante PNG, com contrato v1.
As assinaturas já registradas continuam disponíveis nos relatórios autorizados.

## Responsabilidades

| Parte | Local | Responsabilidade |
|---|---|---|
| API do componente | `frontend/src/modules/assinatura/index.js` | Ponto de entrada para novos formulários |
| Captura | `frontend/src/modules/assinatura/Assinatura.jsx` | Dedo, caneta e mouse, instrução e nome acessível configuráveis |
| Regras e payload | `frontend/src/modules/assinatura/modelo.js` | Coordenadas normalizadas, limites e cópia dos traços para envio |
| Desenho | `frontend/src/modules/assinatura/desenho.js` | Prévia no canvas |
| API do servidor | `backend/app/modules/assinatura/__init__.py` | Esquema, versão do contrato e geração de imagem |
| Contrato | `backend/app/modules/assinatura/contrato.json` | Limites e parâmetros do formato v1 |
| Validação do servidor | `backend/app/modules/assinatura/esquemas.py` | Modelo Pydantic independente de entregas |
| Imagem | `backend/app/modules/assinatura/imagem.py` | PNG em memória, sem arquivo enviado pelo navegador |

O módulo não depende de pedidos, banco, autenticação ou configuração de unidade.
A funcionalidade que o utiliza continua responsável por autorizar o usuário,
identificar o signatário, registrar a data/hora do servidor e persistir o comprovante
na sua transação. No fluxo de Entregas, essas responsabilidades permanecem no endpoint
que finaliza a entrega e no relatório autorizado.

## Uso em um novo formulário React

```jsx
import { useState } from 'react'
import { Assinatura, prepararAssinatura, validarAssinatura } from '../modules/assinatura/index.js'

function Confirmacao() {
  const [tracos, setTracos] = useState([])
  const erro = validarAssinatura(tracos)

  function concluir() {
    if (erro) return
    const assinatura = prepararAssinatura(tracos)
    // Enviar "assinatura" ao endpoint autorizado da funcionalidade.
  }

  return <>
    <Assinatura tracos={tracos} onChange={setTracos}
      rotulo="Área de assinatura do responsável"
      instrucao="Assine para confirmar o recebimento." />
    <button type="button" onClick={concluir} disabled={Boolean(erro)}>Confirmar</button>
  </>
}
```

Propriedades: `tracos`, `onChange`, `disabled`, `rotulo` e `instrucao`.
Cada instância possui identificação própria para as instruções acessíveis.
O componente não faz requisições nem salva o desenho no armazenamento do navegador.
`prepararAssinatura` produz uma cópia independente, para evitar que alterações na
captura modifiquem um payload em preparação. Desenhos incompletos são sinalizados
antes do envio; cancelar um gesto descarta somente o traço que estava em andamento.

## Uso no servidor

```python
from app.modules.assinatura import AssinaturaCreate, gerar_assinatura_png

assinatura = AssinaturaCreate.model_validate(dados_recebidos)
imagem_png = gerar_assinatura_png(assinatura)
# Persistir imagem_png na transação autorizada da funcionalidade.
```

O gerador também aceita diretamente um dicionário no formato do contrato e aplica
a validação antes de renderizar. Não precisa inicializar a aplicação, abrir uma
conexão de banco ou acessar uma impressora.

## Contrato v1 e compatibilidade

O payload continua no formato `{"tracos": [[{"x": 0.1, "y": 0.7}, ...]]}`:

- Coordenadas finitas entre 0 e 1, independentes do tamanho da tela.
- De 1 a 40 traços, cada um com 2 a 1.500 pontos.
- Máximo total de 8.000 pontos e comprimento normalizado mínimo de 0,08.
- Comprovante PNG em escala de cinza, 1.000 × 500 pixels, traço de 6 pixels.
- A versão é identificada pelo módulo; não foi acrescentado campo obrigatório ao
  payload existente nem alterado o armazenamento dos comprovantes.

Os caminhos anteriores de `AssinaturaCreate`/`PontoAssinatura` em
`app.schemas.schemas`, de `gerar_assinatura_png` em `app.services.assinatura` e do
componente `AssinaturaRecebedor` são adaptadores de compatibilidade. Novas telas
devem importar a API pública do módulo.

## Atualizações futuras

1. Concentrar alterações de captura/aparência/regras nos diretórios do módulo.
2. Ao alterar limites, atualizar contrato e implementação do frontend juntos; o
   teste de compatibilidade compara os parâmetros de ambas as plataformas.
3. Preservar o formato v1 para atualizações compatíveis. Para uma alteração que
   mude o formato ou a interpretação dos dados, criar e planejar uma versão nova
   com compatibilidade explícita, antes de substituir o fluxo existente.
4. Executar testes do módulo, de Entregas e dos relatórios, além do build.
5. Publicar pelo processo habitual do Cnutri. O módulo é parte da aplicação;
   mudanças no servidor exigem reinício da API, e mudanças React exigem publicação
   do frontend. Não é um plugin carregado remotamente.

Comprovantes já registrados não são redesenhados ou convertidos nas atualizações.
Não há migração de tabelas nesta modularização. Os arquivos do módulo são incluídos
pelos Dockerfiles existentes, sem serviços ou dependências novos.

Os exemplos de compatibilidade em `frontend/tests/fixtures/assinatura-v1.json` são
utilizados por testes de ambas as plataformas. Os testes também conferem geração
do PNG, limites, posição em telas de tamanhos diferentes, independência do banco
e compatibilidade dos imports anteriores. Os testes existentes verificam que uma
entrega sem assinatura válida não é concluída e que o relatório exige autorização.

Na validação de 26/10/2026, foram aprovados 209 testes do backend e 51 do frontend,
além do build. Cinco testes adicionais de HTTPS/recuperação não foram executados
por dependerem de ambientes específicos. A homologação no navegador utilizou
dados fictícios e verificou captura, limpeza, finalização, data/hora do servidor
e acesso autorizado ao PNG do relatório.
