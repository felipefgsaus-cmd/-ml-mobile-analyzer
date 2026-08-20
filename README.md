# ML Mobile Analyzer V4 Safe

Versão segura e conservadora.

## O que faz

- Mercado Livre API oficial:
  - Questions
  - seller_id
  - vendedor/reputação
- Busca web:
  - usa a **Brave Search API oficial**
  - consulta o índice público da web por item_id/product_id
  - NÃO faz scraping direto de páginas do Mercado Livre
- Corrige mojibake (`OlÃ¡` -> `Olá`) quando possível
- Mantém dados confirmados via API separados de candidatos vindos de snippets

## O que NÃO faz

- não faz crawling/scraping do Mercado Livre
- não tenta contornar 403/PolicyAgent
- não usa proxies/rotação de IP
- não resolve CAPTCHA
- não usa cookies privados do navegador
- não simula navegação humana

## Variável nova no Render

Além das variáveis existentes, adicione:

    BRAVE_SEARCH_API_KEY=...

Crie a chave na Brave Search API e coloque a chave **somente no Render**, nunca no GitHub.

Sem essa chave, a V4 continua funcionando para Questions + vendedor, mas não faz busca externa.

## Segurança

O token OAuth fica em memória do servidor e some quando o serviço reinicia/redeploya.
Isso significa que, após um deploy, pode ser necessário tocar em "Conectar Mercado Livre" novamente.
