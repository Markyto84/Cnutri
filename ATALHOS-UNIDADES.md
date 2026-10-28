# Atalhos de unidade para o navegador padrão

No painel de Administração → Unidades, **Baixar atalho (.zip)** gera um pacote contendo um atalho nativo do Windows, por exemplo:

```text
Cnutri - unidade-havai.zip
└── Cnutri - unidade-havai.lnk
```

Depois de baixar, extraia o `.lnk` e copie-o para a área de trabalho dos computadores da unidade. O atalho abre diretamente o formulário dessa unidade no navegador padrão configurado no Windows do destinatário. Não altera os padrões da máquina nem inclui usuário, senha, token ou sessão do administrador.

## Implementação

- O formato nativo segue [MS-SHLLINK](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-shllink/).
- O destino usa `%SystemRoot%\explorer.exe`, com a URL HTTP/HTTPS como argumento, delegando ao Windows a abertura do navegador. Nenhum caminho do Chrome, Edge ou Firefox é gravado.
- As variáveis de ambiente de destino e ícone são resolvidas no computador que abre o arquivo. Não há dependência da letra do disco ou das pastas pessoais do servidor.
- A URL continua usando o endereço público da instalação, quando configurado, com o código da unidade. Somente HTTP e HTTPS são aceitos; credenciais e parâmetros da tela administrativa não são distribuídos.
- O conteúdo do download é binário, com MIME `application/zip`, em lugar de um Blob de texto. O ZIP preserva o nome e a extensão do atalho nativo; o navegador do chat renomeou um `.lnk` direto para `.download` na validação.
- ZIP sem compressão, um único arquivo e CRC32, conforme a [especificação ZIP](https://pkware.cachefly.net/webdocs/casestudies/APPNOTE.TXT). Não há scripts, instalador ou pedido de elevação.
- A geração acontece no frontend, sem dependências adicionais e sem exigir Windows no servidor. O atalho distribuído destina-se aos computadores Windows das unidades.

## Validação

Testes do frontend verificam endereços de instalação, nomes de arquivos, edição do código da unidade, rejeição de entradas inválidas e ausência de sessão ou navegador fixo. O download foi realizado pelo botão real do componente em página isolada, sem autenticação ou dados hospitalares.

O ZIP baixado foi conferido com `zipfile` do Python, incluindo CRC e nome do único arquivo. O `.lnk` extraído foi lido pela API nativa `WScript.Shell` do Windows, que reconheceu o destino, o argumento HTTP e o nome da unidade com acentos. O uso de COM é apenas uma verificação local; não é necessário na aplicação nem na instalação Linux.
