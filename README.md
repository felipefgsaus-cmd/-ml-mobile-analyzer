# ML Mobile Analyzer V5 Max Free

Objetivo: obter o máximo possível sem serviços externos pagos.

## Fontes tentadas
- `/items/{item_id}`
- `/items/{item_id}/description`
- `/reviews/item/{item_id}`
- `/questions/search`
- `/users/{seller_id}`
- `/products/{product_id}`

Cada rota é tentada uma vez. Se houver 401/403, a ferramenta segue para a próxima fonte.

## Campos tentados
- título
- preço
- vendas do anúncio
- estoque
- frete
- fotos
- atributos
- descrição
- nota
- quantidade de avaliações
- textos de avaliações
- perguntas/respostas
- vendedor
- reputação
- transações históricas do vendedor

## Custo
Nenhuma API externa paga é usada.

## Segurança
- não faz scraping direto do Mercado Livre
- não usa proxies
- não contorna CAPTCHA
- não rotaciona IP
- não insiste em 403
- token OAuth fica na memória do servidor

## Variáveis do Render
Mantenha apenas:
- ML_APP_ID
- ML_CLIENT_SECRET
- ML_REDIRECT_URI
- FLASK_SECRET_KEY
