# Entrega com filipeta assinada e lançamento pela Nutrição

## Operação

1. O solicitante envia o formulário da unidade; a cozinha acompanha o preparo normalmente.
2. A filipeta traz um QR Code compacto no canto superior direito. No rodapé, o recebedor preenche seu nome, a assinatura e a data e hora da entrega.
3. Após a entrega física, a Nutrição lê o QR em um celular ou tablet e entra com sua própria conta.
4. Na tela **Comprovar entrega**, informa o nome do recebedor e a data e hora escritas na filipeta, tira ou seleciona a foto e confere a prévia.
5. **Registrar entrega e comprovante** salva os dados e a imagem na mesma transação e muda o pedido de **Pronto** para **Entregue**.
6. Em **Gestão de Nutrição → Relatórios → Entregas e comprovantes de recebimento**, a equipe consulta os dados, amplia e baixa a foto.

O painel das copeiras está desativado, seus links saíram da cozinha e da gestão e suas rotas de finalização não aceitam novos registros. Credenciais e comprovantes históricos continuam preservados. Os QR Codes já impressos abrem o novo fluxo; não é necessário reimprimir os pedidos existentes para acessar a tela.

## Acesso e rastreabilidade

- Somente **Nutrição** e **Administração de TI**, respeitando as unidades autorizadas, podem registrar entregas e acessar as imagens.
- A data e hora da **entrega** são informadas manualmente e interpretadas no horário de Brasília. Não podem estar no futuro nem antes do minuto da solicitação.
- A data e hora do **lançamento** vêm do servidor. A autoria é a conta autenticada que lançou o comprovante.
- A foto e o nome são obrigatórios. O registro profissional do recebedor deixou de ser solicitado neste fluxo.
- Reenvios não substituem uma entrega já concluída. Cancelamentos e confirmações concorrentes são coordenados pela trava do pedido.
- A consulta pública do código não mostra nome de paciente, recebedor ou imagem. A foto é servida apenas por rota autenticada, sem cache público.
- O QR usa um código aleatório e permanece no fragmento da URL, fora das requisições HTTP e dos logs de acesso.

## Imagem e armazenamento

- Captura ou seleção de **JPG, PNG ou WebP**, até **12 MB**. Fotos HEIC devem ser convertidas para um formato compatível antes do envio.
- O navegador reduz a resolução antes de enviar. O servidor verifica o conteúdo real, corrige a orientação, converte para escala de cinza e remove EXIF e outros metadados.
- A cópia armazenada é **JPEG binário**, com até **2.000 pixels no maior lado** e **300 KiB (307.200 bytes)**. Na compressão adaptativa, a qualidade não cai abaixo de 72 e fotos grandes mantêm pelo menos 1.600 pixels no maior lado.
- Se não for possível compactar dentro do limite com esses parâmetros, o sistema solicita uma nova foto mais próxima da filipeta. Não aplica redução ilimitada que prejudique a leitura.
- Somente a cópia otimizada é salva no banco, sem o original ou uma representação em Base64. Os relatórios carregam a imagem apenas quando o comprovante é aberto.
- O comprovante inclui hash SHA-256 e tamanho para verificar sua integridade. O `pg_dump` da aplicação inclui as fotos. A recuperação confere os bytes, o hash e o formato JPEG.

Enquadre a filipeta inteira com boa iluminação e confirme na prévia se nome, assinatura, data e hora estão legíveis. A compressão não corrige uma foto desfocada.

## Implantação

Não há migração destrutiva. A inicialização cria a tabela `comprovantes_entrega`; as tabelas de entregas e assinaturas anteriores permanecem intactas. O relatório escolhe a data manual dos novos comprovantes e mantém a interpretação dos registros históricos.

Os campos **Lançamento da entrega (Brasília)** e **Foto da filipeta disponível** também constam nas exportações Excel, Calc e CSV para Google Sheets. As imagens são consultadas no sistema, sem incorporar fotos a cada linha da planilha.
