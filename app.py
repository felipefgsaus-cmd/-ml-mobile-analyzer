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
<h1>ML Analyzer+ Prompt Superior</h1>
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
<a class="btn green" href="/prompt">Gerar Prompt Mestre</a>
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
<div class="metric"><b>Total avaliações</b><span>{{ r.fields.reviews_total.value if r.fields.reviews_total else "Indisponível" }}</span>{% if r.fields.reviews_meta %}<div class="src">fontes: {{ (r.fields.reviews_meta.value.sources or [])|join(", ") if r.fields.reviews_meta.value else "" }}</div>{% endif %}</div>
<div class="metric"><b>Perguntas</b><span>{{ r.question_summary.total }}</span></div>
<div class="metric"><b>Fotos encontradas</b><span>{{ r.fields.all_pictures.value|length if r.fields.all_pictures else (r.fields.pictures.value|length if r.fields.pictures else 0) }}</span><div class="src">anúncio + variações + catálogo + ofertas</div></div>
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
<div class="qa"><b>{{ rv.title or ("Nota " ~ rv.rate) }}</b><br>{{ rv.content or rv.comment or "" }}{% if rv._source %}<div class="src">Origem: {{ rv._source }}</div>{% endif %}</div>
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
        for rv in reviews[:12]:
            if not isinstance(rv,dict): continue
            content=rv.get("content") or rv.get("title")
            if content:
                review_lines.append(f"- Nota {rv.get('rate','?')}: {_compact(content,500)} | Origem: {rv.get('_source','não informada')}")

        question_lines=[]
        for q in questions[:20]:
            if not isinstance(q,dict): continue
            question_lines.append(f"- Pergunta: {_compact(q.get('text'),400)} | Resposta: {_compact(q.get('answer'),500)}")

        attr_lines=[]
        for a in attrs[:40]:
            if not isinstance(a,dict): continue
            name=a.get("name") or a.get("id")
            val=a.get("value_name") or a.get("value")
            if name and val not in (None,""):
                attr_lines.append(f"- {name}: {_compact(val,300)}")

        offer_lines=[]
        for o in offers[:20]:
            if not isinstance(o,dict): continue
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
Descrição do anúncio: {_compact(_field_value(r,'description'),4000)}
Descrição/resumo do catálogo: {_compact(_field_value(r,'catalog_description'),2500)}
Destaques do catálogo: {_compact(_field_value(r,'main_features'),2500)}
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
    return f"""ATUE COMO UM ESPECIALISTA SÊNIOR EM MARKETPLACES, COPYWRITING, SEO PARA MERCADO LIVRE, CONVERSÃO E INTELIGÊNCIA COMPETITIVA.

Sua missão é criar a PUBLICAÇÃO IDEAL para superar os concorrentes analisados abaixo. Use os dados como inteligência competitiva, não copie textos dos concorrentes e não invente especificações técnicas que não possam ser sustentadas pelos dados. Quando algo estiver ausente ou incerto, sinalize claramente o que precisa ser confirmado comigo.

Foram analisados {len(valid)} anúncios.

====================
DADOS DOS CONCORRENTES
====================

{data}

====================
SUA TAREFA
====================

1. Faça primeiro uma SÍNTESE COMPETITIVA, identificando:
- padrões de títulos e palavras-chave relevantes;
- benefícios mais explorados;
- benefícios pouco explorados ou oportunidades de diferenciação;
- principais elogios encontrados nas avaliações;
- principais reclamações, objeções e riscos encontrados nas avaliações;
- dúvidas recorrentes encontradas nas perguntas;
- atributos técnicos que aparecem com frequência;
- padrões de preço, frete, logística, reputação e garantia;
- lacunas de informação dos concorrentes que podemos aproveitar.

2. Em seguida, crie a estratégia da PUBLICAÇÃO IDEAL, explicando brevemente como ela deve superar a média dos concorrentes sem fazer promessas falsas ou afirmações não comprovadas.

3. Crie o TÍTULO OTIMIZADO para Mercado Livre. Priorize intenção de busca, clareza, atributos decisivos e leitura natural. Não faça keyword stuffing. Se faltar uma especificação necessária, marque-a como [CONFIRMAR].

4. Crie a DESCRIÇÃO COMPLETA DO ANÚNCIO em português do Brasil, pronta para publicação, com:
- abertura objetiva;
- principais benefícios;
- diferenciais;
- especificações importantes;
- conteúdo da embalagem, somente quando comprovado;
- orientações de uso relevantes;
- garantia, somente quando disponível;
- respostas preventivas às objeções mais comuns;
- chamada final para compra sem exageros.

5. Monte a FICHA TÉCNICA IDEAL e separe em:
- atributos confirmados pelos dados;
- atributos importantes que ainda precisam ser confirmados comigo.

6. Crie uma FAQ com as perguntas que mais ajudam a converter, usando as dúvidas reais coletadas como base. Não invente respostas técnicas.

7. Crie um PLANO DE 10 IMAGENS para a publicação. Para cada imagem informe:
- objetivo da imagem;
- composição/cena;
- texto curto sugerido no infográfico, quando necessário;
- benefício que ela deve provar;
- o que precisa ser visualmente demonstrado.
A imagem 1 deve funcionar como capa principal de marketplace e respeitar boas práticas de fundo limpo e destaque do produto.

8. Crie, separadamente, um PROMPT DE GERAÇÃO DE IMAGEM para cada uma das 10 imagens, suficientemente detalhado para ser usado em um gerador de imagens. Não altere características físicas do produto que não estejam confirmadas.

9. Sugira de 5 a 10 pontos de MELHORIA EM RELAÇÃO AOS CONCORRENTES, ordenados por impacto esperado na conversão.

10. Termine com uma seção chamada "INFORMAÇÕES QUE PRECISO DO VENDEDOR", contendo somente as perguntas que realmente precisamos responder para finalizar um anúncio preciso e superior.

REGRAS IMPORTANTES:
- Não copie frases dos concorrentes.
- Não invente medidas, materiais, compatibilidades, certificações, conteúdo da embalagem, garantia ou desempenho.
- Diferencie fato observado de recomendação.
- Priorize conversão e clareza, mas mantenha conformidade com as regras do marketplace.
- Use português do Brasil.
- Entregue o resultado de forma organizada e pronta para uso.
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


def _picture_url(pic):
    if not isinstance(pic, dict): return None
    return pic.get("secure_url") or pic.get("url")

def _add_picture(bucket, url, source, picture_id=None):
    if not url: return
    url = str(url).replace("http://", "https://", 1)
    if any(x.get("url") == url for x in bucket): return
    bucket.append({"url":url,"source":source,"id":picture_id})

def _mlstatic_from_picture_id(picture_id):
    if not picture_id: return None
    return f"https://http2.mlstatic.com/D_NQ_NP_{picture_id}-O.jpg"

def collect_public_pictures(item_id, product_ids):
    found=[]; discovered=list(product_ids or [])
    for auth_mode in (True, False):
        st,d=api_get(f"/items/{item_id}",{"include_attributes":"all"},auth=auth_mode)
        if st==200 and isinstance(d,dict):
            cp=d.get("catalog_product_id")
            if cp and cp not in discovered: discovered.append(cp)
            _add_picture(found,d.get("secure_thumbnail") or d.get("thumbnail"),"thumbnail do anúncio")
            for pic in d.get("pictures") or []:
                _add_picture(found,_picture_url(pic),"fotos do anúncio",pic.get("id"))
            for var in d.get("variations") or []:
                if isinstance(var,dict):
                    cp=var.get("catalog_product_id")
                    if cp and cp not in discovered: discovered.append(cp)
                    for pid in var.get("picture_ids") or []:
                        _add_picture(found,_mlstatic_from_picture_id(pid),"variação do anúncio",pid)
    for product_id in discovered[:8]:
        st,p=api_get(f"/products/{product_id}",auth=True)
        if st!=200: st,p=api_get(f"/products/{product_id}",auth=False)
        if st==200 and isinstance(p,dict):
            _add_picture(found,p.get("secure_thumbnail") or p.get("thumbnail"),f"thumbnail catálogo {product_id}")
            for pic in p.get("pictures") or []:
                _add_picture(found,_picture_url(pic),f"catálogo {product_id}",pic.get("id"))
        st,offers=api_get(f"/products/{product_id}/items",{"site_id":"MLB"},True)
        if st==200 and isinstance(offers,dict):
            for offer in offers.get("results") or []:
                if not isinstance(offer,dict): continue
                _add_picture(found,offer.get("secure_thumbnail") or offer.get("thumbnail"),f"oferta relacionada {offer.get('item_id','')}")
                for pic in offer.get("pictures") or []:
                    _add_picture(found,_picture_url(pic),f"oferta relacionada {offer.get('item_id','')}",pic.get("id"))
    return found,discovered


def _review_content(rv):
    if not isinstance(rv, dict):
        return None
    return rv.get("content") or rv.get("title") or rv.get("comment")

def _normalize_review(rv, source):
    if not isinstance(rv, dict):
        return None
    out = dict(rv)
    out["_source"] = source
    return out

def _merge_reviews(target, reviews, source, limit=50):
    for rv in reviews or []:
        if not isinstance(rv, dict):
            continue
        n = _normalize_review(rv, source)
        content = (_review_content(n) or "").strip()
        rate = n.get("rate")
        # Deduplicate primarily by content+rate; keep source info.
        key = (content, rate)
        exists = False
        for cur in target:
            ckey = (((_review_content(cur) or "").strip()), cur.get("rate"))
            if key == ckey and (content or rate is not None):
                exists = True
                break
        if not exists:
            target.append(n)
        if len(target) >= limit:
            break

def collect_reviews_cascade(item_id, product_ids):
    """
    Coleta avaliações em cascata.
    1) Reviews do item.
    2) Tenta reviews do produto de catálogo quando o endpoint existir/retornar dados.
    3) Preserva origem e deduplica comentários.
    Nunca transforma review de catálogo em review exclusivo do vendedor.
    """
    reviews = []
    meta = {
        "item_status": None,
        "catalog_statuses": [],
        "rating_average": None,
        "reviews_total": None,
        "sources": []
    }

    # Item-level reviews
    st, d = api_get(f"/reviews/item/{item_id}", auth=True)
    meta["item_status"] = st
    if st == 200 and isinstance(d, dict):
        if d.get("rating_average") is not None:
            meta["rating_average"] = d.get("rating_average")
        total = (d.get("paging") or {}).get("total")
        if total is not None:
            meta["reviews_total"] = total
        item_reviews = d.get("reviews") or []
        if item_reviews:
            _merge_reviews(reviews, item_reviews, "review do anúncio")
            meta["sources"].append("item")

    # Product/catalog fallback.
    # Different ML resources/accounts may expose product reviews differently;
    # try multiple known shapes and accept only valid responses.
    for pid in (product_ids or [])[:8]:
        candidates = [
            f"/reviews/product/{pid}",
            f"/reviews/products/{pid}",
        ]
        got_for_pid = False
        for endpoint in candidates:
            st, d = api_get(endpoint, auth=True)
            meta["catalog_statuses"].append({"product_id": pid, "endpoint": endpoint, "status": st})
            if st == 200 and isinstance(d, dict):
                if meta["rating_average"] is None and d.get("rating_average") is not None:
                    meta["rating_average"] = d.get("rating_average")
                total = (d.get("paging") or {}).get("total")
                if meta["reviews_total"] is None and total is not None:
                    meta["reviews_total"] = total
                revs = d.get("reviews") or d.get("results") or []
                if revs:
                    _merge_reviews(reviews, revs, f"review do catálogo {pid}")
                    got_for_pid = True
                    if "catalog" not in meta["sources"]:
                        meta["sources"].append("catalog")
                    break
        if got_for_pid and len(reviews) >= 50:
            break

    return reviews, meta


def collect(rec):
    item_id=rec["item_id"]; pids=list(rec.get("product_ids") or [])
    fields={}; other_offers=[]
    all_pictures=[]

    if not item_id:
        return {
            "raw":rec.get("raw"),"item_id":None,"product_ids":pids,
            "seller_id":None,"seller":None,
            "question_summary":{"status":0,"total":0,"questions":[]},
            "fields":fields,"other_offers":[],
            "error":"ID do anúncio não reconhecido",
            "_collected_at_unix":int(time.time())
        }

    try:
        all_pictures,pids=collect_public_pictures(item_id,pids)
        if all_pictures:
            setf(fields,"all_pictures",all_pictures,"Fotos V3: anúncio + variações + catálogo + ofertas")
    except Exception:
        all_pictures=[]
    qsum,seller_id=questions(item_id)
    sel=seller(seller_id)

    # V4: avaliações/comentários em cascata, preservando a origem.
    try:
        cascade_reviews, review_meta = collect_reviews_cascade(item_id, pids)
        if review_meta.get("rating_average") is not None:
            setf(fields,"rating_average",review_meta.get("rating_average"),"Mercado Livre reviews em cascata")
        if review_meta.get("reviews_total") is not None:
            setf(fields,"reviews_total",review_meta.get("reviews_total"),"Mercado Livre reviews em cascata")
        if cascade_reviews:
            setf(fields,"reviews",cascade_reviews,"Mercado Livre reviews em cascata")
        setf(fields,"reviews_meta",review_meta,"Diagnóstico/origem das avaliações")
    except Exception as e:
        # Fallback absoluto para o comportamento anterior, sem quebrar a análise.
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
    return {"ok":True,"version":"8.4-fotos-reviews-v4","mode":"web"}

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
