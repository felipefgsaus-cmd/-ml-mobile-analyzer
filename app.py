import os, re, json, csv, secrets, time
from io import StringIO
from urllib.parse import urlencode

import requests
from flask import Flask, request, redirect, session, render_template_string, Response
from dotenv import load_dotenv

load_dotenv()

APP_ID = os.getenv("ML_APP_ID","").strip()
CLIENT_SECRET = os.getenv("ML_CLIENT_SECRET","").strip()
REDIRECT_URI = os.getenv("ML_REDIRECT_URI","").strip()
FLASK_SECRET = os.getenv("FLASK_SECRET_KEY") or secrets.token_hex(32)
API = "https://api.mercadolibre.com"
AUTH_URL = "https://auth.mercadolivre.com.br/authorization"

app = Flask(__name__)
app.secret_key = FLASK_SECRET
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.getenv("SESSION_COOKIE_SECURE","1") == "1",
)

HTML = """
<!doctype html>
<html lang="pt-br">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ML Mobile Analyzer</title>
<style>
body{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;background:#f7f7f7;color:#1f1f1f;margin:0}
.wrap{max-width:980px;margin:auto;padding:18px}
.card{background:#fff;border:1px solid #e3e3e3;border-radius:16px;padding:18px;margin:14px 0;box-shadow:0 2px 10px rgba(0,0,0,.03)}
h1{font-size:25px;margin:4px 0 8px}
h2{font-size:19px}
textarea{width:100%;min-height:180px;padding:12px;border:1px solid #ccc;border-radius:12px;font-size:16px;box-sizing:border-box}
button,.btn{background:#111;color:white;border:0;border-radius:12px;padding:13px 16px;font-size:16px;text-decoration:none;display:inline-block;cursor:pointer}
.btn.secondary{background:#555}.muted{color:#666;font-size:14px}.ok{color:#087a39}.warn{color:#9a5c00}
table{border-collapse:collapse;width:100%;font-size:13px;display:block;overflow-x:auto}
th,td{border-bottom:1px solid #ddd;padding:8px;text-align:left;vertical-align:top;min-width:110px}
img{max-width:80px;max-height:80px;border-radius:8px}
code{background:#f0f0f0;padding:2px 4px;border-radius:4px}
.small{font-size:12px}
</style>
</head>
<body><div class="wrap">
<h1>ML Mobile Analyzer</h1>
<p class="muted">Cole links de concorrentes e consulte o que a API oficial do Mercado Livre permitir para sua autorização.</p>

<div class="card">
<h2>1. Conectar conta</h2>
{% if not configured %}
<p class="warn">Variáveis de ambiente ainda não configuradas.</p>
{% elif token %}
<p class="ok">✓ Conta Mercado Livre autorizada nesta sessão.</p>
<a class="btn secondary" href="/logout">Desconectar</a>
{% else %}
<a class="btn" href="/login">Conectar Mercado Livre</a>
{% endif %}
</div>

<div class="card">
<h2>2. Colar links</h2>
<form method="post" action="/analyze">
<textarea name="links" placeholder="Cole 1 link ou ID por linha">{{ links or "" }}</textarea>
<p><button type="submit">Analisar concorrentes</button></p>
</form>
</div>

{% if error %}
<div class="card"><strong>Erro:</strong> {{ error }}</div>
{% endif %}

{% if rows %}
<div class="card">
<h2>3. Resultado</h2>
<p>
<a class="btn" href="/export/json">Baixar JSON</a>
<a class="btn secondary" href="/export/csv">Baixar CSV</a>
</p>
<table>
<thead><tr><th>ID</th><th>Título</th><th>Preço</th><th>Vendas</th><th>Nota</th><th>Avaliações</th><th>Vendedor</th><th>Frete</th><th>Fotos</th></tr></thead>
<tbody>
{% for r in rows %}
<tr>
<td>{{ r.id }}</td>
<td>{{ r.title or "—" }}</td>
<td>{{ r.currency_id or "" }} {{ r.price if r.price is not none else "—" }}</td>
<td>{{ r.sold_quantity if r.sold_quantity is not none else "indisponível" }}</td>
<td>{{ r.reviews.rating_average if r.reviews and r.reviews.rating_average is not none else "—" }}</td>
<td>{{ r.reviews.paging.total if r.reviews and r.reviews.paging else "—" }}</td>
<td>{{ r.seller.nickname if r.seller else "—" }}</td>
<td>
{% if r.shipping %}
grátis: {{ r.shipping.free_shipping }}<br>
{{ r.shipping.logistic_type or "—" }}
{% else %}—{% endif %}
</td>
<td>{{ r.picture_count or 0 }}</td>
</tr>
{% endfor %}
</tbody>
</table>
<p class="small muted">Campos podem aparecer como indisponíveis se a API não os expuser para anúncios de terceiros.</p>
</div>
{% endif %}
</div></body></html>
"""

def is_configured():
    return bool(APP_ID and CLIENT_SECRET and REDIRECT_URI)

def headers():
    tok = session.get("access_token")
    return {"Authorization": f"Bearer {tok}"} if tok else {}

def api_get(path, params=None, fallback_public=True):
    r = requests.get(API+path, params=params, headers=headers(), timeout=25)
    if r.status_code in (401,403) and headers() and fallback_public:
        r = requests.get(API+path, params=params, timeout=25)
    try:
        data = r.json()
    except Exception:
        data = {"raw_text": r.text[:2000]}
    return r.status_code, data

def extract_ids(text):
    ids = re.findall(r'\bMLB\d{6,}\b', text.upper())
    out=[]; seen=set()
    for x in ids:
        if x not in seen:
            out.append(x); seen.add(x)
    return out

def slim_attrs(attrs):
    return [
        {"id":a.get("id"),"name":a.get("name"),"value_id":a.get("value_id"),"value_name":a.get("value_name")}
        for a in (attrs or [])
    ]

def get_desc(item_id):
    c,d = api_get(f"/items/{item_id}/description")
    return {"status":c, **(d if isinstance(d,dict) else {"data":d})}

def get_user(user_id):
    if not user_id: return None
    c,d = api_get(f"/users/{user_id}")
    if c==200 and isinstance(d,dict):
        return {
            "id":d.get("id"),
            "nickname":d.get("nickname"),
            "seller_reputation":d.get("seller_reputation"),
            "status":d.get("status"),
            "_http_status":c
        }
    return {"id":user_id,"_http_status":c,"_error":d}

def get_reviews(item_id):
    # Endpoint oficial documentado para opiniões do item.
    c,d = api_get(f"/reviews/item/{item_id}", fallback_public=False)
    if c==200 and isinstance(d,dict):
        return {
            "rating_average": d.get("rating_average"),
            "rating_levels": d.get("rating_levels"),
            "paging": d.get("paging"),
            "reviews": d.get("reviews") or [],
            "_http_status": c,
        }
    return {"rating_average":None,"paging":None,"reviews":[],"_http_status":c,"_error":d}

def normalize(body):
    pics=body.get("pictures") or []
    shipping=body.get("shipping") or {}
    return {
        "id":body.get("id"),
        "title":body.get("title"),
        "seller_id":body.get("seller_id"),
        "category_id":body.get("category_id"),
        "official_store_id":body.get("official_store_id"),
        "price":body.get("price"),
        "base_price":body.get("base_price"),
        "original_price":body.get("original_price"),
        "currency_id":body.get("currency_id"),
        "initial_quantity":body.get("initial_quantity"),
        "available_quantity":body.get("available_quantity"),
        "sold_quantity":body.get("sold_quantity"),
        "condition":body.get("condition"),
        "listing_type_id":body.get("listing_type_id"),
        "permalink":body.get("permalink"),
        "status":body.get("status"),
        "warranty":body.get("warranty"),
        "catalog_product_id":body.get("catalog_product_id"),
        "tags":body.get("tags") or [],
        "shipping":{
            "mode":shipping.get("mode"),
            "free_shipping":shipping.get("free_shipping"),
            "logistic_type":shipping.get("logistic_type"),
            "store_pick_up":shipping.get("store_pick_up"),
        },
        "picture_count":len(pics),
        "pictures":[{"id":p.get("id"),"url":p.get("secure_url") or p.get("url")} for p in pics],
        "attributes":slim_attrs(body.get("attributes")),
        "sale_terms":body.get("sale_terms") or [],
        "variations":body.get("variations") or [],
    }

def collect(ids):
    results=[]
    for item_id in ids:
        c,b=api_get(f"/items/{item_id}", params={"include_attributes":"all"})
        if c==200 and isinstance(b,dict):
            row=normalize(b)
            row["description"]=get_desc(item_id)
            row["seller"]=get_user(row.get("seller_id"))
            row["reviews"]=get_reviews(item_id)
        else:
            row={"id":item_id,"_item_http_status":c,"_item_error":b}
        row["_collected_at_unix"]=int(time.time())
        results.append(row)
    return results

@app.route("/")
def home():
    return render_template_string(
        HTML, configured=is_configured(), token=bool(session.get("access_token")),
        rows=session.get("results"), links=session.get("last_links",""),
        error=session.pop("error",None)
    )

@app.route("/health")
def health():
    return {"ok":True}

@app.route("/login")
def login():
    if not is_configured():
        session["error"]="Configuração OAuth ausente."
        return redirect("/")
    state=secrets.token_urlsafe(32)
    session["oauth_state"]=state
    qs=urlencode({
        "response_type":"code",
        "client_id":APP_ID,
        "redirect_uri":REDIRECT_URI,
        "state":state
    })
    return redirect(AUTH_URL+"?"+qs)

@app.route("/callback")
def callback():
    if request.args.get("state") != session.get("oauth_state"):
        session["error"]="Falha de segurança OAuth (state inválido)."
        return redirect("/")
    code=request.args.get("code")
    if not code:
        session["error"]="Código de autorização não recebido."
        return redirect("/")
    payload={
        "grant_type":"authorization_code",
        "client_id":APP_ID,
        "client_secret":CLIENT_SECRET,
        "code":code,
        "redirect_uri":REDIRECT_URI,
    }
    r=requests.post(
        API+"/oauth/token",
        data=payload,
        headers={"accept":"application/json","content-type":"application/x-www-form-urlencoded"},
        timeout=25
    )
    try:d=r.json()
    except Exception:d={"raw_text":r.text[:2000]}
    if r.status_code!=200 or not d.get("access_token"):
        session["error"]=f"Falha ao obter token: HTTP {r.status_code}"
        return redirect("/")
    session["access_token"]=d["access_token"]
    session["oauth_state"]=None
    return redirect("/")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

@app.route("/analyze", methods=["POST"])
def analyze():
    text=request.form.get("links","")
    session["last_links"]=text
    ids=extract_ids(text)
    if not ids:
        session["error"]="Nenhum ID MLB encontrado."
        return redirect("/")
    if len(ids)>20:
        session["error"]="Use no máximo 20 anúncios por vez."
        return redirect("/")
    try:
        session["results"]=collect(ids)
    except Exception as e:
        session["error"]=f"{type(e).__name__}: {e}"
    return redirect("/")

@app.route("/export/json")
def export_json():
    data=session.get("results") or []
    return Response(
        json.dumps(data,ensure_ascii=False,indent=2).encode("utf-8"),
        mimetype="application/json",
        headers={"Content-Disposition":"attachment; filename=ml_concorrentes.json"}
    )

@app.route("/export/csv")
def export_csv():
    data=session.get("results") or []
    out=StringIO()
    fields=["id","title","price","original_price","sold_quantity","rating_average","reviews_total","seller","seller_level","free_shipping","logistic_type","picture_count","permalink"]
    w=csv.DictWriter(out,fieldnames=fields); w.writeheader()
    for r in data:
        seller=r.get("seller") or {}; rep=seller.get("seller_reputation") or {}; rev=r.get("reviews") or {}; paging=rev.get("paging") or {}
        w.writerow({
            "id":r.get("id"),"title":r.get("title"),"price":r.get("price"),"original_price":r.get("original_price"),
            "sold_quantity":r.get("sold_quantity"),"rating_average":rev.get("rating_average"),"reviews_total":paging.get("total"),
            "seller":seller.get("nickname"),"seller_level":rep.get("level_id"),
            "free_shipping":(r.get("shipping") or {}).get("free_shipping"),
            "logistic_type":(r.get("shipping") or {}).get("logistic_type"),
            "picture_count":r.get("picture_count"),"permalink":r.get("permalink")
        })
    return Response(out.getvalue().encode("utf-8-sig"),mimetype="text/csv",
                    headers={"Content-Disposition":"attachment; filename=ml_concorrentes.csv"})

if __name__=="__main__":
    port=int(os.getenv("PORT","8000"))
    app.run(host="0.0.0.0",port=port,debug=False)
