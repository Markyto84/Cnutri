# Teste de pico de solicitações — Ceres Care

Laboratório descartável para avaliar o servidor central sem gerar pedidos, impressões ou alterações no sistema em uso. Resultados de 28/10/2026: [relatório](../TESTE-DE-PICO-2026-10-28.md).

## Escopo e isolamento

- 21 unidades fictícias, 766.500 pedidos históricos e 2.100 pedidos ativos iniciais.
- 168 conexões WebSocket: uma cozinha e sete telas de entregas por unidade. Cinco contas fictícias por unidade mantêm presença a cada 30 segundos.
- Reconciliação HTTP com ETag a cada 120 segundos e ping WebSocket a cada 25 segundos.
- Formulários de paciente e médico válidos; proporção de 80%/20% nas fases medidas.
- API, PostgreSQL e Nginx recebem cotas que somam quatro CPUs, com limites de 2 GiB, 4 GiB e 256 MiB de memória. A diferença até a referência de 8 GB fica como margem para o sistema operacional. Isso não reproduz uma máquina física com exatamente quatro núcleos e 8 GB totais.
- O gerador, o coletor TCP de impressão e os proxies de rede são instrumentos de teste e ficam fora das cotas dos três serviços. Compartilham o mesmo host do laboratório.
- Os scripts recusam URLs de carga fora de `https://127.0.0.1:...`, usam uma CA temporária somente no cliente e conferem `URL_PUBLICA=https://carga.invalid`.
- A limpeza é limitada ao projeto `ceres-carga-*` sob `work/`; nunca apaga o banco da aplicação em uso.

O arquivo `unidades-privado.json`, o `compose.json` e as chaves TLS ficam somente em `work/`, ignorado pelo Git. Não publique esses arquivos. Execute Python normalmente, sem `-O`, para preservar as verificações `assert` dos scripts. O namespace do proxy usa `NET_ADMIN` somente dentro do contêiner do laboratório.

## Pré-requisitos

Docker com Compose e contêineres Linux; aproximadamente 2 GB livres para o banco de teste e seus dados, além das imagens. Use um ambiente Python 3.12+ dedicado com `pip install -r performance/requirements.txt`. As dependências da aplicação rodam dentro da imagem do backend.

As imagens `ceres-care/backend:0.1.0`, `ceres-care/frontend:0.1.0`, `postgres:16-alpine` e `python:3.12-slim` precisam existir localmente. As duas primeiras correspondem à versão em `de14f28`, anterior às alterações ainda pendentes para inicialização limpa de produção. Os testes não usam os fontes parcialmente editados do backend. A reprodução exata requer os IDs de imagem registrados em `ambiente-resultados.json`; etiquetas Docker e imagens de base podem mudar.

O gerador faz uma consulta leve à saúde da aplicação atual em `http://127.0.0.1:5173/api/health/ready` a cada dez segundos e interrompe após três falhas consecutivas ou respostas acima de 2,5 segundos. Adapte esse endereço no código se a aplicação atual estiver em outro local. Nenhuma solicitação de dieta é enviada para esse endereço.

## Execução

A partir da raiz do projeto, em um terminal com o ambiente Python de testes ativado:

```text
python performance/ambiente.py iniciar
```

O comando imprime uma pasta absoluta `.../work/ceres-carga-...`. Substitua `<pasta>` nos comandos abaixo pelo caminho exibido, entre aspas:

```text
python performance/executar.py "<pasta>"
python performance/executar.py "<pasta>" --rede
python performance/validar_reenvio.py "<pasta>"
python performance/resumir.py "<pasta>"
python performance/ambiente.py encerrar "<pasta>"
```

Execute em sequência. Encerre o laboratório também se alguma fase falhar; a remoção dos contêineres e do volume não apaga os arquivos de medição. Guarde apenas os arquivos explicitamente listados na seção seguinte.

O modo `--rede` constrói 21 proxies com `tc netem`: 50 ms por sentido de passagem no proxy e 5 Mbit/s por unidade. No ensaio, o ping mediano observado foi 103 ms. Não são inseridas perdas nem interrupções de conexão. O coletor de impressão permanece na rede local do laboratório, fora dessa limitação.

## Cenários e verificações

LAN: 21, 105 e 210 solicitações iniciadas em rajada; 3,5 solicitações/s por 90 segundos; 20/s por 60 segundos. Rede simulada: 3,5/s por 90 segundos e rajada de 105 solicitações. Cada execução faz 42 pedidos funcionais de aquecimento, excluídos das fases medidas.

As fases verificam status HTTP, quantidade e unicidade no banco, chegada do evento às oito telas da unidade e conclusão da fila de filipetas. O coletor recebe os bytes de impressão gerados pelo código real; não representa velocidade de papel, corte ou confirmação física da impressora. Antes da fase seguinte, pedidos sintéticos dessa fase são marcados como entregues, preservando 100 ativos iniciais por unidade.

`validar_reenvio.py` envia três cópias concorrentes de uma mesma solicitação em cada unidade. Confere que 63 chamadas resultam em 21 pedidos e 21 trabalhos de impressão.

O histórico possui os registros de impressão concluída, mas não os bitmaps históricos. O tamanho do banco de teste não é uma previsão de armazenamento anual.

## Arquivos publicáveis de medição

- `resultados-lan.json` e `resultados-wan.json`: percentis, gravações conferidas e fila.
- `requisicoes-lan.csv` e `requisicoes-wan.csv`: tempos e quantidades de bytes de aplicação; não contêm corpos nem tokens.
- `recursos-lan.json` e `recursos-wan.json`: amostras Docker dos três serviços, aproximadamente a cada seis segundos.
- `reenvios.json`: resultado da verificação de idempotência.
- `resumo-completo.json`: consolidação offline conferida por `resumir.py`.
- `ambiente-resultados.json`: metadados sem credenciais capturados no ensaio de 28/10/2026.

Latências HTTP incluem o percurso HTTPS e o recebimento da resposta, mas não o preenchimento ou renderização do formulário no navegador. O número de painéis representa conexões e consultas de estado; não foram executados 168 navegadores completos. Autenticação de sessão foi exercitada; a criação de sessões no login local/AD não fez parte do pico. Resultados curtos de laboratório não estabelecem capacidade máxima nem disponibilidade durante falhas.
