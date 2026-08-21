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
.imported{white-space:pre-wrap;max-height:280px;overflow:auto;background:#fafafa;border:1px solid #eee;border-radius:10px;padding:10px}
@media(max-width:700px){.grid{grid-template-columns:1fr}}
</style>
</head>
<body><div class="wrap">
<h1>ML Analyzer V8</h1>
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
    h = {"Accept":"application/json","User-Agent":"ML-Analyzer/8.0"}
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
    out=[]
    for raw in [x.strip() for x in text.splitlines() if x.strip()]:
        q = re.findall(r'item_id(?:%3A|:|=)+(MLB\d{6,})', raw, flags=re.I)
        mlb = re.findall(r'\bMLB\d{6,}\b', raw.upper())
        mlbu = re.findall(r'\bMLBU\d{6,}\b', raw.upper())
        pathp = [x.upper() for x in re.findall(r'/(?:p|up)/(MLB(?:U)?\d{6,})', raw, flags=re.I)]
        item_id = q[0].upper() if q else (mlb[-1] if mlb else None)
        pids=[]
        for x in mlbu+pathp:
            if x != item_id and x not in pids: pids.append(x)
        out.append({"raw":raw,"item_id":item_id,"product_ids":pids})
    return out

def setf(fields,k,v,source,confidence="alta"):
    if v in (None,"",[],{}): return
    if k not in fields: fields[k]={"value":deep_fix(v),"source":source,"confidence":confidence}

def questions(item_id):
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
    qsum,seller_id=questions(item_id)
    sel=seller(seller_id)

    # Reviews now confirmed working.
    st,d=api_get(f"/reviews/item/{item_id}",auth=True)
    if st==200 and isinstance(d,dict):
        setf(fields,"rating_average",d.get("rating_average"),"Mercado Livre /reviews")
        setf(fields,"reviews_total",(d.get("paging") or {}).get("total"),"Mercado Livre /reviews")
        setf(fields,"reviews",d.get("reviews"),"Mercado Livre /reviews")

    # Description route can be 200 but blank.
    st,d=api_get(f"/items/{item_id}/description",auth=True)
    if st==200 and isinstance(d,dict):
        desc=d.get("plain_text") or d.get("text")
        setf(fields,"description",desc,"Mercado Livre /description")

    # Product gives title, attributes, images, short description, main features.
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
    return {"ok":True,"version":8,"mode":"web"}

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
    store["results"]=[collect(x) for x in recs]
    return redirect("/")


@app.route("/export/json")
def export_json():
    data=ss().get("results") or []
    return Response(json.dumps(data,ensure_ascii=False,indent=2).encode("utf-8"),
                    mimetype="application/json",
                    headers={"Content-Disposition":"attachment; filename=ml_v7_resultado.json"})

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
                    headers={"Content-Disposition":"attachment; filename=ml_v7_resumo.csv"})

if __name__=="__main__":
    app.run(host="0.0.0.0",port=int(os.getenv("PORT","8000")),debug=False)
