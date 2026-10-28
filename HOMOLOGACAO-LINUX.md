# Ceres Care — instalação em etapas e homologação no Linux

Homologar é executar e registrar os testes do fluxo real no servidor de destino,
com participação da TI e das equipes que usarão o sistema. Testes automatizados e
validação dos arquivos Docker ajudam, mas a aprovação de equipamentos, rede e
certificados depende desse ambiente.

## HTTPS depois da instalação

Para instalações novas, o [assistente inicial](INSTALACAO-SERVIDOR.md) centraliza
IP/DNS, protocolo e portas em `work/servidor.env`. A ativação posterior do HTTPS
usa esse mesmo assistente. A configuração manual abaixo permanece como alternativa.

A instalação base usa `docker-compose.prod.yml`. O HTTPS é uma etapa separada,
ativada pelo complemento `docker-compose.https.yml`, sem reinstalar o banco.
O modelo público `infra/https.env.example` organiza domínio, pasta do certificado
e endereço dos novos QR Codes. Sua cópia privada fica em `work/https-linux.env`,
fora do Git. O roteiro está em [HTTPS.md](HTTPS.md#linuxdocker--servidor-de-destino).

A preparação inicial pode usar HTTP com acesso restrito à TI. A homologação do
acesso às contas e do atendimento deve ocorrer no endereço HTTPS definitivo.
O login AD exige HTTPS e LDAPS já na implementação atual.

Antes de ativar, a TI configura o DNS e disponibiliza certificado/cadeia e chave
válidos para o nome escolhido. A confiança da CA precisa existir nos computadores,
celulares e tablets. A ativação não faz cadastro DNS nem instala uma CA nos dispositivos.

## Ambiente e registro da homologação

- Usar uma instalação de homologação com projeto Compose e volume próprios,
  contas e pedidos fictícios. A mesma lista será conferida no destino definitivo.
- Sincronizar o relógio do Linux por NTP; conferir que relatórios exibem Brasília.
- Registrar versão da aplicação, servidor, data, responsável, equipamentos,
  resultado esperado/obtido e evidências. Evidências usam dados fictícios.
- Separar impressoras de teste ou uma janela combinada com a cozinha. Uma cópia
  restaurada do banco não deve iniciar o consumidor de impressão automaticamente.

## 1. Login e permissões

Conferir no computador e no celular:

1. Conta local válida entra; senha incorreta é recusada. Usar uma conta de teste
   para conferir a limitação de tentativas, sem bloquear contas das equipes.
2. Administrador de TI, Gestão de Nutrição e Copeira chegam aos respectivos painéis
   e acessam somente as funções/unidades autorizadas. A cozinha continua operando
   diretamente, conforme o fluxo público autorizado do projeto.
3. Conta inativa não entra; saída e expiração de sessão exigem novo acesso.
   Troca obrigatória de senha ocorre apenas nas contas marcadas para isso.
4. Se o AD for ativado e parametrizado no ambiente Linux: conferir LDAPS com a CA,
   usuário vinculado, conta de rede inativa e resposta à indisponibilidade do AD.
   Domínio, CA e conectividade são distintos do certificado HTTPS da aplicação.

Aprovado quando o acesso funciona e as restrições de perfil/unidade são mantidas.

## 2. Filipetas e etiquetas

1. Testar a conexão a cada IP/porta a partir da rede dos contêineres. Uma conexão
   TCP aceita não comprova que a impressora entende os comandos ou imprime papel.
2. Solicitar uma refeição fictícia e conferir a filipeta física: acentos (ã, õ, ç, á),
   todos os campos previstos no layout, restrições e QR Code legível.
3. Marcar como pronto e conferir a etiqueta física de 89 × 36 mm: nome da unidade
   em 11 pontos, identificação, nascimento/idade, dieta, andar/leito, marca d'água e
   CONSUMO IMEDIATO. Conferir também a etiqueta médica e os dois destinatários.
4. Confirmar que a etiqueta é liberada somente em Pronto. Testar reimpressão manual
   e falha de rede em pedido fictício; conferir fila, mensagem e retomada sem
   reenvio automático de trabalhos com resultado de transmissão incerto.

Aprovado quando o papel sai correto em cada modelo, unidade e caminho de rede.

## 3. Recebimento por QR Code

1. Escanear um QR da filipeta de teste em celular conectado à rede da unidade.
   Conferir que abre o HTTPS sem aviso de certificado e mostra a refeição esperada.
2. Antes de Pronto, o recebimento não pode ser confirmado. Em Pronto, exigir nome
   completo do recebedor e registro profissional.
3. Confirmar e conferir Entregue na cozinha, nas entregas e no relatório, com nome,
   registro e data/hora atribuída pelo servidor. Conferir atualização em tempo real.
4. Repetir a confirmação e verificar que o primeiro recebimento e horário permanecem.
   Conferir recusa de código inválido, substituído e de pedido cancelado.
5. Conferir os códigos emitidos antes da migração: o endereço impresso precisa
   continuar acessível ou redirecionar para o novo. Alterar a configuração não
   reescreve códigos já impressos. Preferir um nome DNS estável desde o início.

O nome e o registro são uma identificação declarada pelo recebedor; esse fluxo não
consulta conselho profissional nem autentica esse recebedor no AD.

## 4. Backup e recuperação

1. A partir de um ambiente de manutenção, gerar um backup consistente do PostgreSQL
   correto e restaurá-lo em banco descartável, sem substituir o banco em uso.
2. Usar a ferramenta existente `backend/validar_recuperacao.py`, com os parâmetros
   do Linux. Ela confere tabelas, registros, hashes, índices, sequências, formulários
   e assinaturas e publica um resumo no monitoramento. O ambiente de manutenção
   precisa alcançar o banco e o contêiner corretos; não montar o socket Docker na API.
3. Em cópia de homologação separada, com impressoras isoladas, abrir a aplicação e
   conferir contas, unidades, consultas e relatórios. Medir o tempo de recuperação.
4. Repetir a recuperação usando uma cópia obtida do destino externo de backups.
   Guardar separadamente configurações privadas, segredos, certificados/chave,
   arquivos de implantação e a versão correspondente da aplicação. O dump do banco
   não contém esses arquivos nem configurações globais de usuários do PostgreSQL.
5. Definir com a TI a frequência/retenção das cópias, a perda máxima de dados admitida
   e o prazo para retorno. Conferir espaço, permissões, falhas e teste periódico.

Aprovado quando os dados e configurações podem ser recuperados dentro do prazo
combinado, com conferências registradas. Um arquivo de backup apenas existente
não comprova uma restauração bem-sucedida.

Detalhes da ferramenta: [Monitoramento e recuperação](MONITORAMENTO-E-RECUPERACAO.md).

## Aprovação no destino

Após corrigir as falhas encontradas, TI e responsáveis operacionais registram a
aprovação. Conferir ainda o retorno dos serviços após reiniciar o servidor de teste.
A conclusão documentada desses passos libera o uso no Linux; este roteiro, sozinho,
não significa que a instalação Linux já foi homologada.
