# Monitoramento e recuperação — itens 1 e 6

Atualização de 26/10/2026, referente à lista de melhorias sugerida em 23/10.

## 1. Monitoramento no painel de TI

O administrador entra em `/admin` e abre **Monitoramento**, também definido como
aba inicial. A tela atualiza a cada 15 segundos e informa:

- API respondendo e tempo ativo do processo.
- Conexão, latência e tamanho do banco PostgreSQL.
- Atividade do consumidor da impressão, último ciclo e falhas consecutivas.
- Pendências de qualquer data, trabalhos em processamento, falhas e envios incertos
  atuais. Erros de tentativas antigas já substituídas por outro envio não são
  contados como falhas atuais. Pedidos finalizados são excluídos desse indicador.
- Totais históricos por estado dos trabalhos criados nas últimas 24 horas.
- Data e resultado do último teste de recuperação, com o último sucesso preservado
  se uma tentativa posterior falhar.

O atalho **Abrir central de impressões** permite conferir os trabalhos e usar as
regras de reenvio existentes. O monitor não transmite testes para impressoras.
O estado “enviado” continua indicando transmissão TCP, sem comprovar papel impresso.

Detalhes são exclusivos de **ADMIN_TI**. Gestão, Cozinha e Copeira recebem HTTP 403;
visitantes recebem 401. A resposta não contém pacientes, documentos, senhas, tokens,
endereços de conexão, caminhos privados ou conteúdo de erros SQL.

### Sondas e estados

| Endpoint | Finalidade | Resposta |
| --- | --- | --- |
| `/api/health` | Processo da API respondendo | JSON mínimo, HTTP 200 |
| `/api/health/ready` | API consegue consultar o banco | HTTP 200 ou 503; JSON mínimo |
| `/api/admin/monitoramento` | Indicadores detalhados | Autenticação e perfil de TI |

A sonda de banco usa `SELECT 1` com prazo de três segundos. A interface distingue
API respondendo de banco indisponível; quando faltam dados, mostra situação
desconhecida em vez de reapresentar números antigos como se fossem atuais.
O consumidor publica um sinal de atividade a cada ciclo. Sem sinal recente por
dois minutos, com falhas ou com consumidor encerrado, a tela indica atenção/parada.
Processamentos acima de um minuto também aparecem como alerta para conferência.

A imagem Docker inclui verificação de prontidão com intervalo de 15 segundos,
timeout de cinco, três tentativas e início de 20 segundos. Esse indicador de saúde
não substitui a supervisão operacional da instalação.

## 6. Teste completo de recuperação

A ferramenta `backend/validar_recuperacao.py` cria um backup novo e restaura a cópia
em banco temporário. É executada na estação de manutenção, fora do servidor web,
com o ambiente Python do projeto e acesso administrativo ao Docker/PostgreSQL.
O `DATABASE_URL` privado do backend deve alcançar o mesmo PostgreSQL do contêiner
indicado; a ferramenta verifica a identidade do cluster antes de prosseguir.

Na instalação Windows atual:

```powershell
Set-Location 'C:\Users\Suporte\Documents\Projeto Cnutri'
.\backend\.venv\Scripts\python.exe .\backend\validar_recuperacao.py --container dietas-db
```

`--pasta-backups` permite escolher outro diretório local autorizado. O padrão é
`backups/` na raiz do projeto. Para outra instalação, use o contêiner correto e um
ambiente de manutenção privado que alcance seu banco. O comando não altera o
destino configurado da API e não recebe senhas na linha de comando.

### Conferências realizadas

1. Obtém uma visão consistente da origem e a compartilha com `pg_dump --snapshot`.
   Solicitações legítimas podem continuar sendo recebidas durante a cópia.
2. Gera um arquivo customizado `-Fc`, com permissões privadas, fora do Git.
3. Cria um banco com nome aleatório `cnutri_restore_<UUID>`, sem acesso concedido a
   PUBLIC. A cópia não recebe API, seed ou consumidor de impressão.
4. Restaura com `pg_restore --exit-on-error --single-transaction`, sem substituir
   o banco original nem importar permissões/owners de servidor.
5. Compara todas as tabelas públicas por quantidade e resumos SHA-256 dos registros,
   incluindo bytes de documentos, assinaturas, contas e configurações. A leitura
   em fluxo evita concatenar o banco inteiro em memória.
6. Confere colunas, restrições, índices e sua validade. A comparação reconhece a
   representação equivalente dos casts de arrays usada pelo PostgreSQL, preservando
   predicados, colunas e unicidade.
7. Verifica sequências para evitar IDs conflitantes no próximo cadastro; valida os
   formulários e a leitura dos pedidos pelo modelo atual; confere cada assinatura PNG.
8. Remove somente o banco temporário criado pela execução. Falha de conferência ou
   de limpeza impede o resultado **VALIDADO**. Nomes arbitrários e o banco de origem
   são rejeitados como destinos de restauração/remoção.

O relatório privado fica em `work/recuperacao/ultimo_resultado.json`. Contém os
resumos de conferência e o nome do dump, sem valores dos registros, senhas ou tokens.
A publicação é atômica. O painel recebe apenas os campos agregados permitidos.
Os dumps anteriores são preservados; o teste não instala uma agenda de cópias.

### Resultado e alcance

A recuperação real desta instalação foi concluída em 26/10/2026: **todas as 17
tabelas conferidas**, com formulários, documentos, assinaturas, registros e
sequências validados. O banco temporário foi removido. Os totais detalhados e o
arquivo utilizado ficam no relatório privado e no painel de TI.

A comparação antes/depois da publicação confirmou a preservação das 17 tabelas
operacionais. O processo da cópia não enviou impressões nem realizou login com
contas de pessoas. Contas e senhas foram preservadas pelo conteúdo do backup.

Essa execução valida a recuperação local do banco. A política de retenção, cópias
externas, arquivos privados de ambiente, certificados e implantação em outro
servidor fazem parte da preparação operacional desse destino. O backup do banco
não contém automaticamente esses arquivos ou os papéis globais do PostgreSQL.

### Resultado no Docker de produção

`docker-compose.prod.yml` monta somente `work/recuperacao/` como leitura na API e
configura `BACKUP_RELATORIO_ARQUIVO=/var/lib/cnutri-monitoramento/ultimo_resultado.json`.
O diretório de dumps e o controle do Docker não são montados no servidor web.
Em instalações nativas, o caminho padrão aponta para a pasta `work/recuperacao/`
do projeto; a TI pode configurar a variável para outro arquivo privado autorizado.

## Validação automatizada

- **178 testes de backend aprovados**, em 179 descobertos; o teste opcional do
  gateway Caddy/HTTPS não foi habilitado nesta execução.
- **28 testes de frontend aprovados**, build aprovado, lint com somente os dois
  avisos anteriores de efeitos em `Gestao.jsx`.
- Testes PostgreSQL em bancos exclusivos, com dados fictícios: restauração completa,
  falha durante restauração, detecção de registro divergente e entrada de nova
  solicitação durante a captura consistente. Guardas de destino e comparação de
  índices também cobertas. Bancos de teste removidos ao final.
- Testes de autorização, falha de conexão, respostas sem dados privados, sinal de
  atividade da fila e relatório incompleto sem falso sucesso.
- Conferência visual desktop/mobile com dados fictícios. Health e prontidão
  responderam HTTP 200 por localhost e pela rede; o monitor privado recusou acesso
  anônimo com 401. Compose de produção e complemento HTTPS passaram na validação
  de configuração, sem iniciar a instalação de produção.

Referências técnicas: [pg_dump](https://www.postgresql.org/docs/16/app-pgdump.html),
[sincronização de snapshots](https://www.postgresql.org/docs/16/functions-admin.html#FUNCTIONS-SNAPSHOT-SYNCHRONIZATION)
e [pg_restore](https://www.postgresql.org/docs/16/app-pgrestore.html).
