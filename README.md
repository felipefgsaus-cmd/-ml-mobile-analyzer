# ML Mobile Analyzer V7 iPhone

Versão para uso diário.

## Automático via API oficial
- título do catálogo
- preço e preço original via ofertas do catálogo
- vendedor e reputação
- logística
- garantia
- atributos
- fotos
- descrição curta do catálogo
- destaques do catálogo
- avaliações, nota e total
- perguntas e respostas
- outras ofertas do mesmo produto

## Complemento pelo iPhone
A rota `/iphone` cria uma URL privada de recebimento para um Atalho do iPhone.

O Atalho é disparado manualmente pela Folha de Compartilhamento do Safari e pode enviar:
- URL do anúncio
- texto/artigo que o próprio Safari disponibilizar

O servidor não raspa automaticamente a página do Mercado Livre.

## Render
Mantenha:
- ML_APP_ID
- ML_CLIENT_SECRET
- ML_REDIRECT_URI
- FLASK_SECRET_KEY
