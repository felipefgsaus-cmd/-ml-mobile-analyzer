# ML Mobile Analyzer — versão web

Feito para uso pelo celular.

## Como funciona

1. Você publica este projeto em uma hospedagem.
2. Abre o endereço pelo Safari/Chrome.
3. Toca em **Conectar Mercado Livre**.
4. Autoriza no próprio Mercado Livre.
5. Cola os links dos concorrentes.
6. A ferramenta tenta coletar:
   - item/título/preço
   - quantidade vendida, quando disponível
   - vendedor e reputação
   - frete e tipo logístico
   - fotos
   - ficha técnica
   - descrição
   - avaliações pelo endpoint `/reviews/item/{ITEM_ID}`
7. Exporta JSON e CSV.

## Caminho mais fácil: Render

### 1. Suba estes arquivos para um repositório no GitHub

Arquivos principais:
- `app.py`
- `requirements.txt`
- `render.yaml`

### 2. No Render

Crie um **Blueprint** ou **Web Service** a partir do repositório.

O `render.yaml` já define:
- build
- start command
- variáveis necessárias

### 3. Descubra a URL final

Exemplo:

    https://ml-mobile-analyzer.onrender.com

Então o callback será:

    https://ml-mobile-analyzer.onrender.com/callback

### 4. Configure o app no Mercado Livre

No portal de desenvolvedores do Mercado Livre, configure o Redirect URI **exatamente** com o callback acima.

Copie:
- App ID
- Secret Key

### 5. Configure as variáveis no Render

No painel do serviço, adicione:

    ML_APP_ID=SEU_APP_ID
    ML_CLIENT_SECRET=SUA_SECRET_KEY
    ML_REDIRECT_URI=https://SEU-SITE.onrender.com/callback

`FLASK_SECRET_KEY` pode ser gerada automaticamente pelo Render via `render.yaml`.

### 6. Abra no celular

Acesse a URL pública e toque em **Conectar Mercado Livre**.

## Importante

Sua senha nunca passa por esta aplicação.

Você entra diretamente no domínio do Mercado Livre durante o OAuth.

Mesmo com sua conta autorizada, a API pode ocultar certos dados de anúncios de terceiros. Quando isso acontecer, a ferramenta marca o campo como indisponível em vez de inventar.

## Depois

Baixe `ml_concorrentes.json` no celular e envie o arquivo para o ChatGPT. Ele contém também os textos de avaliações quando o endpoint permitir acesso.
