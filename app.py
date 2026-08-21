import os
import re
import csv
import json
import time
import secrets
from io import StringIO
from urllib.parse import urlencode
from html import unescape

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
<title>ML Analyzer FINAL</title>
<style>
body{font-family:system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#f5f5f5;color:#202020;margin:0}
.wrap{max-width:1120px;margin:auto;padding:16px}
.card{background:#fff;border:1px solid #e1e1e1;border-radius:16px;padding:18px;margin:14px 0}
h1{font-size:26px;margin:2px 0 8px}h2{font-size:19px;margin:0 0 12px}h3{font-size:16px}
textarea,input{width:100%;box-sizing:border-box;padding:12px;border:1px solid #cfcfcf;border-radius:12px;font-size:16px}
textarea{min-height:155px}
button,.btn{display:inline-block;background:#111;color:white;border:0;border-radius:12px;padding:12px 15px;text-decoration:none;font-size:15px;cursor:pointer;margin:3px 3px 3px 0}
.btn.secondary{background:#555}.btn.blue{background:#1769aa}
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
<h1>ML Analyzer FINAL</h1>
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
<h3>Descrição</h3>
<p>{{ r.fields.catalog_description.value }}</p>
{% elif r.fields.description %}
<h3>Descrição</h3>
<p>{{ r.fields.description.value }}</p>
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
    h = {"Accept":"application/json","User-Agent":"ML-Analyzer/9.0"}
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



def _norm_mlb(v):
    if not isinstance(v, str):
        return None
    v = v.upper().replace("-", "").strip()
    return v if re.fullmatch(r"MLB\d{6,}", v) else None

def _add_pid(found, v, item_id):
    v = _norm_mlb(v)
    if v and v != item_id and v not in found:
        found.append(v)

def public_search_item(item_id, seller_id=None):
    """Fallback pela busca pública do ML para recuperar dados básicos e catalog_product_id."""
    params = {"q": item_id, "limit": 50}
    if seller_id:
        params["seller_id"] = seller_id
    for auth in (True, False):
        st, data = api_get("/sites/MLB/search", params, auth)
        if st == 200 and isinstance(data, dict):
            for row in data.get("results") or []:
                if isinstance(row, dict) and row.get("id") == item_id:
                    return deep_fix(row)
    return None

def fetch_public_page(raw_url, item_id):
    """Último fallback: abre a página pública e extrai dados estruturados do HTML."""
    urls = []
    if isinstance(raw_url, str) and raw_url.startswith(("http://", "https://")):
        urls.append(raw_url)

    # Formato curto padrão do item.
    digits = item_id.replace("MLB", "")
    urls.append(f"https://produto.mercadolivre.com.br/MLB-{digits}")

    headers = {
        "User-Agent": "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/124.0 Mobile Safari/537.36",
        "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.7",
    }

    for url in urls:
        try:
            r = requests.get(url, headers=headers, timeout=20, allow_redirects=True)
            if r.status_code >= 400 or not r.text:
                continue
            html = r.text
            final_url = r.url or url
            return {"url": final_url, "html": html}
        except requests.RequestException:
            continue
    return None

def extract_page_data(page, item_id):
    out = {"product_ids": [], "pictures": []}
    if not page:
        return out

    html = page.get("html") or ""
    final_url = page.get("url") or ""

    # Catálogo via URL final ou JSON embutido.
    for s in re.findall(r'/p/(MLB\d{6,})', final_url, flags=re.I):
        _add_pid(out["product_ids"], s, item_id)

    patterns = [
        r'"catalog_product_id"\s*:\s*"(MLB\d{6,})"',
        r'"catalogProductId"\s*:\s*"(MLB\d{6,})"',
        r'"product_id"\s*:\s*"(MLB\d{6,})"',
        r'"productId"\s*:\s*"(MLB\d{6,})"',
        r'/p/(MLB\d{6,})',
    ]
    for pat in patterns:
        for s in re.findall(pat, html, flags=re.I):
            _add_pid(out["product_ids"], s, item_id)

    # Metatags / JSON-LD para título, descrição, preço e imagens.
    def meta(prop):
        pats = [
            rf'<meta[^>]+(?:property|name)=["\']{re.escape(prop)}["\'][^>]+content=["\']([^"\']+)["\']',
            rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\']{re.escape(prop)}["\']',
        ]
        for p in pats:
            m = re.search(p, html, flags=re.I)
            if m:
                return unescape(m.group(1)).strip()
        return None

    out["title"] = meta("og:title") or meta("twitter:title")
    out["description"] = meta("og:description") or meta("description")
    out["price"] = meta("product:price:amount") or meta("og:price:amount")

    for prop in ("og:image", "twitter:image"):
        img = meta(prop)
        if img and img not in out["pictures"]:
            out["pictures"].append(img)

    # URLs de imagens do ML encontradas no HTML.
    for img in re.findall(r'https://http2\.mlstatic\.com/[^"\'\\\s<>]+?\.(?:jpg|jpeg|png|webp)', html, flags=re.I):
        img = img.replace("\\u002F", "/").replace("\\/", "/")
        if img not in out["pictures"]:
            out["pictures"].append(img)
        if len(out["pictures"]) >= 20:
            break

    # Alguns valores aparecem diretamente no JSON da página.
    if not out["price"]:
        m = re.search(r'"price"\s*:\s*([0-9]+(?:\.[0-9]+)?)', html)
        if m:
            out["price"] = m.group(1)

    return out

def discover_catalog_product_ids(item_id, review_data=None, seller_id=None, raw_url=None):
    found = []

    # 1) Reviews: secondary_key costuma apontar ao produto de catálogo.
    if isinstance(review_data, dict):
        for rv in review_data.get("reviews") or []:
            if isinstance(rv, dict):
                _add_pid(found, rv.get("secondary_key"), item_id)

    # 2) Item individual.
    st, data = api_get(f"/items/{item_id}", auth=True)
    if st == 200 and isinstance(data, dict):
        _add_pid(found, data.get("catalog_product_id"), item_id)

    # 3) Multi-GET.
    st, data = api_get("/items", {"ids": item_id}, True)
    if st == 200 and isinstance(data, list):
        for row in data:
            if not isinstance(row, dict):
                continue
            body = row.get("body") if isinstance(row.get("body"), dict) else row
            _add_pid(found, body.get("catalog_product_id"), item_id)

    # 4) Busca pública do item.
    sr = public_search_item(item_id, seller_id)
    if sr:
        _add_pid(found, sr.get("catalog_product_id"), item_id)

    # 5) Página pública.
    page = fetch_public_page(raw_url, item_id)
    pdata = extract_page_data(page, item_id)
    for pid in pdata.get("product_ids") or []:
        _add_pid(found, pid, item_id)

    return found, sr, pdata


def collect(rec):
    item_id = rec["item_id"]
    pids = list(rec.get("product_ids") or [])
    fields = {}
    other_offers = []

    if not item_id:
        return {
            "raw": rec.get("raw"), "item_id": None, "product_ids": pids,
            "seller_id": None, "seller": None,
            "question_summary": {"status": 0, "total": 0, "questions": []},
            "fields": fields, "other_offers": [],
            "error": "ID do anúncio não reconhecido",
            "_collected_at_unix": int(time.time())
        }

    # Perguntas e vendedor.
    qsum, seller_id = questions(item_id)
    sel = seller(seller_id)

    # Avaliações.
    review_data = None
    st, d = api_get(f"/reviews/item/{item_id}", auth=True)
    if st == 200 and isinstance(d, dict):
        review_data = d
        setf(fields, "rating_average", d.get("rating_average"), "Mercado Livre /reviews")
        setf(fields, "reviews_total", (d.get("paging") or {}).get("total"), "Mercado Livre /reviews")
        setf(fields, "reviews", d.get("reviews"), "Mercado Livre /reviews")

    # Descobre catálogo + fallback de busca/página pública.
    discovered, search_row, page_data = discover_catalog_product_ids(
        item_id, review_data=review_data, seller_id=seller_id, raw_url=rec.get("raw")
    )
    for pid in discovered:
        if pid not in pids:
            pids.append(pid)

    # Dados básicos pela busca pública, caso o catálogo não consiga fornecê-los.
    if search_row:
        setf(fields, "title", search_row.get("title"), "Mercado Livre /sites/MLB/search", "média")
        if search_row.get("price") is not None:
            cur = search_row.get("currency_id") or "BRL"
            setf(fields, "price", f"{cur} {search_row.get('price')}", "Mercado Livre /sites/MLB/search", "média")
        if search_row.get("original_price") is not None:
            cur = search_row.get("currency_id") or "BRL"
            setf(fields, "original_price", f"{cur} {search_row.get('original_price')}", "Mercado Livre /sites/MLB/search", "média")
        setf(fields, "shipping", search_row.get("shipping"), "Mercado Livre /sites/MLB/search", "média")

    # Página pública como fallback para título, descrição, preço e pelo menos imagens visíveis.
    if page_data:
        setf(fields, "title", page_data.get("title"), "Página pública Mercado Livre", "média")
        setf(fields, "description", page_data.get("description"), "Página pública Mercado Livre", "média")
        if page_data.get("price"):
            val = str(page_data.get("price"))
            if not val.upper().startswith("BRL"):
                val = f"BRL {val}"
            setf(fields, "price", val, "Página pública Mercado Livre", "média")
        if page_data.get("pictures"):
            pics = [{"id": None, "url": u} for u in page_data["pictures"]]
            setf(fields, "pictures", pics, "Página pública Mercado Livre", "média")

    # Descrição oficial do item quando disponível.
    st, d = api_get(f"/items/{item_id}/description", auth=True)
    if st == 200 and isinstance(d, dict):
        desc = d.get("plain_text") or d.get("text")
        setf(fields, "description", desc, "Mercado Livre /description")

    # Catálogo: fonte preferencial para título, ficha, fotos e descrição completa.
    for pid in pids[:6]:
        st, p = api_get(f"/products/{pid}", auth=True)
        if st == 200 and isinstance(p, dict):
            # Catálogo deve prevalecer sobre fallbacks médios.
            if p.get("name") or p.get("title"):
                fields["title"] = {"value": deep_fix(p.get("name") or p.get("title")),
                                   "source": f"Mercado Livre /products/{pid}", "confidence": "alta"}
            if p.get("attributes"):
                fields["attributes"] = {"value": deep_fix(p.get("attributes")),
                                        "source": f"Mercado Livre /products/{pid}", "confidence": "alta"}
            if p.get("pictures"):
                fields["pictures"] = {"value": deep_fix(p.get("pictures")),
                                      "source": f"Mercado Livre /products/{pid}", "confidence": "alta"}
            short = (p.get("short_description") or {}).get("content")
            if short:
                fields["catalog_description"] = {"value": deep_fix(short),
                                                 "source": f"Mercado Livre catálogo {pid}", "confidence": "alta"}
            if p.get("main_features"):
                fields["main_features"] = {"value": deep_fix(p.get("main_features")),
                                           "source": f"Mercado Livre catálogo {pid}", "confidence": "alta"}

        st, offers = api_get(f"/products/{pid}/items", {"site_id": "MLB"}, True)
        if st == 200 and isinstance(offers, dict):
            results = deep_fix(offers.get("results") or [])
            if results:
                other_offers = results
            own = next((x for x in results if x.get("item_id") == item_id), None)
            if own:
                if own.get("price") is not None:
                    fields["price"] = {
                        "value": f"{own.get('currency_id','')} {own.get('price')}".strip(),
                        "source": f"Mercado Livre /products/{pid}/items", "confidence": "alta"
                    }
                if own.get("original_price") is not None:
                    fields["original_price"] = {
                        "value": f"{own.get('currency_id','')} {own.get('original_price')}".strip(),
                        "source": f"Mercado Livre /products/{pid}/items", "confidence": "alta"
                    }
                setf(fields, "shipping", own.get("shipping"), f"Mercado Livre /products/{pid}/items")
                setf(fields, "warranty", own.get("warranty"), f"Mercado Livre /products/{pid}/items")
                setf(fields, "listing_type_id", own.get("listing_type_id"), f"Mercado Livre /products/{pid}/items")
                setf(fields, "user_product_id", own.get("user_product_id"), f"Mercado Livre /products/{pid}/items")

    # Se houver descrição do item mas não descrição de catálogo, exibe também como descrição principal.
    if fields.get("description") and not fields.get("catalog_description"):
        fields["catalog_description"] = fields["description"]

    return {
        "raw": rec.get("raw"),
        "item_id": item_id,
        "product_ids": pids,
        "seller_id": seller_id,
        "seller": sel,
        "question_summary": qsum,
        "fields": fields,
        "other_offers": other_offers,
        "_collected_at_unix": int(time.time())
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
    return {"ok":True,"version":"9.0-final","mode":"web"}

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

@app.route("/export/json")
def export_json():
    data=ss().get("results") or []
    return Response(json.dumps(data,ensure_ascii=False,indent=2).encode("utf-8"),
                    mimetype="application/json",
                    headers={"Content-Disposition":"attachment; filename=ml_analyzer_final_resultado.json"})

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
                    headers={"Content-Disposition":"attachment; filename=ml_analyzer_final_resumo.csv"})

if __name__=="__main__":
    app.run(host="0.0.0.0",port=int(os.getenv("PORT","8000")),debug=False)
