# ML Mobile Analyzer V6 Diagnostic

Versão de diagnóstico profundo para descobrir exatamente quais dados o Mercado Livre liberou após a mudança de permissões.

## Novos testes

Para cada anúncio, testa:

- `GET /items/{ITEM_ID}` com token
- `GET /items/{ITEM_ID}` sem token
- `GET /items/{ITEM_ID}/prices`
- `GET /items/{ITEM_ID}/sale_price?context=channel_marketplace`
- `GET /items/{ITEM_ID}/description`
- `GET /reviews/item/{ITEM_ID}`
- `GET /reviews/item/{ITEM_ID}?catalog_product_id=...`
- `GET /questions/search`
- `GET /users/{SELLER_ID}`
- `GET /products/{PRODUCT_ID}`
- `GET /products/{PRODUCT_ID}/items?site_id=MLB`

Também há um botão para testar:

- `GET /applications/{APP_ID}`
- `GET /applications/{APP_ID}/grants`
- `GET /users/me`

## Reautorização

Depois de mudar permissões no DevCenter, use o botão **Reautorizar após alterar permissões**. Isso força o app a descartar o token local e gerar uma nova autorização.

## Segurança

Esta versão:
- não faz scraping do Mercado Livre;
- não usa proxy;
- não rotaciona IP;
- não tenta burlar PolicyAgent;
- faz apenas uma tentativa por rota por análise;
- registra o corpo completo do erro para diagnóstico.

## Render

Mantenha estas variáveis:
- `ML_APP_ID`
- `ML_CLIENT_SECRET`
- `ML_REDIRECT_URI`
- `FLASK_SECRET_KEY`

Não coloque nenhuma chave secreta no GitHub.
