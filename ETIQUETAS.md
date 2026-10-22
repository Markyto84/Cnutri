# Etiquetas de refeições — 89 mm × 36 mm

## Uso na cozinha

Em **Cozinha → Prontos**, use **Etiqueta** no cartão do paciente. A prévia contém,
nesta ordem: **Unidade, Matrícula, Nome, Data de nascimento, Dieta, Andar e Leito**.
O rodapé traz **CONSUMO IMEDIATO** e o ícone da aba do navegador aparece como marca
d'água. Confira a prévia e pressione **Imprimir etiqueta**. Reimpressões usam o mesmo botão.

O botão aparece somente para Cozinha, Nutrição ou TI autorizados na unidade, em
pedidos prontos com nome de paciente. Pedidos médicos sem paciente não exibem esse
botão. Campos antigos não preenchidos aparecem como **Não informado**; a matrícula
é obtida do formulário, preservando zeros à esquerda. O nascimento é exibido em
dia/mês/ano; a dieta corresponde ao nome da dieta cadastrada no pedido, o andar ao
formulário e o leito ao registro do paciente.

A etiqueta é solicitada pelo operador; mudar o status para Pronto habilita o botão.
A API recusa etiquetas de pedidos pendentes, em preparo, entregues ou cancelados.
O consumidor confere novamente o status antes do envio. Durante a transmissão TCP,
o bloqueio da linha do pedido mantém o status Pronto; entrega ou cancelamento desse
pedido aguarda o fim da transmissão. Outros pedidos continuam independentes.

## Configuração pela TI

Abra **Administração → Impressoras**, selecione a unidade e vá até **Impressora de
etiquetas**. A configuração da filipeta continua na parte superior da mesma tela.

| Campo | Uso |
|---|---|
| Marca e modelo | Identificação do equipamento Gainsha/Gainscha, Tally Dascom ou outro compatível. |
| IP | Endereço da impressora na rede. Vazio mantém etiquetas desativadas. |
| Porta TCP | Padrão 9100; configurável de acordo com o equipamento. |
| Protocolo | ZPL ou TSPL/TSC; selecionar a linguagem ativa no modelo instalado. |
| Resolução | 203 ou 300 dpi, conforme a cabeça de impressão. |
| Espaço entre etiquetas | Em milímetros, para TSPL; padrão de 2 mm, ajustável de 0 a 10. |

O formato é fixo em **89 mm × 36 mm**. Salve antes de usar **Testar conexão de
etiquetas**. Esse teste abre e fecha uma conexão TCP; não imprime nem confirma a
compatibilidade da linguagem ou a calibração do papel. A impressora precisa estar
com a mídia, sensor e protocolo configurados para o rolo instalado.

Os modelos e IPs ainda não foram informados pelo usuário. Nenhum endereço de
impressora de etiquetas é preenchido automaticamente na instalação em uso.
A homologação física fica para quando os equipamentos forem cadastrados.

## Texto e protocolos

O servidor desenha os sete campos usando as fontes distribuídas no projeto e
envia uma imagem monocromática. Assim, acentos não dependem da tabela interna de
caracteres da impressora. A fonte adapta-se de 10 a 7 pontos para caber; se o texto
exceder o espaço mesmo na menor fonte, o trabalho falha com orientação para revisar
o conteúdo. Nomes e dietas não são cortados silenciosamente. O rodapé possui espaço
reservado e fonte de 9 pontos.

A marca d'água usa uma cópia do mesmo arquivo do favicon, distribuída nos assets do
backend. Sua retícula suave de pontos pretos permanece visível nos protocolos
monocromáticos; o texto é desenhado por cima, com contorno branco para manter a leitura.
A prévia usa os mesmos pixels que a impressão, em 203 ou 300 dpi.

ZPL usa `^GFA`, com dados hexadecimais e um exemplar por envio, conforme o
[manual oficial da Zebra](https://cpws.zebra.com/cpws/docs/zpl/zpl-zbi2-pm-en.pdf).
TSPL usa `SIZE`, `GAP`, `BITMAP` e `PRINT`, conforme o
[manual oficial da TSC](https://fs.tscprinters.com/en/dl/1/2541).
A [documentação de desenvolvimento da Gainscha](https://gainscha.github.io/) possui
referências para as duas linguagens. A marca sozinha não determina o protocolo
ativo; é necessário conferir o modelo e a emulação antes de imprimir em papel.

## Fila, segurança e atualização

- Etiquetas e filipetas usam trabalhos independentes na fila persistida. Cada pedido
  pode ter um trabalho ativo de cada tipo; cliques repetidos retornam o trabalho ativo.
- A configuração da impressora é copiada para o trabalho da etiqueta. Alterar IP,
  protocolo ou resolução depois afeta novos trabalhos; uma tentativa pendente conserva
  o documento e a impressora originais.
- Há até três tentativas para falhas antes de conectar. Transmissões interrompidas
  exigem conferir o papel e confirmar outra cópia. **Enviado** confirma transmissão TCP,
  sem garantir saída física ou impressão correta do equipamento.
- Matrícula e nascimento não são acrescentados ao dashboard ou ao WebSocket público. A imagem da
  etiqueta exige autenticação/perfil/unidade e usa `Cache-Control: private, no-store`.
  A prévia do navegador é descartada ao fechar a caixa.
- A inicialização cria `impressoras_etiquetas` e acrescenta `tipo_documento` e
  `configuracao` em `trabalhos_impressao`. Trabalhos anteriores permanecem FILIPETA,
  com seus dados/estados preservados; não são criadas etiquetas de pedidos históricos.
- A atualização do layout de 22/10/2026 não requer mudança de banco. Documentos já
  renderizados na fila conservam seus bytes originais; novos documentos usam os sete campos.
- A API permanece com um worker. A atualização não modifica credenciais, formulários,
  pedidos, entregas, comprovantes ou a configuração das impressoras térmicas.

Backup local anterior à atualização do layout:
`backups/backup-dietas-2026-10-22-antes-layout-etiquetas.dump`, fora
do Git. A leitura do catálogo é conferida com `pg_restore --list`; não substitui um
teste de restauração completo.

Validação do layout de 22/10/2026: 93 testes de backend, incluindo oito em schemas PostgreSQL exclusivos,
onze testes de frontend e build aprovados. Lint mantém dois avisos anteriores em
`Gestao.jsx`. A fila e as transmissões são verificadas com impressoras simuladas;
nenhuma impressão física de teste é feita nesta etapa.

A prévia, o botão restrito a Prontos, o enfileiramento e o cadastro da TI foram
conferidos no navegador com dados fictícios; o diálogo também foi verificado em
largura de celular de 390 pixels. Na aplicação em uso, a migração foi aplicada com
backup e comparação de integridade antes/depois; API e frontend responderam HTTP
200 no IP da rede após a atualização.

Em 22/10/2026, a nova prévia com os sete campos, rodapé e marca d'água foi conferida
no painel com dados fictícios. O reinício da aplicação preservou integralmente as
14 tabelas conferidas, incluindo credenciais, impressoras e trabalhos de impressão.
