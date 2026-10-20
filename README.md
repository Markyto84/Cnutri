# Sistema de Gestão de Dietas Hospitalares

Plataforma multifilial para solicitação, preparo, entrega e auditoria de dietas hospitalares.

**Stack:** FastAPI (Python) · React + Vite · PostgreSQL 16 · WebSockets · Impressão ESC/POS · Docker

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

### 3. Criar o arquivo de variáveis (opcional, recomendado)

Na pasta do projeto no servidor, crie um `.env`:

```bash
cd /opt/projeto-dietas-hospitalares
cat > .env <<'EOF'
POSTGRES_PASSWORD=escolha-uma-senha-forte
JWT_SECRET=escolha-um-segredo-longo-e-aleatorio
EOF
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
| Cozinha (Kanban) | `http://IP-DO-SERVIDOR/cozinha/1` |
| Entregas das copeiras | `http://IP-DO-SERVIDOR/entregas/1` |
| Administração | `http://IP-DO-SERVIDOR/admin` |
| Login | `http://IP-DO-SERVIDOR/login` |

**Utilizadores iniciais (trocar as senhas imediatamente!):**

| Perfil | Usuário | Senha |
|---|---|---|
| Admin TI | admin | `Trocar@123` |
| Nutricionista | nutricao | `Trocar@123` |
| Cozinha | cozinha | `Trocar@123` |

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

Ao final dos dois tipos de filipeta, o bloco **Entrega à recepção** oferece espaço e linha para
**Assinatura**, além de **Data e hora** em branco para preenchimento manual no recebimento.
Esses campos não recebem a data/hora da solicitação automaticamente e também aparecem na reimpressão.

O texto é desenhado no servidor com **Pillow e DejaVu Sans Mono**, incluindo `ã, õ, ç, á`, e enviado
como imagem monocromática ESC/POS em blocos de até 128 linhas de pixels. Assim, os acentos não dependem
da tabela de caracteres interna da POS80. A área usada é de 576 pontos em papel de 80 mm; a impressora
deve aceitar [impressão raster GS v 0](https://download4.epson.biz/sec_pubs/pos/reference_en/escpos/gs_lv_0.html).
As fontes e sua licença ficam em `backend/app/assets/fonts/`, incluídas também na imagem Docker.
Essa conversão acontece somente na impressão; os textos digitados permanecem preservados no banco.

O envio automático e o botão de reimpressão da Cozinha usam o mesmo gerador. A reimpressão consulta
os rótulos atuais da unidade e conserva todos os dados salvos no pedido. O alerta de restrição severa
e o corte de papel são mantidos. O informativo de horários do formulário não é repetido na filipeta.

## Segurança (checklist antes de ir a produção)

- [ ] Trocar as senhas dos 3 utilizadores do seed
- [ ] Definir `JWT_SECRET` forte no `.env`
- [ ] Definir `POSTGRES_PASSWORD` forte no `.env`
- [ ] Atualizar `CORS_ORIGINS` no `docker-compose.prod.yml` com o endereço real do sistema
- [ ] HTTPS: colocar um proxy reverso com TLS (ex.: nginx/Caddy) na frente, ou publicar só na rede interna
- [ ] Backup automático diário do volume `pgdata`

## Desenvolvimento (Windows)

Com Docker Desktop, Python 3.12 e Node.js instalados, execute na pasta do projeto:

```powershell
Set-Location 'C:\Users\Suporte\Documents\Projeto Cnutri'
.\start.ps1
```

O script inicia o PostgreSQL na porta **5433**, a API na **8000** e o frontend na **5173**.
Na primeira execução, cria o ambiente Python e instala as dependências que estiverem ausentes.
Execuções seguintes reutilizam os processos desta pasta. Os logs ficam em `work/logs/`.
Quando precisa iniciar a API ou o frontend, usa uma sessão independente do terminal, via WMI.
Fechar ou interromper o terminal de desenvolvimento não encerra esses serviços. Isso não configura
inicialização automática após reiniciar o Windows; use `start.ps1` novamente nessa situação.

- Formulário: `http://localhost:5173/unidade-havai`
- Cozinha: `http://localhost:5173/cozinha/1` (sem login)
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
destaques, bordas dos cabeçalhos e ações de entrega/exportação. O fundo é azul suave `#EDF5FA`,
com painéis brancos e campos em tons claros. O texto é branco sobre o azul principal e azul profundo
`#06344B` sobre o azul vibrante, com contraste de 5,36:1 e 4,92:1, respectivamente.
As cores ficam centralizadas em `frontend/src/index.css`: `brand`, `brand-vibrant`, `brand-ink`,
variantes de foco/hover, `app-background`, `panel` e escala `slate` com tons azulados. Formulários,
login, gestão, administração, relatórios, cozinha e entregas compartilham essa paleta. Alertas de
restrição/erro, avisos e indicadores de produção continuam identificados por suas cores funcionais.

No painel **Gestão de Nutrição → Refeições médicas**, edite as listas de **Refeição**, **Suco**,
**Sobremesa** e **Local de entrega**, com uma opção por linha em cada campo, e clique em **Salvar opções**.
Essas listas alimentam o formulário médico, preservando a ordem e a obrigatoriedade dos campos.
As opções são salvas no banco de dados, sem alterar as dietas ou o formulário de Enfermagem.

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

## Cozinha, plantão e entregas no computador e no celular

O dashboard `/cozinha/{id}` e a página `/entregas/{id}` abrem sem login para unidades ativas.
Na cozinha, os pedidos passam por **Pendentes → Em preparo → Prontos**. No celular, botões de etapa
mostram uma coluna por vez; no computador, as três colunas aparecem juntas. A página de entregas
mostra somente as refeições prontas, em cartões com botão **Entregar**. Ambas usam botões de toque
de pelo menos 44 pixels e a caixa de seleção se ajusta à largura da tela.

Para cadastrar uma copeira, abra **Administração → Credenciais**, escolha o perfil **Copeira** e
vincule as unidades de trabalho. Nenhuma conta de copeira é criada automaticamente. Ela acessa
**Entrar no plantão** com a credencial cadastrada; enquanto a sessão estiver conectada, seu nome
fica disponível na unidade selecionada. A presença é renovada a cada 30 segundos. **Sair do plantão**
encerra a sessão imediatamente; fechar o navegador ou perder a conexão remove o nome após até
três minutos sem renovação. Sessões simultâneas da mesma pessoa não duplicam seu nome.

Ao tocar em **Entregar**, selecione uma copeira online e avance para a assinatura. Informe o
**Nome do recebedor** e peça que ele assine no quadro branco com o dedo, a caneta ou o mouse.
**Limpar assinatura** permite refazer o desenho; mudar a orientação da tela preserva os traços.
O botão **Finalizar entrega** exige nome e assinatura preenchidos. O servidor verifica novamente
se a copeira está no plantão e se o pedido continua pronto; salva a assinatura, o recebedor e a
entrega na mesma transação, e muda o pedido para **ENTREGUE**. A data e hora são registradas pelo
banco no momento da finalização, sem usar o relógio informado pelo dispositivo. Se houver falha
ao salvar a assinatura, toda a entrega é revertida. O pedido sai das listas de prontos e de
entregas, mantendo histórico e indicadores. Confirmações repetidas ou concorrentes são bloqueadas.

Em **Gestão de Nutrição → Relatórios → Entregas e comprovantes de recebimento**, consulte o
destinatário, refeição, copeira, recebedor, local/leito e **data e hora da entrega**. Os filtros
por data e os horários usam Brasília (UTC-3); o relatório tem páginas de até 50 entregas.
**Ver assinatura** abre a imagem do comprovante. A consulta e a imagem exigem perfil de Gestão
ou Administração e acesso à unidade. As assinaturas não são publicadas no dashboard ou no
WebSocket. Entregas antigas continuam visíveis, identificadas quando não possuem assinatura.

As rotas `/api/operacao` e o WebSocket `/ws/operacao/{id}` fornecem os dados operacionais para
essas telas. Prontuário, registro profissional, matrícula, sexo e data de nascimento não são
publicados nesse canal; a idade é calculada no servidor. O canal interno `/ws/cozinha/{id}` segue
restrito a perfis de operação autorizados. Atualização por consulta a cada dez segundos complementa
o WebSocket; a lista de copeiras é consultada a cada cinco segundos.

As tabelas `sessoes_copeiras` e `entregas_pedidos` e o perfil `COPEIRA` são criados na inicialização,
preservando usuários, pedidos e configurações existentes. O backup local anterior a essa atualização
fica em `backups/backup-dietas-2026-10-20-antes-entregas.dump`, fora do Git.

A tabela `recebimentos_entregas`, criada automaticamente na inicialização, guarda o nome do
recebedor e a imagem PNG da assinatura vinculada à entrega. O servidor recebe traços com limites
de quantidade e coordenadas e gera o PNG com Pillow; rejeita assinaturas vazias ou inválidas.
Os backups do banco incluem os comprovantes. Antes dessa adição foi validado o backup
`backups/backup-dietas-2026-10-20-antes-assinaturas.dump`, também fora do Git.

### Testes da administração, entregas, impressão e relatórios

Os testes usam um banco SQLite temporário em memória, sem modificar o PostgreSQL em uso:

```powershell
Set-Location backend
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

São 46 testes: onze da administração/login, catorze de operação/plantão/entrega, treze das filipetas,
sete do relatório de dietas e exportações e um de migração PostgreSQL.
O teste de migração só roda quando `CNUTRI_TEST_POSTGRES_URL` aponta explicitamente para um banco
de testes PostgreSQL com permissão para criar schemas. Ele usa um schema exclusivo e reverte toda
a transação ao terminar; sem essa variável, esse teste é omitido e os outros 45 usam SQLite isolado.
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
As impressoras são simuladas nesses testes; a saída em papel deve ser validada no equipamento real.

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
