# Recebimento por QR Code

Nas novas filipetas, o rodapé **ENTREGA À RECEPÇÃO** traz um QR Code no lugar das linhas
de assinatura e data/hora. O recebedor escaneia o código com o celular, informa seu registro
profissional e toca em **Confirmar recebimento**. A confirmação altera a refeição de
**Pronto** para **Entregue** e usa a data/hora do servidor. A cozinha e o painel de entregas
recebem a atualização, e os relatórios e exportações mostram o registro profissional informado.

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
- A página exibe apenas unidade, número e situação da refeição. O registro profissional
  fica disponível nos relatórios autenticados, sem expô-lo em consultas públicas.
- O botão exige registro preenchido; o servidor só aceita pedidos prontos, de unidade ativa.
  Códigos inválidos, substituídos e pedidos cancelados não registram entrega.
- Confirmações repetidas preservam o primeiro registro e horário. O bloqueio do pedido
  coordena confirmação, cancelamento e impressão. Uma correção dos dados gera outro código.
- A tabela aditiva `recebimentos_qr` armazena código, versão do pedido, origem do link,
  registro profissional, horário de confirmação e IP. Entregas e assinaturas anteriores
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

Na validação desta alteração: suíte completa do backend com 279 casos, 274 aprovados
e 5 verificações externas omitidas; regressões finais do QR com 16 casos aprovados;
18 testes do fluxo anterior de entregas aprovados; frontend com 73 casos aprovados.
Build aprovado e lint com somente os dois avisos preexistentes em `Gestao.jsx`.
Os logs e prévias ficam em `work-recebimento-qr-*.log` e `work/validacao-recebimento-qr/`.
