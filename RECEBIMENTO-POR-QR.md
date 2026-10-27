# Recebimento por QR Code

Nas novas filipetas, o rodapé **ENTREGA À RECEPÇÃO** traz um QR Code no lugar das linhas
de assinatura e data/hora. O recebedor escaneia o código com o celular, informa seu nome e registro
profissional e toca em **Confirmar recebimento**. A confirmação altera a refeição de
**Pronto** para **Entregue** e usa a data/hora do servidor. A cozinha e o painel de entregas
recebem a atualização, e os relatórios e exportações mostram o nome e o registro profissional informados.

O campo **Recebedor** solicita o nome completo e é obrigatório, junto ao registro profissional,
para novas confirmações. O nome aceita acentos, apóstrofos e sobrenomes compostos, até 120 caracteres.
Recebimentos anteriores sem nome mantêm o registro e o horário originais, sem atribuição retroativa.

O preenchimento identifica o recebedor por declaração. Não equivale a autenticação no AD
nem a consulta de validade do registro junto a um conselho profissional.

## Configuração

Configure no ambiente privado do backend:

```dotenv
URL_RECEBIMENTO_PUBLICA=http://10.1.140.15:5173
```

Use o domínio/IP, protocolo e porta pelos quais os celulares acessam o Cnutri. Essa variável
aceita somente a origem da aplicação, sem caminhos, credenciais ou parâmetros. Reinicie
a API após mudar o endereço. O celular precisa alcançar esse endereço na intranet.
Em uma futura migração, prefira manter um nome DNS estável; os links já impressos contêm
o endereço vigente na emissão.

Sem a configuração, a instalação mantém o fluxo anterior. As filipetas já emitidas continuam
utilizáveis: pedidos antigos sem QR podem ser finalizados pela copeira. Uma nova reimpressão
com a integração configurada inclui o QR e passa a exigir confirmação do recebedor.
Não são reimpressos pedidos automaticamente durante a atualização.

## Registro e integridade

- Cada pedido tem um código aleatório exclusivo; não contém nome, prontuário ou registro.
- O código fica no fragmento da URL (`/receber#...`), fora do caminho HTTP e do Referer.
  A consulta e a confirmação enviam o código no corpo da requisição.
- A página exibe apenas unidade, número e situação da refeição. O nome e o registro profissional
  ficam disponíveis nos relatórios autenticados, sem expô-los em consultas públicas.
- O botão exige nome e registro preenchidos; o servidor só aceita pedidos prontos, de unidade ativa.
  Códigos inválidos, substituídos e pedidos cancelados não registram entrega.
- Confirmações repetidas preservam o primeiro registro e horário. O bloqueio do pedido
  coordena confirmação, cancelamento e impressão. Uma correção dos dados gera outro código.
- A tabela aditiva `recebimentos_qr` armazena código, versão do pedido, origem do link,
  nome do recebedor, registro profissional, horário de confirmação e IP. Entregas e assinaturas anteriores
  permanecem nas tabelas originais, sem alteração de dados históricos.
- Para pedidos com QR, a API e a interface bloqueiam a finalização manual pela copeira.
  O login das áreas administrativas e os controles de outras operações permanecem vigentes.

## Impressão e validação

O QR é desenhado junto do texto no raster ESC/POS, em preto e branco, com módulos inteiros
e margem branca. A fonte da filipeta permanece em 10 pontos; etiquetas não são alteradas.
Utiliza-se [qrcode 8.2](https://pypi.org/project/qrcode/8.2/), com leitura independente do
raster de teste por [ZXing-C++](https://github.com/zxing-cpp/zxing-cpp/tree/master/wrappers/python).

Testes usam dados fictícios, SQLite e PostgreSQL descartáveis, com transporte de impressão
simulado. A homologação inclui confirmação pelo celular simulado, desativação/ativação do
botão conforme preenchimento e atualização automática da cozinha. Esses testes não
acionam impressoras físicas nem modificam refeições reais.

Na validação inicial: suíte completa do backend com 279 casos, 274 aprovados
e 5 verificações externas omitidas. Na inclusão do nome: regressões do QR com 20 casos
aprovados (SQLite e PostgreSQL, incluindo migração de recebimentos antigos e concorrência),
9 testes de relatórios, 18 testes do fluxo anterior de entregas e 74 testes do frontend aprovados.
Build aprovado e lint com somente os dois avisos preexistentes em `Gestao.jsx`.
Os logs e prévias ficam em `work-recebimento-qr-*.log`, `work-recebedor-*.log`
e `work/validacao-recebimento-qr/`.
