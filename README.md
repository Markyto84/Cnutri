# Ceres Care — Gestão de Nutrição

**Nutrição e cuidado em cada etapa.**

Plataforma multifilial para solicitação, preparo, entrega e auditoria de dietas hospitalares,
anteriormente chamada Cnutri. A identidade pública usa **Ceres Care** na interface, na aba
do navegador, nos relatórios e nos arquivos exportados. O ícone e a paleta azul são mantidos.

Os endereços já distribuídos, as pastas, o repositório Git, as configurações privadas e os
identificadores de integração continuam compatíveis. A alteração do nome não muda o DNS
reservado pela TI. Consulte a [linguagem visual](UI-ACOLHIMENTO.md).

**Stack:** FastAPI (Python) · React + Vite · PostgreSQL 16 · WebSockets · Impressão ESC/POS · Docker

Administração → **Monitoramento** mostra API, banco, fila de impressão e o último
teste de recuperação. O teste completo de backup em banco temporário e o roteiro
de manutenção estão em [Monitoramento e recuperação](MONITORAMENTO-E-RECUPERACAO.md).

Gestão e Administração → **Pedidos e rastreabilidade** oferece correções com motivo
e histórico por pedido. A seção de prescrição foi removida dos formulários;
informações anteriores permanecem disponíveis para consulta.
Os dashboards públicos mostram número/etapa; dados de pacientes exigem sessão da
unidade. Veja [fluxo e permissões](PRESCRICOES-E-RASTREABILIDADE.md).

Os painéis usam WebSocket com reconciliação condicional a cada dois minutos,
contexto central de unidades/prazos/plantão e recuperação automática de falhas.
Veja [sincronização e redução de consultas](SINCRONIZACAO-OPERACIONAL.md).

Nas novas filipetas, o recebedor escaneia o **QR Code**, informa seu nome e registro profissional
e confirma o recebimento; o servidor registra a entrega e a data/hora. Consulte
[recebimento por QR Code](RECEBIMENTO-POR-QR.md). A [entrega direta](ENTREGA-DIRETA.md)
permanece para filipetas anteriores sem QR.
O [módulo de assinatura](MODULO-ASSINATURA.md) permanece disponível para futura reativação.

---

## Estrutura do projeto

Pasta única de desenvolvimento nesta estação: `C:\Users\Suporte\Documents\Projeto Cnutri`.
Ela contém o repositório `Markyto84/Cnutri`, com o histórico Git e as correções locais mais recentes.
Os caminhos anteriores do LM Studio e da cópia do Codex apontam para esta mesma pasta.

```
Projeto Cnutri/
├── backend/                  # API FastAPI (app/), Dockerfile
├── frontend/                 # SPA React (src/), Dockerfile + nginx.conf
├── configuracoes/            # Cópias versionadas dos esquemas de formulário
├── backups/                  # Backups locais do banco (fora do Git)
├── work/                     # Logs e processos locais (fora do Git)
├── docker-compose.yml        # Desenvolvimento (só o PostgreSQL)
├── docker-compose.prod.yml   # Produção (banco + backend + frontend)
├── start.ps1                 # Inicia o ambiente Windows
└── stop.ps1                  # Para os processos desta cópia
```

## Como rodar em um servidor Linux

Há um [assistente de configuração inicial](INSTALACAO-SERVIDOR.md) para definir
IP/DNS, protocolo e porta da instalação, gerar os arquivos privados e iniciar os
serviços com a mesma configuração. O painel de TI mostra o destino em **Servidor
da aplicação**; atalhos e novos QR Codes seguem o endereço definido.

```sh
sh ./servidor.sh configurar
sh ./servidor.sh validar
sh ./servidor.sh iniciar
```

O procedimento manual abaixo continua disponível para instalações anteriores.

O item 10 do review (HTTPS com domínio/certificado da TI e preparação operacional)
foi adiado para o novo servidor. O roteiro Docker abaixo é a base existente e ainda
precisa dessa etapa antes da implantação definitiva. A API deve usar **um único
worker**, como fixado no Dockerfile, enquanto os eventos WebSocket estiverem em memória.

### 1. Instalar o Docker (se ainda não tiver)

```bash
curl -fsSL https://get.docker.com | sh
sudo systemctl enable --now docker
```

### 2. Copiar o projeto para o servidor

Por exemplo, com `scp` (a partir da máquina Windows):

```powershell
scp -r projeto-dietas-hospitalares usuario@IP-DO-SERVIDOR:/opt/
```

### 3. Criar o arquivo privado de variáveis (obrigatório)

Na pasta do projeto no servidor, crie um `.env`:

```bash
cd /opt/projeto-dietas-hospitalares
umask 077
cnutri_admin_inicial=''
until [[ "$cnutri_admin_inicial" =~ [A-Z] && "$cnutri_admin_inicial" =~ [0-9] && "$cnutri_admin_inicial" =~ [^[:alnum:][:space:]] ]]; do
  cnutri_admin_inicial=$(openssl rand -base64 9)
done
printf 'POSTGRES_PASSWORD=%s\nJWT_SECRET=%s\nADMIN_INICIAL_SENHA=%s\n' "$(openssl rand -hex 24)" "$(openssl rand -hex 48)" "$cnutri_admin_inicial" > .env
unset cnutri_admin_inicial
chmod 600 .env
```

### 4. Subir tudo

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

Isso sobe 3 serviços: **db** (PostgreSQL 16), **backend** (API na porta interna 8000) e **frontend** (nginx na porta 80, que também serve a API e o WebSocket via proxy).

### 5. Acessar

Na primeira inicialização, o sistema cria as tabelas e o **seed inicial**:

| Tela | URL |
|---|---|
| Kiosk (enfermagem/médico) | `http://IP-DO-SERVIDOR/unidade-havai` |
| Cozinha (Kanban) | `http://IP-DO-SERVIDOR/cozinha/unidade-havai` |
| Entregas das copeiras | `http://IP-DO-SERVIDOR/entregas/1` |
| Administração | `http://IP-DO-SERVIDOR/admin` |
| Login | `http://IP-DO-SERVIDOR/login` |

Distribua um atalho com a URL específica de cada unidade. Os formulários e cozinhas abrem
diretamente, sem página de seleção de unidade. O endereço principal apenas orienta a usar
o atalho fornecido pela TI, sem escolher ou redirecionar para uma unidade.
Em **Administração → Unidades**, use **Baixar atalho (.url)** na unidade desejada.
Após criar ou editar uma unidade, o painel também mostra o endereço salvo e seu download.
O arquivo usa o domínio/IP, protocolo e porta do endereço pelo qual a TI acessou o Ceres Care.
Novos endereços de unidade precisam incluir uma letra e não podem usar rotas reservadas,
como `login` ou `admin`.

Em banco vazio, é criada somente a conta **admin**, com a senha temporária definida em
`ADMIN_INICIAL_SENHA`. Consulte essa variável no arquivo privado local; seu valor não é exibido nos logs.
O primeiro acesso leva à página **Defina sua nova senha**, antes de liberar a administração.
A TI cadastra os demais perfis e unidades pelo painel. Toda senha criada/redefinida pela TI exige troca.

Para atualizar uma instalação antiga, faça backup e execute a migração de credenciais antes de iniciar:

```bash
docker compose -f docker-compose.prod.yml build backend
docker compose -f docker-compose.prod.yml run --rm -v "$PWD/work:/handover" backend python atualizar_seguranca.py --arquivo /handover/acessos-temporarios.txt
```

O comando substitui somente a senha pública das versões antigas. Senhas já personalizadas são preservadas.
Entregue os acessos do arquivo privado aos responsáveis pela TI. O arquivo não deve entrar no Git.

### 6. Comandos úteis

```bash
docker compose -f docker-compose.prod.yml logs -f backend   # ver logs
docker compose -f docker-compose.prod.yml down              # parar (dados ficam no volume)
docker compose -f docker-compose.prod.yml up -d --build     # atualizar após mudanças no código
docker exec dietas-db-prod pg_dump -U dietas dietas > backup.sql   # backup do banco
```

## Impressoras térmicas (ESC/POS)

No painel **Administração → Impressoras**, escolha a unidade e informe o IP da impressora térmica.
Clique em **Salvar impressora** e depois em **Testar conexão** para verificar a porta 9100 sem imprimir.
O servidor precisa **alcançar a impressora pela rede** (TCP porta 9100). Para testar conectividade a partir do servidor:

```bash
nc -zv IP-DA-IMPRESSORA 9100
```

A filipeta inclui os dados do solicitante e os campos dos formulários Médico e Enfermagem,
com os rótulos e a ordem configurados para cada unidade. **Sexo** e **Prontuário** são omitidos somente
na impressão; os valores continuam nos formulários e no pedido. Campos adicionados pelo gestor passam a sair
na impressão; valores antigos continuam visíveis mesmo se o campo for removido da configuração.
Campos configurados sem resposta mostram **Não informado**. Datas são apresentadas como `DD/MM/AAAA`,
dietas pelo nome e textos longos quebram conforme a largura do papel, sem truncar refeições,
nomes ou observações.

A fonte da filipeta usa **10 pontos** (28 pixels a 203 dpi), inclusive nos rótulos e nas observações.
Cabeçalhos e alertas mantêm o negrito. A largura útil comporta 31 caracteres por linha nesse tamanho;
o espaçamento entre linhas e a quebra dos textos são calculados pelas métricas da fonte.

Ao final dos dois tipos de filipeta, o bloco **Entrega à recepção** exibe o QR Code de recebimento
quando o endereço público está configurado. O recebedor informa nome e registro profissional no
celular; o servidor registra a data/hora da confirmação. Instalações sem essa configuração
mantêm as linhas de assinatura e data/hora para preenchimento manual.

O texto é desenhado no servidor com **Pillow e DejaVu Sans Mono**, incluindo `ã, õ, ç, á`, e enviado
como imagem monocromática ESC/POS em blocos de até 128 linhas de pixels. Assim, os acentos não dependem
da tabela de caracteres interna da POS80. A área usada é de 576 pontos em papel de 80 mm; a impressora
deve aceitar [impressão raster GS v 0](https://download4.epson.biz/sec_pubs/pos/reference_en/escpos/gs_lv_0.html).
As fontes e sua licença ficam em `backend/app/assets/fonts/`, incluídas também na imagem Docker.
Essa conversão acontece somente na impressão; os textos digitados permanecem preservados no banco.

O envio automático e o botão de reimpressão da Cozinha usam o mesmo gerador. A reimpressão consulta
os rótulos atuais da unidade e conserva todos os dados salvos no pedido. O alerta de restrição severa
e o corte de papel são mantidos. O informativo de horários do formulário não é repetido na filipeta.

## Segurança de acesso

A API exige segredo JWT exclusivo de pelo menos 32 caracteres, sem valor padrão.
A produção recusa a senha padrão do banco, credencial de banco com menos de 12 caracteres e contas
ativas ainda usando a senha inicial antiga. O Compose de produção exige as variáveis do banco e JWT.
O backend de produção fica na rede interna do Docker; somente o nginx publica portas e substitui
os cabeçalhos de origem para a limitação de autenticação por IP.

O dashboard da cozinha permite consultar dados de preparo, mudar etapas, cancelar com motivo,
reimprimir e emitir etiquetas sem login. Usa rotas próprias em `/api/cozinha` e canal
`/ws/cozinha-publica/{id}`, com resumo operacional dos pedidos da unidade ativa.
A lista de entregas mostra somente número e etapa sem login; seus dados detalhados exigem
conta autorizada da unidade.
Registrar entrega exige Copeira (somente a própria entrega), Nutricionista ou Admin TI.
A gestão seleciona uma copeira online; o relatório identifica a copeira e quem registrou a ação.

Após cinco falhas para um usuário no mesmo IP em 15 minutos, o login fica limitado até terminar
a janela; há também limite geral de 100 falhas por IP. Os registros ficam no banco e os logs não
contêm senhas nem tokens. Logout encerra a sessão; troca/reset de senha revoga sessões anteriores.
Senhas novas têm **de 8 a 12 caracteres**, com pelo menos **uma letra maiúscula, um número
e um caractere especial**. Espaço não conta como caractere especial. A regra vale no cadastro,
na redefinição pela TI e na troca em `/senha`; as senhas temporárias geradas usam 12 caracteres.
Senhas existentes continuam válidas até serem trocadas, inclusive as que têm mais de 12 caracteres.

Veja [Segurança — itens 1 a 3](SEGURANCA-ITENS-1-3.md) para permissões, regras do formulário e validação.
A preparação de HTTPS, recuperação automática dos serviços e agenda de cópias externas permanece no item 10 do review,
adiado pelo usuário para outro servidor. Os itens 4–9 estão descritos em
[Estabilização — itens 4 a 9](ESTABILIZACAO-ITENS-4-9.md).

O monitoramento e o teste de recuperação local do banco foram implementados em
26/10/2026: [procedimento e validação](MONITORAMENTO-E-RECUPERACAO.md).

## Desenvolvimento (Windows)

Com Docker Desktop, Python 3.12 e Node.js instalados, execute na pasta do projeto:

```powershell
Set-Location 'C:\Users\Suporte\Documents\Projeto Cnutri'
.\start.ps1
```

O script inicia o PostgreSQL na porta **5433**, a API na **8000** e o frontend na **5173**.
Na primeira execução, cria o ambiente Python e instala as dependências que estiverem ausentes.
O script também prepara `backend/.env` com segredos aleatórios e acesso restrito ao usuário do Windows e ao SYSTEM.
Em instalações antigas, execute `backend\.venv\Scripts\python.exe backend\atualizar_seguranca.py` após o backup e antes de reiniciar a API.
O caminho do arquivo privado com as senhas temporárias é informado sem revelar os valores.
Execuções seguintes reutilizam os processos desta pasta. Os logs ficam em `work/logs/`.
Quando precisa iniciar a API ou o frontend, usa uma sessão independente do terminal, via WMI.
Fechar ou interromper o terminal de desenvolvimento não encerra esses serviços. Isso não configura
inicialização automática após reiniciar o Windows; use `start.ps1` novamente nessa situação.

- Formulário: `http://localhost:5173/unidade-havai`
- Cozinha: `http://localhost:5173/cozinha/unidade-havai` (consulta e operação sem login)
- Entregas: `http://localhost:5173/entregas/1`
- Login: `http://localhost:5173/login`
- Pela rede: `http://IP-DESTA-MAQUINA:5173/unidade-havai`

Para encerrar ou reinstalar dependências:

```powershell
.\stop.ps1                         # encerra frontend e API
.\stop.ps1 -PararBanco             # encerra também o PostgreSQL
.\start.ps1 -InstalarDependencias  # reinstala com os serviços parados
```

O Compose de desenvolvimento mantém o nome `projeto-dietas-hospitalares`, associado ao volume
`projeto-dietas-hospitalares_pgdata`. Assim, mudar a pasta de trabalho preserva o banco existente.

O tema corporativo usa **Blue `#0070AD`** nas ações principais e **Vibrant Blue `#17ABDA`** nos
destaques e ações de entrega/exportação. O fundo neutro suave é `#F4F7F8`,
com painéis brancos e campos em tons claros. O texto é branco sobre o azul principal e azul profundo
`#06344B` sobre o azul vibrante, com contraste de 5,36:1 e 4,92:1, respectivamente.
As cores ficam centralizadas em `frontend/src/cuidado.css`, importado pelo `index.css`: `brand`, `brand-vibrant`, `brand-ink`,
variantes de foco/hover, `app-background`, `panel` e escala `slate` com tons azulados. Formulários,
login, gestão, administração, relatórios, cozinha e entregas compartilham essa paleta. Alertas de
restrição/erro, avisos e indicadores de produção continuam identificados por suas cores funcionais.

A [linguagem visual de acolhimento](UI-ACOLHIMENTO.md) reúne tipografia local, ícones SVG,
formas suaves, navegação e formulários responsivos. A interface funciona sem fontes ou CDNs externos.

No painel **Gestão de Nutrição → Formulários → Médico**, edite as listas de **Refeição**, **Suco**,
**Sobremesa** e **Local de entrega**, com uma opção por linha em cada campo, e publique o formulário.
Essas listas alimentam o formulário médico, preservando a ordem e a obrigatoriedade dos campos.
As opções são salvas no banco de dados, sem alterar as dietas ou o formulário de Enfermagem.

A Nutrição edita títulos, avisos, cardápios e opções das listas. Os controles de nome,
tipo, obrigatoriedade, inclusão, remoção e restauração dos campos ficam disponíveis somente
ao perfil `ADMIN_TI` na gestão. A API também impõe essa separação de permissões.

**Líquido espessado** usa as opções **Sim / Não**. Em Sim, **Líquidos disponíveis** aparece
e exige uma opção da lista configurada pela Nutrição. Em Não, a escolha anterior é descartada.
A lista continua editável em **Formulários → Enfermagem / Paciente → Opções das listas**.
O líquido escolhido acompanha o pedido nos painéis, na filipeta e nos relatórios/exportações.
Cadastros e pedidos antigos são preservados; clientes anteriores que enviam diretamente
NÉCTAR, MEL ou PUDIM são convertidos para Sim e o respectivo líquido ao criar/corrigir o pedido.

O botão **Cancelar** da cozinha abre uma caixa com motivo obrigatório de 5 a 1.000 caracteres.
Todas as rotas de alteração de status exigem o motivo. O painel sem login registra
**Painel da cozinha (sem login)** e o horário do servidor; rotas autenticadas preservam a conta
que realizou a ação. O relatório distingue **Solicitante** de **Cancelado por**, mostra o
motivo e a data/hora, e inclui esses dados em XLSX, ODS e CSV. Cancelamentos antigos sem motivo
continuam identificados como não registrados na época, sem preencher informações fictícias.

O cabeçalho identifica **Cozinha sem login**. **Iniciar preparo**, **Marcar pronto**, cancelamento,
filipetas e etiquetas funcionam diretamente, inclusive quando há uma sessão de Copeira ou uma
credencial expirada no navegador. A cozinha usa conexão independente da sessão pessoal.
Etapas e unidade continuam validadas pelo servidor; etiquetas exigem status Pronto e envios
incertos exigem conferência antes de repetir. Veja [COZINHA-SEM-LOGIN.md](COZINHA-SEM-LOGIN.md).

## Painel de administração

O perfil **Administrador** entra diretamente em `/admin` após o login e tem acesso a todas as unidades.

- **Unidades:** criar, editar, ativar ou desativar unidades; abrir o formulário e o painel da cozinha;
  acessar a gestão de dietas, refeições, formulários e relatórios da unidade escolhida. Novas unidades
  recebem cópias independentes dos formulários e das dietas da unidade de origem selecionada.
- **Credenciais:** criar e editar nome, nome de usuário, senha, perfil e unidades de acesso; ativar ou desativar
  contas. Os perfis disponíveis são Administrador, Gestor de nutrição, Cozinha e Copeira. A própria conta
  administrativa não pode ser desativada nem perder seu perfil pelo mesmo usuário.
- **Impressoras:** associar uma impressora padrão por unidade, alterar/remover o IP e testar a conexão.
- **Relatórios:** consultar e exportar dietas e refeições médicas de uma unidade ou de todas as unidades.

Gestão, administração, relatórios e o canal interno autenticado continuam verificando perfil e
unidades permitidas. O administrador pode retornar ao painel pelo link **Administração** nas telas
de Gestão e Cozinha.

### Login por nome de usuário

O acesso em `/login` usa **Usuário** e **Senha**. Em **Administração → Credenciais**, o administrador
de TI define o **Nome de usuário** de cada pessoa, separado do nome completo. Não é necessário
cadastrar e-mail. O nome de acesso deve ter de 3 a 50 caracteres, começar por letra ou número e
conter apenas letras sem acento, números, ponto, hífen ou sublinhado. Maiúsculas e minúsculas são
equivalentes; o cadastro salva o nome em minúsculas e bloqueia nomes já usados por outra conta.

Na atualização de uma base PostgreSQL existente, a inicialização cria o campo `nome_usuario` e
preenche as contas com o texto anterior ao `@` do e-mail antigo. Acentos e caracteres inválidos são
normalizados; colisões recebem um sufixo com o ID, e nomes muito curtos recebem `usuario{ID}`.
O administrador pode alterar esses nomes depois. Senhas, IDs, perfis, vínculos, sessões e históricos
são preservados; e-mails antigos ficam no banco como dados legados e deixam de servir para login.
Executar a migração novamente preserva os nomes já definidos pela TI. A unicidade também é
verificada no banco, sem diferenciar maiúsculas e minúsculas.

## Relatório de dietas por período e exportação

Em **Gestão de Nutrição → Relatórios** ou **Administração → Relatórios**, informe a data e hora
inicial e final e clique em **Consultar dietas**. Os horários usam Brasília (UTC-3), incluindo
todo o minuto final selecionado. Escolha se o período corresponde à **solicitação** ou à
**entrega** e, opcionalmente, filtre por formulário (Enfermagem ou Médico) e situação.
O gestor consulta a unidade selecionada entre as suas unidades permitidas. O administrador
pode escolher uma unidade, inclusive inativa, ou consultar todas.

O relatório apresenta totais, resumo por unidade/dieta e solicitações em páginas de 25 registros.
Em **Abrir relatório em**, escolha o formato e clique em **Exportar relatório**:

- **Excel (.xlsx):** duas abas, **Resumo** e **Solicitações**, com números e datas tipados,
  cabeçalhos fixos, filtros e textos com quebra de linha.
- **LibreOffice Calc (.ods):** as mesmas duas abas em formato OpenDocument, com datas e números tipados.
- **Google Sheets (.csv):** registros detalhados em UTF-8 com acentos, para abrir no Google Sheets
  em **Arquivo → Importar**. O arquivo é baixado; não há envio automático a uma conta Google.

Os arquivos incluem **todos os resultados dos filtros**, mesmo os de outras páginas. Alterar um
filtro exige consultar novamente antes de exportar. O detalhamento inclui dieta, refeição,
cardápio, equipe, suco, sobremesa, local/leito, observações, horários de solicitação/preparo/entrega,
copeira, recebedor e indicação de assinatura registrada. A imagem da assinatura continua no
relatório de comprovantes; prontuário, sexo, nascimento e matrícula não são exportados.
Textos que se parecem com fórmulas são tratados como texto. Se um campo exceder o limite de
32.767 caracteres do Excel, o sistema orienta usar CSV ou ODS, preservando o conteúdo completo.

A consulta e os três formatos verificam perfil e unidades permitidas no servidor. A funcionalidade
usa `openpyxl` e `odfpy`, incluídos em `backend/requirements.txt`. Ao atualizar uma instalação existente,
pare os serviços e execute `start.ps1 -InstalarDependencias` para instalar essas dependências.

## Paciente e acompanhante

No formulário **Enfermagem / Paciente**, o campo **Para** controla as escolhas:

| Para | Dieta e cardápio |
|---|---|
| Paciente | Mantém as dietas e o cardápio correspondente à dieta selecionada. |
| Acompanhante | Seleciona somente a dieta GERAL e as opções do grupo dessa dieta. |
| Paciente e Acompanhante | Mantém a dieta/cardápio do paciente e exige um **Cardápio do acompanhante**, abaixo do cardápio principal, com opções do grupo GERAL. |

Ao trocar o destinatário ou a dieta, escolhas incompatíveis são limpas e o campo
oculto do acompanhante é retirado do envio. A API valida as mesmas regras antes
de registrar o pedido ou enfileirar a impressão. Se GERAL estiver inativa ou sem
cardápio, o envio com acompanhante fica bloqueado com orientação para a Nutrição.

A Gestão edita as opções em **Formulários → Enfermagem / Paciente → Grupos do
Cardápio**, no grupo que contém GERAL. O campo do acompanhante é derivado desse
cadastro, sem uma segunda lista para manter. A regra vale para as unidades que
possuem os campos Para, Tipo de Dieta e Cardápio, inclusive unidades novas.
O cardápio adicional é salvo em `dados_dinamicos.cardapio_acompanhante` e aparece
na cozinha, nas entregas, na filipeta e no relatório (tela, XLSX, ODS e CSV).
Continua sendo uma solicitação com os dois cardápios; o resumo conta solicitações.
Não há mudança de banco ou de pedidos anteriores.

## Etiquetas para refeições prontas

Em **Administração → Impressoras → Impressora de etiquetas**, a TI configura marca/modelo,
IP, porta, protocolo ZPL ou TSPL, resolução e intervalo do papel por unidade. O tamanho é
**89 mm × 36 mm**. O cadastro é independente da impressora térmica das filipetas.

Na cozinha, o botão **Etiqueta** aparece nos pedidos de pacientes e de profissionais
em **Prontos**, para operadores autorizados. Para pacientes, a prévia inclui unidade, matrícula, nome, data de nascimento,
dieta, andar e leito, com **CONSUMO IMEDIATO** no rodapé e o ícone da aplicação como
marca d'água.
No formulário médico, uma etiqueta identifica unidade, profissional, registro,
equipe/horário, refeição, suco/sobremesa e local de entrega. Ela usa o nome do
solicitante e dispensa dados de paciente; atende às equipes Médica e Administração.
Para **Acompanhante**, a etiqueta traz dieta GERAL e a palavra **Acompanhante**
à direita na linha do leito. Para **Paciente e Acompanhante**, o mesmo clique
envia duas etiquetas distintas, uma de cada tipo; o diálogo mostra ambas antes
do envio. Reimprimir repete o conjunto completo, com conferência obrigatória
quando o envio anterior tiver sido interrompido.
O servidor valida o status antes de enfileirar e antes do envio. Veja [ETIQUETAS.md](ETIQUETAS.md)
para configuração, estados da fila, privacidade e homologação no equipamento.

## Confirmação de pedidos e fila de impressão

O kiosk mostra **Pedido #n registrado** e o estado do envio à impressora separadamente.
Uma queda de rede permite repetir a tentativa com a mesma chave, retornando o pedido
original. A confirmação pode ser recuperada ao recarregar a página. **Nova solicitação**
ou o retorno automático após 20 segundos inicia outra tentativa.

A fila fica no banco e é processada em segundo plano. A cozinha mostra os estados
pendente, processando, enviado, falha e envio incerto. Falhas de conexão permitem até
três tentativas; transmissões interrompidas exigem conferir o papel antes de reenviar.
**Enviada à impressora** confirma transmissão TCP, sem afirmar que o papel saiu.
Pedidos anteriores à atualização não são impressos automaticamente. Veja as regras
de reenvio e compatibilidade da API em [ESTABILIZACAO-ITENS-4-9.md](ESTABILIZACAO-ITENS-4-9.md).

## Cozinha, plantão e entregas no computador e no celular

O dashboard `/cozinha/{nome-da-unidade}` e a página `/entregas/{id}` abrem sem login para unidades ativas.
As cozinhas usam o identificador já cadastrado na unidade, como `/cozinha/unidade-havai`,
`/cozinha/unidade-colorado` e `/cozinha/unidade-dubai`. Endereços numéricos anteriores,
como `/cozinha/1`, continuam funcionando e redirecionam para o nome correspondente.
Links da administração, gestão, entregas e seletor de unidade usam o novo formato.
Na cozinha, os pedidos passam por **Pendentes → Em preparo → Prontos**. No celular, botões de etapa
mostram uma coluna por vez; no computador, as três colunas aparecem juntas. A página de entregas
mostra somente as refeições prontas. As novas filipetas são finalizadas pelo recebedor,
via **QR Code**, com nome e registro profissional. A entrega pela copeira permanece nos pedidos
anteriores sem QR. Ambas usam botões de toque
de pelo menos 44 pixels e a caixa de seleção se ajusta à largura da tela.

Para cadastrar uma copeira, abra **Administração → Credenciais**, escolha o perfil **Copeira** e
vincule as unidades de trabalho. Nenhuma conta de copeira é criada automaticamente. Ela acessa
**Entrar no plantão** com a credencial cadastrada; enquanto a sessão estiver conectada, seu nome
fica disponível na unidade selecionada. A presença é renovada a cada 30 segundos. **Sair do plantão**
encerra a sessão imediatamente; fechar o navegador ou perder a conexão remove o nome após até
três minutos sem renovação. Sessões simultâneas da mesma pessoa não duplicam seu nome.

No fluxo anterior, para filipetas sem QR, ao tocar em **Realizar entrega**, a copeira finaliza o atendimento em um único passo, sem
selecionar o próprio nome, preencher recebedor ou assinar. O servidor usa a identidade da sessão,
verifica o plantão e se a refeição continua pronta, registra a entrega e muda o pedido para
**ENTREGUE**. Gestão/TI seleciona uma copeira online e confirma em **Finalizar atendimento**.
A data e hora são registradas pelo banco, sem usar o relógio do dispositivo. O pedido sai das
listas de prontos e de entregas, mantendo histórico e indicadores. Confirmações repetidas ou
concorrentes são bloqueadas. Novas entregas desse fluxo não criam comprovante de assinatura.

Em **Gestão de Nutrição → Relatórios → Entregas e comprovantes de recebimento**, consulte o
destinatário, refeição, copeira, recebedor, local/leito e **data e hora da entrega**. Os filtros
por data e os horários usam Brasília (UTC-3); o relatório tem páginas de até 50 entregas.
**Ver assinatura** abre a imagem do comprovante. A consulta e a imagem exigem perfil de Gestão
ou Administração e acesso à unidade. As assinaturas não são publicadas no dashboard ou no
WebSocket. Entregas sem assinatura continuam visíveis, sem recebedor ou imagem presumidos.

As rotas `/api/operacao` e o WebSocket `/ws/operacao/{id}` fornecem os dados operacionais para
essas telas. Prontuário, registro profissional, matrícula, sexo e data de nascimento não são
publicados nesse canal; a idade é calculada no servidor. O canal interno `/ws/cozinha/{id}` segue
restrito a perfis de operação autorizados. Uma reconciliação condicional a cada dois minutos
complementa o WebSocket; unidades, prazos e plantão são verificados centralmente a cada cinco
segundos. Falhas ativam as consultas de recuperação descritas em SINCRONIZACAO-OPERACIONAL.md.

As tabelas `sessoes_copeiras` e `entregas_pedidos` e o perfil `COPEIRA` são criados na inicialização,
preservando usuários, pedidos e configurações existentes. O backup local anterior a essa atualização
fica em `backups/backup-dietas-2026-10-20-antes-entregas.dump`, fora do Git.

A tabela `recebimentos_entregas`, criada automaticamente na inicialização, guarda o nome do
recebedor e a imagem PNG da assinatura vinculada à entrega. O servidor recebe traços com limites
de quantidade e coordenadas e gera o PNG com Pillow para clientes anteriores que ainda enviem
comprovante completo; rejeita assinaturas parciais ou inválidas. A tela atual dispensa essa coleta.
Os backups do banco incluem os comprovantes. Antes dessa adição foi validado o backup
`backups/backup-dietas-2026-10-20-antes-assinaturas.dump`, também fora do Git.

### Testes da administração, entregas, impressão e relatórios

Os testes usam um banco SQLite temporário em memória, sem modificar o PostgreSQL em uso:

```powershell
Set-Location backend
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

A suíte inclui testes que exigem `CNUTRI_TEST_POSTGRES_URL` apontando explicitamente
para um banco de testes PostgreSQL com permissão para criar schemas. Usam schemas exclusivos,
revertidos ou removidos ao terminar: migrações e verificações de concorrência de
senhas, repetição de pedidos, consumo da fila e status durante o envio da etiqueta. Sem a
variável, os testes PostgreSQL são omitidos; os demais usam SQLite isolado ou verificam
serviços Python sem acessar registros do hospital.
Os testes de entrega cobrem presença por login, saída, expiração, unidades, registro único,
concorrência, proteção do canal interno e preservação do consumo após a entrega. Também verificam
assinatura obrigatória, imagem salva, horário do servidor, acesso ao comprovante, filtros de data
na virada do dia em Brasília, compatibilidade com entregas antigas e reversão em caso de falha.
As verificações de filipeta incluem campos completos nos dois fluxos,
textos extensos, acentos, campos novos/antigos e igualdade entre impressão automática e reimpressão.
Os testes também reconstroem a imagem transmitida e conferem pixels, polaridade, limites dos blocos
e glifos diferentes para letras com e sem acento.
Os testes do novo relatório cobrem limites de data/hora e fuso, unidade/perfil, filtros, paginação,
exportação completa nos três formatos, acentos, datas tipadas, textos que se parecem com fórmulas,
resultado vazio e rejeição de truncamento no Excel.
Os testes de login verificam o acesso por usuário, rejeição do e-mail antigo, maiúsculas/minúsculas,
renomeação mantendo senha e sessão, nomes inválidos/duplicados e cadastro restrito à TI. A migração
é verificada com contas legadas, colisões, preservação de senha/vínculo e repetição sem perda de dados.
Também são verificados encerramento dos canais privados no logout/troca/reset, expiração
de sessão já conectada, tentativas limitadas de impressão, transmissão incerta, preservação
do documento, idempotência, limites dos turnos em Brasília e grupos com nomes iguais.
No frontend, `npm test` verifica autorização, retorno seguro após o login, condições
do acompanhante, persistência da solicitação, mensagens de impressão, regras das senhas
novas e proteção do protocolo encaminhado pelo proxy.
As impressoras são simuladas nesses testes; a saída em papel deve ser validada no equipamento real.

## HTTPS

Para configurar o certificado da TI na instalação Windows atual, use
`configurar-https.ps1`. No servidor Linux/Docker, há o complemento
`docker-compose.https.yml`. A ativação depende do nome DNS reservado ao Ceres Care,
certificado válido para esse nome e chave privada. Veja [HTTPS.md](HTTPS.md)
para preparação, ativação, renovação e validações. Os acessos atuais são mantidos
até que a configuração seja aplicada.

No Linux, o modelo `infra/https.env.example` permite preparar os parâmetros após
a instalação base e ativar o HTTPS em etapa separada. Consulte também o
[roteiro de homologação Linux](HOMOLOGACAO-LINUX.md) para login, impressões,
QR Codes e recuperação de backup no servidor de destino.

## Active Directory e permissões

A área Administração → Credenciais permite escolher conta local ou AD local do
Windows Server. A senha AD é validada no domínio; perfil e unidades continuam
controlados no Ceres Care. A integração vem desativada e exige LDAPS com certificado
válido e HTTPS no acesso à aplicação. Usuários e senhas atuais são preservados.
Veja [configuração, ativação e limites das sessões AD](ACTIVE-DIRECTORY.md).

## Configuração dos formulários no GitHub

`configuracoes/formularios-unidade-havai.json` registra os esquemas Médico e Enfermagem em
19/10/2026, incluindo campos, ordem, obrigatoriedade, informativos e opções. O arquivo contém
somente a configuração dos formulários; pedidos, dados de pacientes, usuários e credenciais ficam fora dele.

As edições feitas no gestor continuam sendo gravadas no PostgreSQL. Atualize essa cópia ao sincronizar
novas alterações de formulário. Um `git pull` atualiza os arquivos e não substitui o banco em execução.

Para recuperar um esquema em outra instalação, autentique-se na API com um perfil de Gestão,
carregue `GET /api/gestao/formularios/{filial_id}/{tipo}` e envie o respectivo objeto
`formularios.MEDICO` ou `formularios.ENFERMAGEM` do JSON para
`PUT /api/gestao/formularios/{filial_id}/{tipo}`, em `esquema_json`. Inclua em `versao` o
`atualizado_em` retornado pelo GET para preservar a proteção contra edição concorrente.
