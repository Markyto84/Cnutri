# Ceres Care — linguagem visual de acolhimento

O desenho aproxima o sistema da rotina de quem solicita, prepara e recebe as refeições.
Acolhimento é uma intenção do conjunto visual e da linguagem, sem presumir que uma cor
produza a mesma resposta emocional em todas as pessoas.

A marca apresentada é **Ceres Care**, com a assinatura **Nutrição e cuidado em cada etapa.**
O nome e os prefixos de arquivos ficam centralizados em `frontend/src/services/marca.js`
e `backend/app/core/marca.py`. O título HTML também identifica a aplicação na aba do navegador.

## Cores e hierarquia

- **#0070AD:** ações principais, seleção ativa, títulos de apoio e foco do teclado.
- **#17ABDA:** acentos da identidade e ações secundárias já associadas à marca.
- **#F4F7F8:** fundo neutro suave, com superfícies brancas e variações claras de azul.
- **#06344B:** títulos e texto sobre azul vibrante; os textos de apoio usam azul acinzentado escuro.
- Vermelho, âmbar e verde continuam identificando restrições, atenção e conclusão.
  Os estados também têm texto, sem depender somente da cor.

Pares conferidos numericamente: branco sobre azul principal **5,36:1**; texto #06344B
sobre azul vibrante **4,92:1**; texto de apoio #526D7B sobre branco **5,48:1**.
As bordas #7895A5 sobre o fundo de campo #F7FAFB têm **3,01:1**.
Essas conferências apoiam a leitura; não constituem certificação de acessibilidade da aplicação.

## Tipografia e formas

Usa-se uma família de fontes locais: **Segoe UI Variable Text / Segoe UI**, Roboto,
Helvetica Neue e Arial, conforme a disponibilidade do dispositivo. Títulos, rótulos e
orientações têm escalas e pesos distintos. Não há fonte externa nem pedido a um CDN.
A obtenção de Nunito Sans foi considerada, mas a resolução de domínios externos estava
indisponível durante a implementação; nenhum recurso ausente ficou referenciado no aplicativo.

Cartões têm cantos arredondados, sombra discreta e espaço entre grupos. Círculos e arcos
formam uma ilustração leve de refeição, folha e cuidado. Ícones são SVG com traço arredondado,
decorativos para leitores de tela; botões mantêm o nome da ação em texto.
O ícone original continua identificando a aplicação ao lado do nome Ceres Care.

## Telas e interação

- Solicitações da unidade: escolha clara entre Médico / Administração e Enfermagem / Paciente,
  com explicação curta e indicação das etapas.
- Formulários: identificação e dados da refeição em grupos; campos em duas colunas no
  computador e uma no celular. Refeição, cardápio, nomes e observações têm espaço maior.
  Valores longos de seleção também podem ser lidos por inteiro abaixo do campo.
- Orientações extensas da unidade abrem expandidas e podem ser recolhidas pelo usuário.
  O informativo médico permanece sempre visível.
- Cozinha e entregas: cores de situação, contadores, cartões e ações com hierarquia consistente.
  Preparo e impressão continuam acessíveis diretamente na cozinha.
- Gestão e administração: mesma identidade, indicadores e navegação horizontal com
  rolagem quando necessária. Campos mantêm os rótulos visíveis.
- Recebimento: nome, registro profissional e confirmação em um cartão legível no celular;
  a conclusão mostra o horário registrado pelo servidor.

Os botões adotam alvos de pelo menos 44 px de altura. O foco do teclado tem contorno
visível, inclusive nos campos que usavam `outline-none`. Animações e transições respeitam
`prefers-reduced-motion`. Ícones e formas são locais, sem bibliotecas adicionais.

## Validação

São usados dados fictícios e banco SQLite separado, sem impressoras físicas. A conferência
inclui formulário médico, campos condicionais de paciente/acompanhante e líquidos,
cozinha sem login, gestão, confirmação por QR e reflow no celular. Os registros reais,
as permissões, as regras de envio e a geração das filipetas/etiquetas não são modificados.
Na validação final, os **74 testes do frontend** e o build passaram. O lint manteve somente
os dois avisos preexistentes de dependências de `useEffect` em `Gestao.jsx`.
Logs e imagens de homologação ficam em `work-humanizacao-frontend-final.log`
e `work/validacao-humanizacao/`, fora do versionamento.

Referências: [W3C — contraste mínimo](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html),
[W3C — tamanho mínimo de alvos](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html).
