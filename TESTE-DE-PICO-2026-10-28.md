# Teste de pico de solicitações — Ceres Care

**Data:** 28/10/2026. **Referência solicitada:** 4 vCPUs e 8 GB. **Base testada:** imagens Linux 0.1.0, código da versão `de14f28`.

**Recomendação: manter o servidor central e o acesso pelo navegador.** Nos cenários executados, não apareceu um gargalo de solicitação que justifique instalar uma aplicação cliente em cada unidade. Foram registradas **2.271 solicitações medidas, sem falhas nem divergências de gravação**, com 21 unidades e 168 conexões de painéis. O resultado é uma evidência de capacidade neste laboratório; a decisão de produção ainda depende da homologação no servidor e nos enlaces reais.

## Carga representada

O dimensionamento usa os números informados pela operação:

- 21 unidades × 100 dietas/dia = **2.100 solicitações/dia**.
- Por unidade: 1 computador, 5 celulares e 2 tablets = **168 dispositivos** no conjunto.
- Como referência conservadora, concentrar todas as 2.100 solicitações em dez minutos equivale a **3,5 solicitações por segundo** no servidor central.

Essa taxa foi exercitada por 90 segundos em cada condição de rede, produzindo 315 pedidos por condição. Não foi executada a janela completa de dez minutos. Também foram testadas rajadas instantâneas de 1, 5 e 10 solicitações por unidade e uma taxa de 20/s por um minuto, aproximadamente 5,7 vezes a referência de 3,5/s.

O banco isolado iniciou com **766.500 pedidos históricos fictícios** — 365 dias × 2.100 pedidos — e **2.100 pedidos ativos**, 100 por unidade. O histórico tem metadados de impressão concluída, sem os bitmaps antigos. Seu tamanho inicial de aproximadamente 529 MiB serve para caracterizar o ensaio e **não é uma estimativa de armazenamento anual**.

## Ambiente e método

Foram usados o backend real, PostgreSQL 16, Nginx com HTTPS e a fila real de impressão. Os limites dos serviços foram:

| Serviço | CPU máxima | Memória máxima |
|---|---:|---:|
| API, um processo Uvicorn | 1,5 vCPU | 2 GiB |
| PostgreSQL | 2 vCPUs | 4 GiB |
| Nginx | 0,5 vCPU | 256 MiB |
| Total dos três serviços | **4 vCPUs** | **6,25 GiB** |

A margem até a referência de 8 GB contempla o sistema operacional. Trata-se de cotas Docker em um computador compartilhado com processador Intel Core i5-13500; a VM Docker dispõe de aproximadamente 8 GB e 20 CPUs lógicas. Isso limita recursos dos contêineres, mas não reproduz o desempenho de qualquer servidor físico de quatro núcleos. O gerador, os proxies e o coletor de impressão são instrumentos fora das cotas dos serviços, no mesmo host.

Cada unidade manteve uma conexão de cozinha e sete de entregas. Foram usadas cinco contas fictícias por unidade, totalizando 105 sessões com presença periódica. Os painéis receberam os eventos reais WebSocket, enviaram ping a cada 25 segundos e fizeram reconciliação HTTP a cada 120 segundos. As sessões passaram pelas verificações de autenticação do backend. Os formulários enviados eram de paciente e médico, em proporção aproximada de 80%/20%.

O gerador distribuiu as solicitações pelas 21 unidades e conferiu os registros efetivos no banco, além das respostas HTTP. Para cada pedido medido, verificou a chegada do evento às oito telas da unidade e a conclusão de sua filipeta na fila. Entre cenários, os pedidos gerados na fase eram marcados como entregues, preservando o conjunto inicial de 100 ativos por unidade.

Todos os dados eram sintéticos. Os endpoints de carga foram publicados somente em `127.0.0.1`, com banco, certificados e impressora simulada próprios. A aplicação em uso continuou respondendo às consultas leves de saúde durante o teste.

## Tempo para registrar as solicitações

O tempo abaixo vai do envio HTTPS até o recebimento da resposta de registro. **P95** significa que 95% das solicitações responderam dentro desse tempo. Não mede o preenchimento do formulário nem a renderização do navegador.

| Condição | Solicitações medidas | P50 | P95 | Maior tempo | Falhas |
|---|---:|---:|---:|---:|---:|
| LAN: 21 simultâneas, 1/unidade | 21 | 0,52 s | **0,58 s** | 0,58 s | 0 |
| LAN: 105 simultâneas, 5/unidade | 105 | 0,74 s | **1,08 s** | 1,14 s | 0 |
| LAN: 210 simultâneas, 10/unidade | 210 | 1,42 s | **2,16 s** | 2,27 s | 0 |
| LAN: 3,5/s por 90 segundos | 315 | 0,038 s | **0,050 s** | 0,57 s | 0 |
| LAN: 20/s por 60 segundos | 1.200 | 0,027 s | **0,127 s** | 1,09 s | 0 |
| Rede simulada: 3,5/s por 90 segundos | 315 | 0,35 s | **0,37 s** | 0,68 s | 0 |
| Rede simulada: 105 simultâneas | 105 | 0,73 s | **1,08 s** | 1,10 s | 0 |
| **Total** | **2.271** | — | — | **2,27 s** | **0** |

A rede simulada tinha 21 proxies independentes com **5 Mbit/s por unidade e cerca de 100 ms de latência adicionada**. O ping de aplicação mediano passou de 3,8 ms na LAN para 103 ms. Não houve perda de pacotes nem interrupção de enlace simulada. Esse cenário não substitui medir os circuitos reais das unidades.

O P95 praticamente igual nas duas rajadas de 105 pedidos não significa que o atraso de rede seja irrelevante: aquecimento, conexões disponíveis e duração curta afetam a comparação. No fluxo contínuo de 3,5/s, o efeito da rede aparece claramente, de aproximadamente 50 ms para 374 ms.

Como referência de análise, se a operação pactuar P95 de até dois segundos, a rajada de 210 pedidos excede ligeiramente essa meta, chegando a 2,16 segundos. Houve espera transitória sob a rajada extrema. O ensaio não encontrou falha de registro ou acúmulo persistente na carga contínua testada.

## Atualização das telas e impressão

Todos os **2.271 pedidos apareceram nas oito conexões da respectiva unidade**. Não foram observados eventos de outra unidade nem desconexões WebSocket. Na rajada de 210, o P95 de chegada à última das oito telas foi 2,15 segundos; no fluxo de 3,5/s, foi 47 ms na LAN e 372 ms na rede simulada.

O coletor TCP recebeu os bytes produzidos pela renderização real da filipeta, incluindo QR Code. O tempo de fila usa os instantes de criação do trabalho e de transmissão registrados no banco; tem origem diferente da medição HTTP e não deve ser somado mecanicamente ao P95 da solicitação.

| Cenário | P95 até transmissão da filipeta | Maior tempo | Pendentes ao final | Falhas de transmissão |
|---|---:|---:|---:|---:|
| LAN: 21 simultâneas | 1,40 s | 1,46 s | 0 | 0 |
| LAN: 105 simultâneas | 3,66 s | 3,82 s | 0 | 0 |
| LAN: 210 simultâneas | **7,33 s** | **7,60 s** | 0 | 0 |
| LAN: 3,5/s | 1,03 s | 1,32 s | 0 | 0 |
| LAN: 20/s | 1,46 s | 1,80 s | 0 | 0 |
| Rede simulada: 3,5/s | 1,00 s | 1,09 s | 0 | 0 |
| Rede simulada: 105 simultâneas | 3,78 s | 3,96 s | 0 | 0 |

Nas rajadas maiores, a fila de impressão é o trecho que demora mais para concluir. **ENVIADO confirma transmissão TCP ao coletor**, sem comprovar saída no papel. Não foram simulados movimento do papel, corte, falta de bobina, impressora desligada ou enlace remoto da impressora. A limitação de rede foi aplicada ao HTTP/WebSocket dos dispositivos; o coletor de impressão permaneceu na LAN do laboratório.

Um ensaio separado de reenvio concorrente fez 63 chamadas — três cópias da mesma solicitação em cada unidade. Foram criados **21 pedidos e 21 trabalhos de impressão**, com 21 respostas de criação e 42 respostas de reaproveitamento. Não houve duplicação nesse teste.

## Recursos observados

As amostras Docker foram coletadas aproximadamente a cada seis segundos: 32 amostras na execução LAN e 20 na execução de rede simulada. Elas não capturam necessariamente picos instantâneos.

| Medida dos três serviços | LAN | Rede simulada |
|---|---:|---:|
| Maior CPU total amostrada | 1,51 núcleo | 1,47 núcleo |
| Fração da cota conjunta de 4 vCPUs | **37,7%** | **36,7%** |
| Maior soma de memória informada pelo Docker | **833 MiB** | **821 MiB** |
| Reinícios / encerramentos por falta de memória | 0 / 0 | 0 / 0 |

A memória informada pelo Docker representa os contêineres e não equivale ao consumo total de uma instalação Linux: não inclui todos os custos do host, ferramentas, backups e caches. Esses valores demonstram folga no ensaio; não justificam reduzir a referência de 8 GB para produção. As consultas de saúde da aplicação em uso continuaram respondendo, com maior tempo observado de 156 ms.

## Decisão e próximos critérios

**O navegador com servidor central atende à carga exercitada.** Um cliente instalado em cada unidade continuaria dependendo da API e do banco centrais para registrar as refeições; portanto sua instalação, por si só, não corrige um eventual limite desses serviços.

Se a preocupação for continuar operando durante queda do enlace, será necessário projetar operação offline com fila local, sincronização e tratamento de conflitos. Essa é uma necessidade distinta de capacidade e não foi homologada neste ensaio. Um agente local apenas para impressão também pode ser considerado caso os testes físicos mostrem dificuldade de comunicação com as impressoras remotas.

Antes da primeira versão de produção, os próximos critérios são:

1. Repetir o roteiro no servidor Linux escolhido, com o armazenamento e os outros serviços que efetivamente compartilharão a máquina.
2. Medir latência, banda e estabilidade dos enlaces das 21 unidades e repetir o cenário simultâneo a partir da rede real.
3. Homologar impressoras físicas por unidade, inclusive falha de conexão, retomada e conferência do QR Code impresso.
4. Definir com a operação os limites aceitáveis para resposta, atualização de tela e fila de impressão; executar um teste prolongado que inclua relatórios, backups e uso pelos demais perfis.

O teste atual não estabelece a capacidade máxima do sistema nem cobre 24 horas, login simultâneo/AD, exportações extensas, recuperação de falhas, indisponibilidade de rede, impressão de etiquetas no status pronto ou confirmação de entrega por QR Code sob carga. Exercita especificamente a solicitação, a distribuição aos painéis e a transmissão da filipeta.

## Evidências e reprodução

O roteiro e os scripts estão em `performance/`. As medições disponíveis no pacote de resultados são os CSVs individuais, amostras de recursos, resultados por cenário, conferência dos reenvios e metadados das imagens. Credenciais fictícias e chaves temporárias ficam fora do pacote e do Git. Os 84 pedidos de aquecimento das execuções finais e os pedidos de calibração são excluídos dos 2.271 medidos.

As imagens usadas foram:

- Backend: `sha256:91a7765c2be3bf69356f19681057d6c927ab156d2eca02e9b3f990fa313b7eb0`.
- Frontend: `sha256:4879b7ae3c3a80226850e1a92e9b80e2633bc88dee255982487ee9d0aa6e2b67`.

Os ajustes pendentes para criar um banco limpo de produção não fazem parte dessa versão medida. O empacotamento de uma nova versão continua após as alterações anteriores à primeira instalação.
