import os
import re
import csv
import json
import time
import secrets
from io import StringIO
from urllib.parse import urlencode

import requests
from flask import Flask, request, redirect, session, render_template_string, Response, jsonify
from dotenv import load_dotenv

load_dotenv()

APP_ID = os.getenv("ML_APP_ID", "").strip()
CLIENT_SECRET = os.getenv("ML_CLIENT_SECRET", "").strip()
REDIRECT_URI = os.getenv("ML_REDIRECT_URI", "").strip()
FLASK_SECRET = os.getenv("FLASK_SECRET_KEY") or secrets.token_hex(32)

API = "https://api.mercadolibre.com"
AUTH_URL = "https://auth.mercadolivre.com.br/authorization"

app = Flask(__name__)
app.secret_key = FLASK_SECRET
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=True,
)

SERVER_SESSIONS = {}

HTML = """
<!doctype html>
<html lang="pt-br">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ML Analyzer V8</title>
<style>
body{font-family:system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#f5f5f5;color:#202020;margin:0}
.wrap{max-width:1120px;margin:auto;padding:16px}
.card{background:#fff;border:1px solid #e1e1e1;border-radius:16px;padding:18px;margin:14px 0}
h1{font-size:26px;margin:2px 0 8px}h2{font-size:19px;margin:0 0 12px}h3{font-size:16px}
textarea,input{width:100%;box-sizing:border-box;padding:12px;border:1px solid #cfcfcf;border-radius:12px;font-size:16px}
textarea{min-height:155px}
button,.btn{display:inline-block;background:#111;color:white;border:0;border-radius:12px;padding:12px 15px;text-decoration:none;font-size:15px;cursor:pointer;margin:3px 3px 3px 0}
.btn.secondary{background:#555}.btn.blue{background:#1769aa}.btn.green{background:#087a39}
.ok{color:#087a39}.bad{color:#a40000}.muted{color:#686868;font-size:13px}
.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}
.metric{border:1px solid #e4e4e4;background:#fafafa;border-radius:12px;padding:12px}
.metric b{display:block;color:#666;font-size:12px;margin-bottom:5px}.metric span{font-weight:700;font-size:17px}
.src{font-size:11px;color:#777;margin-top:5px}
table{border-collapse:collapse;width:100%;display:block;overflow:auto;font-size:12px}
th,td{border-bottom:1px solid #ddd;padding:8px;text-align:left;vertical-align:top;min-width:105px}
.qa{border-top:1px solid #eee;padding:11px 0}
.code{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;word-break:break-all;background:#f6f6f6;padding:10px;border-radius:10px;font-size:12px}
@media(max-width:700px){.grid{grid-template-columns:1fr}}
</style>
</head>
<body><div class="wrap">
<h1>ML Analyzer V8 — Coleta Estável + Prompt V2.1</h1>
<p class="muted">API oficial + catálogo + reviews + perguntas + ofertas relacionadas.</p>

<div class="card">
<h2>1. Mercado Livre</h2>
{% if not configured %}
<p class="bad">OAuth não configurado.</p>
{% elif token %}
<p class="ok">✓ Conta autorizada.</p>
<a class="btn secondary" href="/logout">Desconectar</a>
<a class="btn blue" href="/reauthorize">Reautorizar</a>
{% else %}
<a class="btn" href="/login">Conectar Mercado Livre</a>
{% endif %}
</div>

<div class="card">
<h2>2. Analisar anúncios</h2>
<form method="post" action="/analyze">
<textarea name="links" placeholder="Cole um link ou ID por linha">{{ links or "" }}</textarea>
<p><button type="submit">Analisar</button></p>
</form>
<p class="muted">Até 8 anúncios por vez.</p>
</div>

{% if error %}<div class="card bad"><b>Erro:</b> {{ error }}</div>{% endif %}

{% if rows %}
<div class="card">
<h2>Resultados</h2>
<a class="btn" href="/export/json">JSON completo</a>
<a class="btn secondary" href="/export/csv">CSV resumo</a>
<a class="btn green" href="/prompt">Gerar Prompt Mestre V2.1</a>
</div>

{% for r in rows %}
<div class="card">
<h2>{{ r.fields.title.value if r.fields.title else (r.item_id or "Anúncio") }}</h2>
<div class="grid">
<div class="metric"><b>Preço</b><span>{{ r.fields.price.value if r.fields.price else "Indisponível" }}</span>{% if r.fields.price %}<div class="src">{{ r.fields.price.source }}</div>{% endif %}</div>
<div class="metric"><b>Preço original</b><span>{{ r.fields.original_price.value if r.fields.original_price else "Indisponível" }}</span></div>
<div class="metric"><b>Vendedor</b><span>{{ r.seller.nickname if r.seller else "Indisponível" }}</span></div>
<div class="metric"><b>Reputação</b><span>{% if r.seller and r.seller.seller_reputation %}{{ r.seller.seller_reputation.level_id or "—" }}{% else %}—{% endif %}</span></div>
<div class="metric"><b>Avaliação</b><span>{{ r.fields.rating_average.value if r.fields.rating_average else "Indisponível" }}</span></div>
<div class="metric"><b>Total avaliações</b><span>{{ r.fields.reviews_total.value if r.fields.reviews_total else "Indisponível" }}</span></div>
<div class="metric"><b>Perguntas</b><span>{{ r.question_summary.total }}</span></div>
<div class="metric"><b>Fotos catálogo</b><span>{{ r.fields.pictures.value|length if r.fields.pictures else 0 }}</span></div>
</div>

{% if r.fields.catalog_description %}
<h3>Descrição / resumo do catálogo</h3>
<p>{{ r.fields.catalog_description.value }}</p>
{% endif %}

{% if r.fields.main_features %}
<h3>Destaques do catálogo</h3>
{% for x in r.fields.main_features.value %}<p>• {{ x.text if x.text else x }}</p>{% endfor %}
{% endif %}

{% if r.fields.shipping %}
<h3>Logística do anúncio</h3>
<pre class="code">{{ r.fields.shipping.value|tojson(indent=2) }}</pre>
{% endif %}

{% if r.fields.warranty %}
<p><b>Garantia:</b> {{ r.fields.warranty.value }}</p>
{% endif %}

{% if r.fields.attributes %}
<h3>Ficha técnica</h3>
<table><thead><tr><th>Atributo</th><th>Valor</th></tr></thead><tbody>
{% for a in r.fields.attributes.value %}
<tr><td>{{ a.name or a.id }}</td><td>{{ a.value_name or a.value or "" }}</td></tr>
{% endfor %}
</tbody></table>
{% endif %}

{% if r.fields.reviews %}
<h3>Avaliações em destaque</h3>
{% for rv in r.fields.reviews.value[:5] %}
<div class="qa"><b>{{ rv.title or ("Nota " ~ rv.rate) }}</b><br>{{ rv.content or "" }}</div>
{% endfor %}
{% endif %}

{% if r.question_summary.questions %}
<h3>Perguntas e respostas</h3>
{% for q in r.question_summary.questions %}
<div class="qa"><b>{{ q.text }}</b><br>{{ q.answer or "Sem resposta" }}</div>
{% endfor %}
{% endif %}

{% if r.other_offers %}
<h3>Outras ofertas do mesmo produto</h3>
<table><thead><tr><th>Item</th><th>Vendedor</th><th>Preço</th><th>Frete grátis</th><th>Logística</th></tr></thead><tbody>
{% for o in r.other_offers %}
<tr><td>{{ o.item_id }}</td><td>{{ o.seller_id }}</td><td>{{ o.currency_id }} {{ o.price }}</td><td>{{ o.shipping.free_shipping if o.shipping else "" }}</td><td>{{ o.shipping.logistic_type if o.shipping else "" }}</td></tr>
{% endfor %}
</tbody></table>
{% endif %}
</div>
{% endfor %}
{% endif %}
</div></body></html>
"""

PROMPT_HTML = """
<!doctype html>
<html lang="pt-br">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Prompt Mestre - ML Analyzer V8</title>
<style>
body{font-family:system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#f5f5f5;color:#202020;margin:0}
.wrap{max-width:1120px;margin:auto;padding:16px}
.card{background:#fff;border:1px solid #e1e1e1;border-radius:16px;padding:18px;margin:14px 0}
h1{font-size:25px;margin:2px 0 8px}
textarea{width:100%;box-sizing:border-box;min-height:65vh;padding:12px;border:1px solid #cfcfcf;border-radius:12px;font-size:14px;line-height:1.45}
button,.btn{display:inline-block;background:#111;color:#fff;border:0;border-radius:12px;padding:12px 15px;text-decoration:none;font-size:15px;cursor:pointer;margin:3px 3px 3px 0}
.btn.secondary{background:#555}.ok{color:#087a39;font-weight:700}.muted{color:#686868;font-size:13px}
</style>
</head>
<body><div class="wrap">
<h1>Prompt Mestre da Publicação Perfeita</h1>
<p class="muted">Gerado localmente pelo ML Analyzer V8 usando os dados já coletados. Nenhuma API de IA é necessária.</p>
<div class="card">
<button type="button" onclick="copyPrompt()">Copiar prompt</button>
<a class="btn secondary" href="/export/prompt.txt">Baixar .txt</a>
<a class="btn secondary" href="/">Voltar</a>
<span id="copied" class="ok"></span>
<textarea id="prompt" readonly>{{ prompt }}</textarea>
</div>
</div>
<script>
async function copyPrompt(){
  const el=document.getElementById('prompt');
  try{ await navigator.clipboard.writeText(el.value); }
  catch(e){ el.select(); document.execCommand('copy'); }
  document.getElementById('copied').textContent=' ✓ Copiado';
}
</script>
</body></html>
"""

def _field_value(record, key):
    return ((record.get("fields") or {}).get(key) or {}).get("value")

def _compact(value, limit=1800):
    if value in (None, "", [], {}):
        return "Não disponível"
    if isinstance(value, (dict, list)):
        text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    else:
        text = str(value)
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= limit else text[:limit] + "…"

def build_master_prompt(results):
    valid = [r for r in (results or []) if not r.get("error")]
    if not valid:
        return "Não há anúncios analisados com dados suficientes para gerar o prompt."

    blocks=[]
    for i,r in enumerate(valid,1):
        seller_data=r.get("seller") or {}
        reputation=seller_data.get("seller_reputation") or {}
        questions=(r.get("question_summary") or {}).get("questions") or []
        reviews=_field_value(r,"reviews") or []
        offers=r.get("other_offers") or []
        attrs=_field_value(r,"attributes") or []
        shipping=_field_value(r,"shipping") or {}

        review_lines=[]
        for rv in reviews[:15]:
            if not isinstance(rv,dict):
                continue
            content=rv.get("content") or rv.get("title")
            if content:
                review_lines.append(f"- Nota {rv.get('rate','?')}: {_compact(content,650)}")

        question_lines=[]
        for q in questions[:25]:
            if not isinstance(q,dict):
                continue
            question_lines.append(
                f"- Pergunta: {_compact(q.get('text'),450)} | Resposta: {_compact(q.get('answer'),650)}"
            )

        attr_lines=[]
        for a in attrs[:50]:
            if not isinstance(a,dict):
                continue
            name=a.get("name") or a.get("id")
            val=a.get("value_name") or a.get("value")
            if name and val not in (None,""):
                attr_lines.append(f"- {name}: {_compact(val,350)}")

        offer_lines=[]
        for o in offers[:25]:
            if not isinstance(o,dict):
                continue
            osh=o.get("shipping") or {}
            offer_lines.append(
                f"- Item {o.get('item_id','?')} | preço {o.get('currency_id','')} {o.get('price','?')} | "
                f"frete grátis={osh.get('free_shipping')} | logística={osh.get('logistic_type')}"
            )

        block=f"""
### CONCORRENTE {i}
ID: {r.get('item_id') or 'Não disponível'}
Título: {_compact(_field_value(r,'title'))}
Preço: {_compact(_field_value(r,'price'))}
Preço original: {_compact(_field_value(r,'original_price'))}
Avaliação média: {_compact(_field_value(r,'rating_average'))}
Total de avaliações: {_compact(_field_value(r,'reviews_total'))}
Vendedor: {_compact(seller_data.get('nickname'))}
Reputação do vendedor: {_compact(reputation.get('level_id'))}
Garantia: {_compact(_field_value(r,'warranty'))}
Frete/logística: {_compact(shipping)}
Descrição do anúncio: {_compact(_field_value(r,'description'),5000)}
Descrição/resumo do catálogo: {_compact(_field_value(r,'catalog_description'),3500)}
Destaques do catálogo: {_compact(_field_value(r,'main_features'),3000)}
Quantidade de fotos de catálogo: {len(_field_value(r,'pictures') or [])}

Ficha técnica:
{chr(10).join(attr_lines) if attr_lines else '- Não disponível'}

Avaliações coletadas:
{chr(10).join(review_lines) if review_lines else '- Não disponível'}

Perguntas e respostas coletadas:
{chr(10).join(question_lines) if question_lines else '- Não disponível'}

Outras ofertas do mesmo produto:
{chr(10).join(offer_lines) if offer_lines else '- Não disponível'}
"""
        blocks.append(block.strip())

    data="\n\n".join(blocks)
    return f"""PROMPT MESTRE V2.1 — ENGINE DE CONVERSÃO

ATUE COMO UM ESTRATEGISTA SÊNIOR DE MARKETPLACES ESPECIALIZADO EM MERCADO LIVRE, INTELIGÊNCIA COMPETITIVA, SEO, COPYWRITING DE PERFORMANCE, MERCHANDISING DIGITAL, CRO (OTIMIZAÇÃO DE CONVERSÃO), REDUÇÃO DE OBJEÇÕES E PREVENÇÃO DE DEVOLUÇÕES.

OBJETIVO CENTRAL
Construa a publicação com MAIOR PROBABILIDADE DE CONVERTER entre os anúncios analisados, usando os concorrentes apenas como inteligência de mercado. A publicação deve reduzir dúvidas antes da compra, destacar os atributos decisivos comprováveis, melhorar a percepção de valor e evitar afirmações que possam gerar devolução, reclamação ou perda de confiança.

NÃO CONFUNDA popularidade com verdade técnica. Avaliações, perguntas e respostas de vendedores são sinais de mercado, mas não substituem documentação do fabricante. Quando houver conflito entre fontes, trate a informação como NÃO COMPROVADA até confirmação.

Foram analisados {len(valid)} anúncios.

====================
DADOS DOS CONCORRENTES
====================

{data}

====================
PROTOCOLO DE ANÁLISE
====================

ANTES de escrever título, descrição ou imagens, siga obrigatoriamente estas regras:

1. CLASSIFIQUE CADA INFORMAÇÃO RELEVANTE em uma destas categorias:
- FATO CONFIRMADO: sustentado de forma consistente pelos dados disponíveis;
- SINAL DE MERCADO: aparece em avaliações, perguntas ou respostas, mas não é especificação oficial;
- INFERÊNCIA: conclusão plausível derivada dos dados, sem comprovação direta;
- RECOMENDAÇÃO: decisão estratégica proposta por você;
- NÃO COMPROVADO / CONFLITANTE: dado ausente, contraditório ou insuficiente.

2. NÃO transforme experiência individual de comprador em promessa universal.
3. NÃO use respostas dos concorrentes como prova técnica quando não houver sustentação adicional.
4. Quando concorrentes discordarem sobre medida, rendimento, compatibilidade, material, temperatura, garantia, origem ou desempenho, destaque a divergência e marque como [CONFIRMAR].
5. Não invente certificações, compatibilidades, conteúdo da embalagem, procedência, garantia, prazo de entrega, quantidade vendida, desempenho ou características físicas.
6. Não copie frases dos concorrentes.
7. Priorize o que ajuda o cliente a decidir corretamente e comprar com segurança.

====================
SUA TAREFA — PROMPT MESTRE V2
====================

## 1. RESUMO EXECUTIVO DE CONVERSÃO
Comece com no máximo 10 bullets contendo os insights mais importantes para vender este produto melhor que a média dos concorrentes.

Inclua:
- principal intenção de busca;
- principal motivo de compra;
- maior objeção;
- principal risco de compra errada;
- atributo mais decisivo;
- melhor oportunidade de diferenciação;
- principal oportunidade de SEO;
- maior lacuna dos concorrentes;
- risco de afirmação não comprovada;
- ação de maior impacto recomendada.

## 2. MAPA DE SINAIS DE COMPRA
Identifique e agrupe:
- palavras e expressões recorrentes nos títulos;
- linguagem espontânea usada pelos compradores nas avaliações;
- linguagem espontânea usada nas perguntas;
- benefícios mais elogiados;
- problemas/objeções mais citados;
- dúvidas que se repetem;
- atributos técnicos mais recorrentes;
- fatores de confiança: reputação, avaliações, garantia, logística, fotos e clareza da oferta;
- sinais de sensibilidade a preço, frete e prazo.

Dê maior peso aos termos que aparecem simultaneamente em TÍTULOS + AVALIAÇÕES + PERGUNTAS.

## 3. RANKING DOS FATORES DE CONVERSÃO
Crie uma tabela com os fatores que mais influenciam a decisão de compra.

Colunas obrigatórias:
- Fator;
- Impacto provável na conversão (1-5);
- Frequência nos dados (1-5);
- Força da evidência (1-5);
- Risco se comunicarmos errado (1-5);
- Classificação: FATO / SINAL / INFERÊNCIA / RECOMENDAÇÃO / NÃO COMPROVADO;
- Ação recomendada no anúncio.

Ordene pelo impacto esperado na conversão.

## 4. MAPA DE OBJEÇÕES E RISCO DE DEVOLUÇÃO
Liste as principais objeções do comprador e, para cada uma, informe:
- a dúvida/medo;
- evidência encontrada;
- impacto provável na conversão;
- risco de devolução ou reclamação;
- como prevenir a objeção no anúncio;
- em qual parte resolver: título, imagem, ficha, descrição ou FAQ.

Não tente "vencer" uma objeção com uma promessa não comprovada. Quando não houver resposta segura, transforme a incerteza em uma pergunta para o vendedor.

## 5. MATRIZ DE MENSAGENS COMERCIAIS
Monte uma tabela com as melhores mensagens que podemos usar.

Colunas:
- Mensagem/argumento;
- Evidência que sustenta;
- Objeção que resolve;
- Onde usar no anúncio;
- Status: PODE AFIRMAR / USAR COM CAUTELA / NÃO USAR AINDA;
- Observação.

## 6. ALEGAÇÕES QUE NÃO DEVEM SER USADAS
Crie uma seção explícita chamada "ALEGAÇÕES PROIBIDAS OU NÃO COMPROVADAS".
Liste tudo que os dados não permitem afirmar com segurança, especialmente:
- "original" ou origem geográfica sem comprovação;
- compatibilidade universal;
- rendimento exato quando houver divergência;
- superioridade absoluta como "melhor";
- resistência, temperatura, duração ou desempenho sem sustentação;
- itens inclusos não confirmados;
- garantias não definidas.

Explique em uma frase por que cada alegação deve ser evitada.

## 7. SEO POR INTENÇÃO DE COMPRA
Separe as palavras-chave em 3 grupos:
A. ALTA INTENÇÃO — termos diretamente ligados ao produto e à busca de compra;
B. ATRIBUTOS DECISIVOS — marca, medida, modelo, aplicação, cor, quantidade etc.;
C. TERMOS AUXILIARES — úteis na descrição/ficha, mas que não devem poluir o título.

Depois indique:
- termos prioritários para título;
- termos prioritários para ficha técnica;
- termos que devem aparecer naturalmente na descrição;
- termos que devem ser evitados por serem irrelevantes, repetitivos ou não comprovados.

## 8. PROPOSTA DE VALOR CENTRAL
Crie uma frase curta que represente a melhor proposta de valor possível SEM inventar diferencial do produto.
Depois explique em 2-4 linhas por que essa proposta deve orientar título, imagens e descrição.

## 9. ESTRATÉGIA DA PUBLICAÇÃO IDEAL
Explique como superar a média dos concorrentes usando:
- clareza;
- informação decisiva;
- redução de objeções;
- melhor organização visual;
- prova do que pode ser comprovado;
- prevenção de compra errada;
- percepção de valor;
- SEO sem keyword stuffing.

Diferencie claramente melhoria da PUBLICAÇÃO de melhoria do PRODUTO.

## 10. TÍTULOS OTIMIZADOS
Crie 3 opções:
- TÍTULO A — SEO máximo;
- TÍTULO B — equilíbrio SEO + leitura natural;
- TÍTULO C — foco em conversão e clareza.

Para cada título:
- explique rapidamente o raciocínio;
- aponte qualquer termo que dependa de [CONFIRMAR].

Depois escolha um único "TÍTULO RECOMENDADO" e explique por que ele é o melhor.
Não faça keyword stuffing e respeite leitura natural para Mercado Livre.

## 11. DESCRIÇÃO COMPLETA PRONTA PARA PUBLICAR
Escreva em português do Brasil, pronta para uso, com:
- abertura objetiva;
- o que é o produto;
- para quem/para qual uso ele é indicado SOMENTE quando sustentado;
- principais benefícios comprováveis;
- diferenciais da oferta somente quando comprováveis;
- especificações importantes;
- conteúdo da embalagem somente se confirmado;
- orientações de uso relevantes;
- compatibilidades e limitações;
- garantia somente quando confirmada;
- prevenção das principais objeções;
- chamada final para compra sem exagero.

A descrição deve ser escaneável no celular, com blocos curtos. Não encha a descrição de palavras-chave repetidas.

## 12. FICHA TÉCNICA IDEAL
Separe em:
A. ATRIBUTOS CONFIRMADOS;
B. ATRIBUTOS PROVÁVEIS, MAS QUE EXIGEM CONFIRMAÇÃO;
C. ATRIBUTOS IMPORTANTES AUSENTES.

Para cada atributo B ou C, explique em uma frase por que vale a pena confirmar.

## 13. FAQ DE CONVERSÃO
Crie uma FAQ baseada prioritariamente nas perguntas reais dos compradores.
Ordene as perguntas pelo impacto na decisão de compra.
Responda apenas o que é sustentado pelos dados.
Onde não houver certeza, escreva [CONFIRMAR] e explique exatamente qual informação falta.

## 14. FUNIL VISUAL DE 10 IMAGENS
As 10 imagens devem funcionar como uma sequência de decisão, não como imagens decorativas.

Use preferencialmente esta lógica, adaptando ao produto:
1. O que estou comprando? — capa;
2. Qual é a medida/modelo/variante decisiva?;
3. Para que serve?;
4. Serve para mim? — compatibilidade;
5. Por que confiar? — benefício/prova visual;
6. Como usar/instalar?;
7. O que preciso saber antes da compra?;
8. Rendimento/capacidade/limitação, apenas se comprovável;
9. O que vem na embalagem?;
10. Resumo final da decisão.

Para CADA imagem informe:
- objetivo de conversão;
- pergunta do cliente que ela responde;
- composição/cena;
- texto curto do infográfico;
- benefício ou atributo que deve provar;
- o que precisa ser visualmente demonstrado;
- o que NÃO pode aparecer para evitar informação enganosa.

A imagem 1 deve ser adequada a capa de marketplace, com fundo limpo e produto como protagonista.

## 15. PROMPTS PROFISSIONAIS PARA GERAR AS 10 IMAGENS
Crie um prompt separado para cada imagem.
Cada prompt deve definir:
- fotografia/estilo visual;
- enquadramento;
- iluminação;
- fundo/cenário;
- posição do produto;
- hierarquia do infográfico quando houver;
- texto exato permitido;
- características físicas que devem permanecer idênticas à referência;
- elementos que NÃO podem ser inventados;
- formato apropriado para galeria de marketplace e leitura em smartphone.

Se não houver foto real do produto disponível nos dados, informe que uma fotografia real de referência deve ser fornecida antes de gerar imagens que pretendam representar exatamente o item vendido.

## 16. ANÁLISE DE PREÇO, FRETE E LOGÍSTICA
Com base SOMENTE nos dados coletados:
- identifique o núcleo de preço competitivo;
- diferencie preço do item de custo total percebido pelo cliente;
- analise presença de frete grátis;
- compare tipos de logística;
- identifique se existe oportunidade de posicionamento.

Não determine preço final sem conhecer custos, margem, tarifas e estratégia do vendedor. Se necessário, peça esses dados.

## 17. MELHORIAS SOBRE OS CONCORRENTES
Sugira entre 5 e 10 melhorias, ordenadas por IMPACTO ESPERADO NA CONVERSÃO.
Para cada melhoria, indique:
- impacto: ALTO / MÉDIO / BAIXO;
- esforço: ALTO / MÉDIO / BAIXO;
- por que pode funcionar;
- qual evidência dos concorrentes levou à recomendação.

## 18. NOTA DE PRONTIDÃO DA PUBLICAÇÃO
Dê uma nota geral de 0 a 100 para a prontidão do anúncio.
Crie também notas de 0 a 100 para:
- identificação do produto;
- medidas/especificações;
- compatibilidade;
- conteúdo da embalagem;
- procedência/autenticidade;
- garantia;
- logística;
- SEO;
- descrição;
- FAQ;
- material visual.

IMPORTANTE: a nota deve refletir a QUALIDADE DAS INFORMAÇÕES DISPONÍVEIS, e não inventar que algo está pronto quando faltam dados.
Explique os 3 fatores que mais impedem chegar a 100.

## 19. PLANO DE AÇÃO PRIORITÁRIO
Crie uma lista de ações em ordem:
- FAZER AGORA;
- CONFIRMAR ANTES DE PUBLICAR;
- MELHORAR DEPOIS.

Priorize tarefas que aumentem conversão ou evitem erro de compra.

## 20. INFORMAÇÕES QUE PRECISO DO VENDEDOR
Finalize com esse título EXATO.
Faça SOMENTE perguntas realmente necessárias para transformar os pontos [CONFIRMAR] em informação segura.
Agrupe perguntas semelhantes e evite perguntar algo que já esteja sustentado pelos dados.
Sempre que possível, peça evidência simples, como foto da embalagem, etiqueta, código de barras, manual ou informação oficial do fabricante.

====================
CRITÉRIO DE QUALIDADE FINAL
====================

Sua resposta deve funcionar como um plano de execução comercial, não apenas como um relatório dos concorrentes.
Para cada recomendação importante, deixe claro POR QUE ela pode aumentar conversão ou reduzir devolução.
Priorize decisões baseadas em recorrência e evidência.
Se houver conflito nos dados, prefira transparência a uma resposta aparentemente convincente.
Use português do Brasil.
Entregue tudo de forma organizada, prática e pronta para uso.
""".strip()

def configured():
    return bool(APP_ID and CLIENT_SECRET and REDIRECT_URI)

def ss():
    sid = session.get("sid")
    if not sid:
        sid = secrets.token_urlsafe(24)
        session["sid"] = sid
    return SERVER_SESSIONS.setdefault(sid, {})

def token():
    return ss().get("access_token")

def api_headers(auth=True):
    h = {"Accept":"application/json","User-Agent":"ML-Analyzer/8.1"}
    if auth and token():
        h["Authorization"] = f"Bearer {token()}"
    return h

def api_get(path, params=None, auth=True):
    try:
        r = requests.get(API + path, params=params, headers=api_headers(auth), timeout=20)
        try: data = r.json()
        except Exception: data = {"raw_text":r.text[:5000]}
        return r.status_code, data
    except requests.RequestException as e:
        return 0, {"error":type(e).__name__,"message":str(e)}

def fix_text(x):
    if not isinstance(x, str):
        return x
    if any(s in x for s in ("Ã","Â","â€","â€™","â€œ","â€”")):
        try:
            return x.encode("latin1").decode("utf-8")
        except Exception:
            return x
    return x

def deep_fix(obj):
    if isinstance(obj, str): return fix_text(obj)
    if isinstance(obj, list): return [deep_fix(x) for x in obj]
    if isinstance(obj, dict): return {k:deep_fix(v) for k,v in obj.items()}
    return obj

def parse_inputs(text):
    out = []
    for raw in [x.strip() for x in text.splitlines() if x.strip()]:
        # item_id em query string: item_id:MLB123 / item_id%3AMLB123
        q = re.findall(r'item_id(?:%3A|:|=)+(MLB-?\d{6,})', raw, flags=re.I)

        # IDs de item tanto MLB123 quanto MLB-123
        mlb = re.findall(r'\bMLB-?\d{6,}\b', raw.upper())

        # IDs de produto/usuário
        mlbu = re.findall(r'\bMLBU\d{6,}\b', raw.upper())

        # IDs de catálogo em /p/MLB... ou /up/MLBU...
        pathp = [x.upper() for x in re.findall(r'/(?:p|up)/(MLB(?:U)?-?\d{6,})', raw, flags=re.I)]

        def normalize(x):
            return x.upper().replace("-", "") if x else x

        q = [normalize(x) for x in q]
        mlb = [normalize(x) for x in mlb]
        pathp = [normalize(x) for x in pathp]

        # Em URLs de produto tradicionais, o ID do anúncio costuma ser o último MLB encontrado.
        item_id = q[0] if q else (mlb[-1] if mlb else None)

        pids = []
        for x in mlbu + pathp:
            x = normalize(x)
            if x and x != item_id and x not in pids:
                pids.append(x)

        out.append({"raw": raw, "item_id": item_id, "product_ids": pids})
    return out

def setf(fields,k,v,source,confidence="alta"):
    if v in (None,"",[],{}): return
    if k not in fields: fields[k]={"value":deep_fix(v),"source":source,"confidence":confidence}

def questions(item_id):
    if not item_id:
        return {"status":0,"total":0,"questions":[]}, None
    st,d=api_get("/questions/search",{"item":item_id,"api_version":4,"limit":50},True)
    qs=[]; seller_id=None
    if st==200 and isinstance(d,dict):
        for q in d.get("questions") or []:
            seller_id=seller_id or q.get("seller_id")
            qs.append({
                "id":q.get("id"),"date_created":q.get("date_created"),"seller_id":q.get("seller_id"),
                "status":q.get("status"),"text":fix_text(q.get("text")),
                "answer":fix_text((q.get("answer") or {}).get("text"))
            })
    return {"status":st,"total":len(qs),"questions":qs},seller_id

def seller(seller_id):
    if not seller_id: return None
    st,d=api_get(f"/users/{seller_id}",auth=True)
    if st!=200 or not isinstance(d,dict): return None
    return deep_fix(d)

def collect(rec):
    item_id=rec["item_id"]; pids=list(rec.get("product_ids") or [])
    fields={}; other_offers=[]

    if not item_id:
        return {
            "raw":rec.get("raw"),"item_id":None,"product_ids":pids,
            "seller_id":None,"seller":None,
            "question_summary":{"status":0,"total":0,"questions":[]},
            "fields":fields,"other_offers":[],
            "error":"ID do anúncio não reconhecido",
            "_collected_at_unix":int(time.time())
        }

    qsum,seller_id=questions(item_id)
    sel=seller(seller_id)

    st,d=api_get(f"/reviews/item/{item_id}",auth=True)
    if st==200 and isinstance(d,dict):
        setf(fields,"rating_average",d.get("rating_average"),"Mercado Livre /reviews")
        setf(fields,"reviews_total",(d.get("paging") or {}).get("total"),"Mercado Livre /reviews")
        setf(fields,"reviews",d.get("reviews"),"Mercado Livre /reviews")

    st,d=api_get(f"/items/{item_id}/description",auth=True)
    if st==200 and isinstance(d,dict):
        desc=d.get("plain_text") or d.get("text")
        setf(fields,"description",desc,"Mercado Livre /description")

    for pid in pids[:4]:
        st,p=api_get(f"/products/{pid}",auth=True)
        if st==200 and isinstance(p,dict):
            setf(fields,"title",p.get("name") or p.get("title"),f"Mercado Livre /products/{pid}")
            setf(fields,"attributes",p.get("attributes"),f"Mercado Livre /products/{pid}")
            setf(fields,"pictures",p.get("pictures"),f"Mercado Livre /products/{pid}")
            short=(p.get("short_description") or {}).get("content")
            setf(fields,"catalog_description",short,f"Mercado Livre catálogo {pid}")
            setf(fields,"main_features",p.get("main_features"),f"Mercado Livre catálogo {pid}")

        st,offers=api_get(f"/products/{pid}/items",{"site_id":"MLB"},True)
        if st==200 and isinstance(offers,dict):
            results=deep_fix(offers.get("results") or [])
            other_offers=results
            own=next((x for x in results if x.get("item_id")==item_id),None)
            if own:
                if own.get("price") is not None:
                    setf(fields,"price",f"{own.get('currency_id','')} {own.get('price')}".strip(),
                         f"Mercado Livre /products/{pid}/items")
                if own.get("original_price") is not None:
                    setf(fields,"original_price",f"{own.get('currency_id','')} {own.get('original_price')}".strip(),
                         f"Mercado Livre /products/{pid}/items")
                setf(fields,"shipping",own.get("shipping"),f"Mercado Livre /products/{pid}/items")
                setf(fields,"warranty",own.get("warranty"),f"Mercado Livre /products/{pid}/items")
                setf(fields,"listing_type_id",own.get("listing_type_id"),f"Mercado Livre /products/{pid}/items")
                setf(fields,"user_product_id",own.get("user_product_id"),f"Mercado Livre /products/{pid}/items")

    return {
        "raw":rec.get("raw"),"item_id":item_id,"product_ids":pids,
        "seller_id":seller_id,"seller":sel,"question_summary":qsum,
        "fields":fields,"other_offers":other_offers,"_collected_at_unix":int(time.time())
    }

@app.route("/")
def home():
    store=ss()
    return render_template_string(
        HTML, configured=configured(), token=bool(store.get("access_token")),
        rows=store.get("results"), links=store.get("last_links",""),
        error=store.pop("error",None)
    )

@app.route("/health")
def health():
    return {"ok":True,"version":"8.1-stable-prompt-v2.1","mode":"web"}

@app.route("/notifications",methods=["GET","POST"])
def notifications():
    return {"ok":True},200

@app.route("/login")
def login():
    store=ss()
    state=secrets.token_urlsafe(32); store["oauth_state"]=state
    qs=urlencode({"response_type":"code","client_id":APP_ID,"redirect_uri":REDIRECT_URI,"state":state})
    return redirect(AUTH_URL+"?"+qs)

@app.route("/reauthorize")
def reauthorize():
    store=ss(); store.pop("access_token",None); store.pop("refresh_token",None)
    return redirect("/login")

@app.route("/callback")
def callback():
    store=ss()
    if request.args.get("state")!=store.get("oauth_state"):
        store["error"]="OAuth state inválido."; return redirect("/")
    payload={"grant_type":"authorization_code","client_id":APP_ID,"client_secret":CLIENT_SECRET,
             "code":request.args.get("code"),"redirect_uri":REDIRECT_URI}
    try:
        r=requests.post(API+"/oauth/token",data=payload,
            headers={"Accept":"application/json","Content-Type":"application/x-www-form-urlencoded"},timeout=20)
        data=r.json()
    except Exception as e:
        store["error"]=str(e); return redirect("/")
    if r.status_code!=200 or not data.get("access_token"):
        store["error"]=f"Falha OAuth HTTP {r.status_code}: {data}"; return redirect("/")
    store["access_token"]=data["access_token"]; store["refresh_token"]=data.get("refresh_token")
    return redirect("/")

@app.route("/logout")
def logout():
    sid=session.get("sid")
    if sid: SERVER_SESSIONS.pop(sid,None)
    session.clear()
    return redirect("/")

@app.route("/analyze",methods=["POST"])
def analyze():
    store=ss(); text=request.form.get("links",""); store["last_links"]=text
    recs=parse_inputs(text)
    if not recs:
        store["error"]="Nenhum anúncio reconhecido."; return redirect("/")
    if len(recs)>8:
        store["error"]="Máximo de 8 anúncios."; return redirect("/")

    results=[]
    for rec in recs:
        try:
            results.append(collect(rec))
        except Exception as e:
            results.append({
                "raw":rec.get("raw"),
                "item_id":rec.get("item_id"),
                "product_ids":rec.get("product_ids") or [],
                "seller_id":None,
                "seller":None,
                "question_summary":{"status":0,"total":0,"questions":[]},
                "fields":{},
                "other_offers":[],
                "error":f"{type(e).__name__}: {e}",
                "_collected_at_unix":int(time.time())
            })

    store["results"]=results
    return redirect("/")

@app.route("/prompt")
def prompt_master():
    results=ss().get("results") or []
    if not results:
        ss()["error"]="Analise pelo menos um anúncio antes de gerar o Prompt Mestre."
        return redirect("/")
    prompt=build_master_prompt(results)
    return render_template_string(PROMPT_HTML,prompt=prompt)

@app.route("/export/prompt.txt")
def export_prompt():
    results=ss().get("results") or []
    if not results:
        return Response("Nenhum resultado analisado.",status=400,mimetype="text/plain")
    prompt=build_master_prompt(results)
    return Response(prompt.encode("utf-8"),mimetype="text/plain; charset=utf-8",
                    headers={"Content-Disposition":"attachment; filename=ml_v8_prompt_mestre.txt"})

@app.route("/export/json")
def export_json():
    data=ss().get("results") or []
    return Response(json.dumps(data,ensure_ascii=False,indent=2).encode("utf-8"),
                    mimetype="application/json",
                    headers={"Content-Disposition":"attachment; filename=ml_v8_resultado.json"})

@app.route("/export/csv")
def export_csv():
    data=ss().get("results") or []; out=StringIO()
    cols=["item_id","title","price","original_price","seller","seller_level","questions",
          "rating_average","reviews_total","warranty","logistic_type","free_shipping"]
    w=csv.DictWriter(out,fieldnames=cols); w.writeheader()
    for r in data:
        f=r.get("fields") or {}; s=r.get("seller") or {}; rep=s.get("seller_reputation") or {}
        def fv(k): return (f.get(k) or {}).get("value")
        ship=fv("shipping") or {}
        w.writerow({
            "item_id":r.get("item_id"),"title":fv("title"),"price":fv("price"),
            "original_price":fv("original_price"),"seller":s.get("nickname"),
            "seller_level":rep.get("level_id"),"questions":(r.get("question_summary") or {}).get("total"),
            "rating_average":fv("rating_average"),"reviews_total":fv("reviews_total"),
            "warranty":fv("warranty"),"logistic_type":ship.get("logistic_type"),
            "free_shipping":ship.get("free_shipping")
        })
    return Response(out.getvalue().encode("utf-8-sig"),mimetype="text/csv",
                    headers={"Content-Disposition":"attachment; filename=ml_v8_resumo.csv"})

if __name__=="__main__":
    app.run(host="0.0.0.0",port=int(os.getenv("PORT","8000")),debug=False)
