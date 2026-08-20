import os
import re
import csv
import json
import time
import secrets
from io import StringIO
from urllib.parse import urlencode

import requests
from flask import Flask, request, redirect, session, render_template_string, Response
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
<title>ML Mobile Analyzer V2</title>
<style>
body{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;background:#f7f7f7;color:#1f1f1f;margin:0}
.wrap{max-width:1100px;margin:auto;padding:18px}
.card{background:#fff;border:1px solid #e3e3e3;border-radius:16px;padding:18px;margin:14px 0}
h1{font-size:25px;margin:4px 0 8px} h2{font-size:19px}
textarea{width:100%;min-height:190px;padding:12px;border:1px solid #ccc;border-radius:12px;font-size:16px;box-sizing:border-box}
button,.btn{background:#111;color:#fff;border:0;border-radius:12px;padding:13px 16px;font-size:16px;text-decoration:none;display:inline-block;cursor:pointer}
.btn.secondary{background:#555}.muted{color:#666;font-size:14px}.ok{color:#087a39}.bad{color:#a40000}
table{border-collapse:collapse;width:100%;font-size:13px;display:block;overflow-x:auto}
th,td{border-bottom:1px solid #ddd;padding:8px;text-align:left;vertical-align:top;min-width:105px}
.status{font-weight:700}.s200{color:#087a39}.s401,.s403{color:#a40000}.s404{color:#9a5c00}
.small{font-size:12px}
</style>
</head>
<body><div class="wrap">
<h1>ML Mobile Analyzer V2</h1>
<p class="muted">Diagnóstico por rota da API oficial do Mercado Livre.</p>

<div class="card">
<h2>1. Conectar conta</h2>
{% if not configured %}
<p class="bad">Variáveis OAuth não configuradas.</p>
{% elif token %}
<p class="ok">✓ Conta Mercado Livre autorizada nesta sessão.</p>
<a class="btn secondary" href="/logout">Desconectar</a>
{% else %}
<a class="btn" href="/login">Conectar Mercado Livre</a>
{% endif %}
</div>

<div class="card">
<h2>2. Colar links completos ou IDs</h2>
<p class="muted">Prefira os links completos para capturar também IDs de produto/catálogo.</p>
<form method="post" action="/analyze">
<textarea name="links" placeholder="Cole 1 link completo ou ID por linha">{{ links or "" }}</textarea>
<p><button type="submit">Analisar concorrentes</button></p>
</form>
</div>

{% if error %}
<div class="card"><strong>Erro:</strong> {{ error }}</div>
{% endif %}

{% if rows %}
<div class="card">
<h2>3. Diagnóstico</h2>
<p><a class="btn" href="/export/json">Baixar JSON completo</a>
<a class="btn secondary" href="/export/csv">Baixar CSV diagnóstico</a></p>
<table>
<thead><tr>
<th>Item ID</th><th>Produto/Catálogo</th><th>Item auth</th><th>Item público</th><th>Multiget</th>
<th>Reviews</th><th>Questions</th><th>Catalog</th><th>Título recuperado</th><th>Preço</th>
</tr></thead>
<tbody>
{% for r in rows %}
<tr>
<td>{{ r.item_id or "—" }}</td>
<td>{{ (r.product_ids or [])|join(", ") or "—" }}</td>
{% for key in ["item_auth","item_public","item_multiget","reviews_auth","questions_auth","catalog_best"] %}
<td>
{% set p = r.probes.get(key) %}
{% if p %}
<span class="status s{{ p.status }}">{{ p.status }}</span>
{% if p.code %}<br><span class="small">{{ p.code }}</span>{% endif %}
{% else %}—{% endif %}
</td>
{% endfor %}
<td>{{ r.best.title if r.best else "—" }}</td>
<td>{{ r.best.currency_id if r.best else "" }} {{ r.best.price if r.best and r.best.price is not none else "—" }}</td>
</tr>
{% endfor %}
</tbody>
</table>
<p class="small muted">200 = respondeu; 401/403 = bloqueio; 404 = não encontrado. O JSON mostra a mensagem completa.</p>
</div>
{% endif %}
</div></body></html>
"""

def configured():
    return bool(APP_ID and CLIENT_SECRET and REDIRECT_URI)

def server_session():
    sid = session.get("sid")
    if not sid:
        sid = secrets.token_urlsafe(24)
        session["sid"] = sid
    return SERVER_SESSIONS.setdefault(sid, {})

def access_token():
    return server_session().get("access_token")

def auth_headers():
    tok = access_token()
    return {"Authorization": f"Bearer {tok}"} if tok else {}

def request_json(path, params=None, use_auth=True):
    headers = auth_headers() if use_auth else {}
    try:
        r = requests.get(API + path, params=params, headers=headers, timeout=25)
        try:
            data = r.json()
        except Exception:
            data = {"raw_text": r.text[:4000]}
        return r.status_code, data
    except requests.RequestException as e:
        return 0, {"exception": type(e).__name__, "message": str(e)}

def probe(path, params=None, use_auth=True):
    status, data = request_json(path, params=params, use_auth=use_auth)
    return {
        "status": status,
        "code": data.get("code") if isinstance(data, dict) else None,
        "message": data.get("message") if isinstance(data, dict) else None,
        "blocked_by": data.get("blocked_by") if isinstance(data, dict) else None,
        "data": data,
        "path": path,
        "params": params or {},
        "auth": use_auth,
    }

def parse_input(text):
    records = []
    for raw in [x.strip() for x in text.splitlines() if x.strip()]:
        item_ids = re.findall(r'\bMLB\d{6,}\b', raw.upper())
        mlbu = re.findall(r'\bMLBU\d{6,}\b', raw.upper())
        q_item = re.findall(r'item_id[:%3A=]+(MLB\d{6,})', raw, flags=re.I)
        q_item = [x.upper() for x in q_item]
        path_products = re.findall(r'/(?:p|up)/(MLB(?:U)?\d{6,})', raw, flags=re.I)
        path_products = [x.upper() for x in path_products]
        item_id = q_item[0] if q_item else (item_ids[-1] if item_ids else None)
        product_ids = []
        for x in mlbu + path_products:
            if x != item_id and x not in product_ids:
                product_ids.append(x)
        for x in item_ids:
            if x != item_id and x in path_products and x not in product_ids:
                product_ids.append(x)
        records.append({"raw": raw, "item_id": item_id, "product_ids": product_ids})
    return records

def summarize_item(data):
    if not isinstance(data, dict) or not data.get("id"):
        return None
    return {
        "id": data.get("id"),
        "title": data.get("title"),
        "price": data.get("price"),
        "original_price": data.get("original_price"),
        "currency_id": data.get("currency_id"),
        "seller_id": data.get("seller_id"),
        "category_id": data.get("category_id"),
        "catalog_product_id": data.get("catalog_product_id"),
        "sold_quantity": data.get("sold_quantity"),
        "available_quantity": data.get("available_quantity"),
        "pictures": data.get("pictures") or [],
        "attributes": data.get("attributes") or [],
        "shipping": data.get("shipping") or {},
        "permalink": data.get("permalink"),
    }

def summarize_multiget(data, item_id):
    if not isinstance(data, list):
        return None
    for entry in data:
        body = entry.get("body") if isinstance(entry, dict) else None
        if isinstance(entry, dict) and entry.get("code") == 200 and isinstance(body, dict) and body.get("id") == item_id:
            return summarize_item(body)
    return None

def summarize_product(data):
    if not isinstance(data, dict):
        return None
    title = data.get("name") or data.get("title")
    if not title:
        return None
    return {
        "id": data.get("id"),
        "title": title,
        "price": None,
        "original_price": None,
        "currency_id": "",
        "seller_id": None,
        "category_id": data.get("category_id"),
        "catalog_product_id": data.get("id"),
        "sold_quantity": None,
        "available_quantity": None,
        "pictures": data.get("pictures") or [],
        "attributes": data.get("attributes") or [],
        "shipping": {},
        "permalink": data.get("permalink"),
    }

def collect_record(rec):
    item_id = rec.get("item_id")
    product_ids = list(rec.get("product_ids") or [])
    probes, best = {}, None

    if item_id:
        probes["item_auth"] = probe(f"/items/{item_id}", {"include_attributes":"all"}, True)
        best = summarize_item(probes["item_auth"]["data"])

        probes["item_public"] = probe(f"/items/{item_id}", {"include_attributes":"all"}, False)
        if not best: best = summarize_item(probes["item_public"]["data"])

        probes["item_multiget"] = probe("/items", {"ids": item_id}, True)
        if not best: best = summarize_multiget(probes["item_multiget"]["data"], item_id)

        probes["item_multiget_public"] = probe("/items", {"ids": item_id}, False)
        if not best: best = summarize_multiget(probes["item_multiget_public"]["data"], item_id)

        probes["reviews_auth"] = probe(f"/reviews/item/{item_id}", use_auth=True)
        probes["reviews_public"] = probe(f"/reviews/item/{item_id}", use_auth=False)

        probes["questions_auth"] = probe("/questions/search", {"item": item_id, "api_version": 4, "limit": 50}, True)
        probes["questions_item_id_auth"] = probe("/questions/search", {"item_id": item_id, "api_version": 4, "limit": 50}, True)

        probes["description_auth"] = probe(f"/items/{item_id}/description", use_auth=True)
        probes["description_public"] = probe(f"/items/{item_id}/description", use_auth=False)

        for key in ("item_auth","item_public"):
            d = probes[key]["data"]
            if isinstance(d, dict):
                cp = d.get("catalog_product_id")
                if cp and cp not in product_ids:
                    product_ids.append(cp)

    catalog_results = []
    for pid in product_ids:
        pa = probe(f"/products/{pid}", use_auth=True)
        pp = probe(f"/products/{pid}", use_auth=False)
        probes[f"catalog_{pid}_auth"] = pa
        probes[f"catalog_{pid}_public"] = pp
        summary = summarize_product(pa["data"] if pa["status"] == 200 else pp["data"])
        catalog_results.append((pid, pa, pp, summary))
        if not best and summary: best = summary

    if catalog_results:
        chosen = None
        for _, pa, pp, _ in catalog_results:
            if pa["status"] == 200: chosen = pa; break
            if pp["status"] == 200: chosen = pp; break
        if chosen is None: chosen = catalog_results[0][1]
        probes["catalog_best"] = {
            "status": chosen["status"],
            "code": chosen.get("code"),
            "message": chosen.get("message"),
            "blocked_by": chosen.get("blocked_by"),
        }

    return {
        "raw": rec.get("raw"),
        "item_id": item_id,
        "product_ids": product_ids,
        "probes": probes,
        "best": best,
        "_collected_at_unix": int(time.time()),
    }

@app.route("/")
def home():
    ss = server_session()
    return render_template_string(
        HTML,
        configured=configured(),
        token=bool(ss.get("access_token")),
        rows=ss.get("results"),
        links=ss.get("last_links",""),
        error=ss.pop("error",None),
    )

@app.route("/health")
def health():
    return {"ok": True, "version": 2}

@app.route("/notifications", methods=["GET","POST"])
def notifications():
    return {"ok": True}, 200

@app.route("/login")
def login():
    ss = server_session()
    if not configured():
        ss["error"] = "Configuração OAuth ausente."
        return redirect("/")
    state = secrets.token_urlsafe(32)
    ss["oauth_state"] = state
    qs = urlencode({"response_type":"code","client_id":APP_ID,"redirect_uri":REDIRECT_URI,"state":state})
    return redirect(AUTH_URL + "?" + qs)

@app.route("/callback")
def callback():
    ss = server_session()
    if request.args.get("state") != ss.get("oauth_state"):
        ss["error"] = "Falha de segurança OAuth: state inválido."
        return redirect("/")
    code = request.args.get("code")
    if not code:
        ss["error"] = "Código de autorização não recebido."
        return redirect("/")
    payload = {
        "grant_type":"authorization_code",
        "client_id":APP_ID,
        "client_secret":CLIENT_SECRET,
        "code":code,
        "redirect_uri":REDIRECT_URI,
    }
    r = requests.post(API + "/oauth/token", data=payload,
                      headers={"accept":"application/json","content-type":"application/x-www-form-urlencoded"},
                      timeout=25)
    try: d = r.json()
    except Exception: d = {"raw_text": r.text[:4000]}
    if r.status_code != 200 or not d.get("access_token"):
        ss["error"] = f"Falha ao obter token: HTTP {r.status_code} — {d.get('message', d)}"
        return redirect("/")
    ss["access_token"] = d["access_token"]
    ss["oauth_state"] = None
    return redirect("/")

@app.route("/logout")
def logout():
    sid = session.get("sid")
    if sid: SERVER_SESSIONS.pop(sid, None)
    session.clear()
    return redirect("/")

@app.route("/analyze", methods=["POST"])
def analyze():
    ss = server_session()
    text = request.form.get("links","")
    ss["last_links"] = text
    records = parse_input(text)
    if not records:
        ss["error"] = "Nenhum link ou ID reconhecido."
        return redirect("/")
    if len(records) > 10:
        ss["error"] = "Use no máximo 10 anúncios por teste."
        return redirect("/")
    ss["results"] = [collect_record(r) for r in records]
    return redirect("/")

@app.route("/export/json")
def export_json():
    data = server_session().get("results") or []
    return Response(json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"),
                    mimetype="application/json",
                    headers={"Content-Disposition":"attachment; filename=ml_diagnostico_v2.json"})

@app.route("/export/csv")
def export_csv():
    data = server_session().get("results") or []
    out = StringIO()
    fields = ["item_id","product_ids","item_auth","item_public","item_multiget",
              "reviews_auth","reviews_public","questions_auth","description_auth",
              "catalog_best","title","price"]
    w = csv.DictWriter(out, fieldnames=fields); w.writeheader()
    for r in data:
        p = r.get("probes") or {}; best = r.get("best") or {}
        st = lambda k: (p.get(k) or {}).get("status")
        w.writerow({
            "item_id":r.get("item_id"),
            "product_ids":",".join(r.get("product_ids") or []),
            "item_auth":st("item_auth"),
            "item_public":st("item_public"),
            "item_multiget":st("item_multiget"),
            "reviews_auth":st("reviews_auth"),
            "reviews_public":st("reviews_public"),
            "questions_auth":st("questions_auth"),
            "description_auth":st("description_auth"),
            "catalog_best":st("catalog_best"),
            "title":best.get("title"),
            "price":best.get("price"),
        })
    return Response(out.getvalue().encode("utf-8-sig"), mimetype="text/csv",
                    headers={"Content-Disposition":"attachment; filename=ml_diagnostico_v2.csv"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT","8000")), debug=False)
