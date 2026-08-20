# ML Mobile Analyzer V3

V3 focada em rotas alternativas oficiais quando `/items/{id}` é bloqueado.

## Estratégia

1. item direto (uma tentativa)
2. Questions
3. seller_id extraído das Questions
4. `/users/{seller_id}` para reputação
5. `/users/{seller_id}/items/search`
6. `/sites/MLB/search?seller_id=...`
7. `/products/{product_id}`
8. `/products/{product_id}/items`
9. consolidação em JSON/CSV

A ferramenta não tenta contornar CAPTCHA, PolicyAgent ou proteção anti-bot.
Durante a análise, usa somente requisições GET.
