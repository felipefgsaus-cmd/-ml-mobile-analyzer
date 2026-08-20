# ML Mobile Analyzer V4 Free Clean

Versão gratuita e enxuta.

## Mantido
- Login OAuth do Mercado Livre
- Questions
- seller_id
- Perfil do vendedor
- Reputação
- Power seller
- Total histórico de transações do vendedor
- Exportação JSON
- Exportação CSV

## Removido da interface
- Preço
- Título
- Reviews
- Descrição
- Estoque
- Catálogo
- Vendas por anúncio
- Probes/diagnósticos 401/403
- Brave Search API
- Qualquer integração paga

## Observação
`transactions.total` é histórico do vendedor, não quantidade vendida daquele anúncio.

## Variáveis do Render
Continue usando apenas:

- ML_APP_ID
- ML_CLIENT_SECRET
- ML_REDIRECT_URI
- FLASK_SECRET_KEY

Não é necessário criar BRAVE_SEARCH_API_KEY.
