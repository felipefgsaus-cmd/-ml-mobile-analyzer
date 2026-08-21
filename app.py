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
<title>ML Mobile Analyzer V6 Diagnostic</title>
<style>
body{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;background:#f5f5f5;color:#202020;margin:0}
.wrap{max-width:1180px;margin:auto;padding:18px}
.card{background:#fff;border:1px solid #dedede;border-radius:16px;padding:18px;margin:14px 0}
h1{font-size:27px;margin:3px 0 8px}h2{font-size:19px;margin:0 0 12px}h3{font-size:16px}
textarea{width:100%;min-height:180px;padding:12px;border:1px solid #bbb;border-radius:12px;font-size:16px;box-sizing:border-box}
button,.btn{background:#111;color:#fff;border:0;border-radius:12px;padding:13px 16px;font-size:15px;text-decoration:none;display:inline-block;cursor:pointer;margin:3px}
.btn.secondary{background:#555}.btn.blue{background:#1769aa}
.ok{color:#087a39}.bad{color:#a40000}.warn{color:#946200}.muted{color:#666;font-size:13px}
.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}
.metric{padding:12px;border:1px solid #e3e3e3;border-radius:12px;background:#fafafa}
.metric b{display:block;font-size:12px;color:#666;margin-bottom:5px}
.metric span{font-size:17px;font-weight:700}
table{border-collapse:collapse;width:100%;font-size:12px;display:block;overflow:auto}
th,td{border-bottom:1px solid #ddd;padding:8px;text-align:left;vertical-align:top;min-width:110px;max-width:380px;word-break:break-word}
.status200{color:#087a39;font-weight:700}.status403,.status401{color:#a40000;font-weight:700}.status0{color:#946200;font-weight:700}
pre{white-space:pre-wrap;word-break:break-word;background:#f7f7f7;padding:10px;border-radius:10px;font-size:11px;max-height:280px;overflow:auto}
.pill{display:inline-block;border:1px solid #ddd;border-radius:999px;padding:3px 7px;margin:2px;font-size:11px}
@media(max-width:700px){.grid{grid-template-columns:1fr}}
</style>
</head>
<body><div class="wrap">
<h1>ML Mobile Analyzer V6 Diagnostic</h1>
<p class="muted">Diagnóstico profundo das rotas oficiais. Não contorna 403, não usa proxy e não faz scraping do Mercado Livre.</p>

<div class="card">
<h2>1. OAuth / permissões</h2>
{% if not configured %}
<p class="bad">Variáveis OAuth ausentes no Render.</p>
{% elif token %}
<p class="ok">✓ Token ativo nesta sessão.</p>
<a class="btn secondary" href="/logout">Desconectar</a>
<a class="btn blue" href="/reauthorize">Reautorizar após alterar permissões</a>
<a class="btn" href="/diagnose-app">Diagnosticar aplicação/grants</a>
{% else %}
<a class="btn" href="/login">Conectar Mercado Livre</a>
{% endif %}
{% if appdiag %}
<h3>Aplicação / grants</h3>
<pre>{{ appdiag|tojson(indent=2) }}</pre>
{% endif %}
</div>

<div class="card">
<h2>2. Anúncios</h2>
<form method="post" action="/analyze">
<textarea name="links" placeholder="Cole 1 link completo ou ID por linha">{{ links or "" }}</textarea>
<p><button type="submit">Executar diagnóstico completo</button></p>
</form>
<p class="muted">Máximo 8 anúncios. A V6 faz uma tentativa por rota e registra o corpo do erro.</p>
</div>

{% if error %}<div class="card bad"><b>Erro:</b> {{ error }}</div>{% endif %}

{% if rows %}
<div class="card">
<h2>3. Exportar</h2>
<a class="btn" href="/export/json">JSON completo</a>
<a class="btn secondary" href="/export/csv">CSV resumo</a>
</div>

{% for r in rows %}
<div class="card">
<h2>{{ r.item_id or "Item não identificado" }}</h2>
<div class="grid">
<div class="metric"><b>Título</b><span>{{ r.fields.title.value if r.fields.title else "Indisponível" }}</span></div>
<div class="metric"><b>Preço atual</b><span>{{ r.fields.price.value if r.fields.price else "Indisponível" }}</span></div>
<div class="metric"><b>Vendedor</b><span>{{ r.seller.nickname if r.seller else "Indisponível" }}</span></div>
<div class="metric"><b>Perguntas</b><span>{{ r.question_summary.total }}</span></div>
<div class="metric"><b>Avaliação</b><span>{{ r.fields.rating_average.value if r.fields.rating_average else "Indisponível" }}</span></div>
<div class="metric"><b>Descrição</b><span>{{ "Disponível" if r.fields.description else "Indisponível" }}</span></div>
</div>

<h3>Diagnóstico por rota</h3>
<table>
<thead><tr><th>Teste</th><th>HTTP</th><th>Código</th><th>Mensagem</th><th>Blocked by</th><th>Observação</th></tr></thead>
<tbody>
{% for name,p in r.probes.items() %}
<tr>
<td>{{ name }}</td>
<td class="status{{ p.status }}">{{ p.status }}</td>
<td>{{ p.code or "" }}</td>
<td>{{ p.message or "" }}</td>
<td>{{ p.blocked_by or "" }}</td>
<td>{{ p.note or "" }}</td>
</tr>
{% endfor %}
</tbody>
</table>

{% if r.fields.attributes %}
<h3>Atributos recuperados ({{ r.fields.attributes.value|length }})</h3>
<table><thead><tr><th>Nome</th><th>Valor</th></tr></thead><tbody>
{% for a in r.fields.attributes.value %}
<tr><td>{{ a.name or a.id }}</td><td>{{ a.value_name or a.value or "" }}</td></tr>
{% endfor %}
</tbody></table>
{% endif %}

{% if r.question_summary.questions %}
<h3>Perguntas recuperadas</h3>
{% for q in r.question_summary.questions %}
<p><b>{{ q.text }}</b><br>{{ q.answer or "Sem resposta" }}</p>
{% endfor %}
{% endif %}

<details>
<summary>Ver respostas técnicas completas</summary>
<pre>{{ r.probes|tojson(indent=2) }}</pre>
</details>
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

def headers(auth=True, extra=None):
    h = {"Accept": "application/json", "User-Agent": "ML-Mobile-Analyzer/6.0"}
    if auth and token():
        h["Authorization"] = f"Bearer {token()}"
    if extra:
        h.update(extra)
    return h

def safe_json(resp):
    try:
        return resp.json()
    except Exception:
        return {"raw_text": resp.text[:8000]}

def normalize_error(data):
    if not isinstance(data, dict):
        return None, None, None
    return data.get("code"), data.get("message") or data.get("error"), data.get("blocked_by")

def probe(name, path, params=None, auth=True, extra_headers=None, note=None):
    try:
        r = requests.get(API + path, params=params, headers=headers(auth, extra_headers), timeout=20)
        data = safe_json(r)
        code, message, blocked_by = normalize_error(data)
        return {
            "name": name,
            "status": r.status_code,
            "code": code,
            "message": message,
            "blocked_by": blocked_by,
            "path": path,
            "params": params or {},
            "auth": auth,
            "note": note,
            "response": data,
            "response_headers": {
                k: v for k, v in r.headers.items()
                if k.lower() in {"x-request-id","x-content-type-options","content-type","retry-after"}
            }
        }
    except requests.RequestException as e:
        return {
            "name": name, "status": 0, "code": type(e).__name__,
            "message": str(e), "blocked_by": None, "path": path,
            "params": params or {}, "auth": auth, "note": note,
            "response": None, "response_headers": {}
        }

def fix_text(x):
    if not isinstance(x, str):
        return x
    # Mercado Livre sometimes returns already-decoded unicode; only repair obvious mojibake.
    if any(s in x for s in ("Ã", "Â", "â€", "â€™", "â€œ", "â€”")):
        try:
            return x.encode("latin-1").decode("utf-8")
        except Exception:
            return x
    return x

def parse_inputs(text):
    out = []
    for raw in [x.strip() for x in text.splitlines() if x.strip()]:
        item_q = re.findall(r'item_id(?:%3A|:|=)+(MLB\d{6,})', raw, flags=re.I)
        mlb = re.findall(r'\bMLB\d{6,}\b', raw.upper())
        mlbu = re.findall(r'\bMLBU\d{6,}\b', raw.upper())
        paths = [x.upper() for x in re.findall(r'/(?:p|up)/(MLB(?:U)?\d{6,})', raw, flags=re.I)]
        item_id = item_q[0].upper() if item_q else (mlb[-1] if mlb else None)
        product_ids = []
        for x in mlbu + paths:
            if x != item_id and x not in product_ids:
                product_ids.append(x)
        out.append({"raw": raw, "item_id": item_id, "product_ids": product_ids})
    return out

def set_field(fields, key, value, source, confidence="alta"):
    if value in (None, "", [], {}):
        return
    if key not in fields:
        fields[key] = {"value": value, "source": source, "confidence": confidence}

def item_to_fields(data, fields, source):
    if not isinstance(data, dict):
        return
    set_field(fields, "title", fix_text(data.get("title")), source)
    if data.get("price") is not None:
        set_field(fields, "price", f"{data.get('currency_id','')} {data.get('price')}".strip(), source)
    set_field(fields, "original_price", data.get("original_price"), source)
    set_field(fields, "sold_quantity", data.get("sold_quantity"), source)
    set_field(fields, "available_quantity", data.get("available_quantity"), source)
    set_field(fields, "attributes", data.get("attributes"), source)
    set_field(fields, "pictures", data.get("pictures"), source)
    set_field(fields, "shipping", data.get("shipping"), source)

def product_to_fields(data, fields, source):
    if not isinstance(data, dict):
        return
    set_field(fields, "title", fix_text(data.get("name") or data.get("title")), source)
    set_field(fields, "attributes", data.get("attributes"), source)
    set_field(fields, "pictures", data.get("pictures"), source)

def apply_prices(data, fields, source):
    if not isinstance(data, dict):
        return
    prices = data.get("prices") or []
    if prices:
        # Prefer promotion if active result contains one; otherwise standard.
        chosen = next((p for p in prices if p.get("type") == "promotion"), None)
        chosen = chosen or next((p for p in prices if p.get("type") == "standard"), None) or prices[0]
        if chosen.get("amount") is not None:
            set_field(fields, "price", f"{chosen.get('currency_id','')} {chosen.get('amount')}".strip(), source)
        set_field(fields, "regular_price", chosen.get("regular_amount"), source)
        set_field(fields, "all_prices", prices, source)

def get_questions(item_id):
    p = probe("questions_auth", "/questions/search", {"item": item_id, "api_version": 4, "limit": 50}, True)
    qs = []
    seller_id = None
    if p["status"] == 200 and isinstance(p["response"], dict):
        for q in p["response"].get("questions") or []:
            if not seller_id and q.get("seller_id"):
                seller_id = q.get("seller_id")
            qs.append({
                "id": q.get("id"),
                "date_created": q.get("date_created"),
                "seller_id": q.get("seller_id"),
                "status": q.get("status"),
                "text": fix_text(q.get("text")),
                "answer": fix_text((q.get("answer") or {}).get("text"))
            })
    return p, {"status": p["status"], "total": len(qs), "questions": qs}, seller_id

def get_seller(seller_id):
    if not seller_id:
        return None, None
    p = probe("seller_auth", f"/users/{seller_id}", auth=True)
    if p["status"] != 200 or not isinstance(p["response"], dict):
        return p, None
    d = p["response"]
    rep = d.get("seller_reputation") or {}
    tx = rep.get("transactions") or {}
    seller = {
        "id": d.get("id"),
        "nickname": fix_text(d.get("nickname")),
        "address": {k: fix_text(v) for k,v in (d.get("address") or {}).items()},
        "status": d.get("status"),
        "permalink": d.get("permalink"),
        "seller_reputation": {
            "level_id": rep.get("level_id"),
            "power_seller_status": rep.get("power_seller_status"),
            "transactions": {"period": tx.get("period"), "total": tx.get("total")}
        }
    }
    return p, seller

def collect(rec):
    item_id = rec.get("item_id")
    product_ids = list(rec.get("product_ids") or [])
    fields = {}
    probes = {}

    if not item_id:
        return {
            **rec, "seller_id": None, "seller": None,
            "question_summary": {"status":0,"total":0,"questions":[]},
            "fields": fields, "probes": probes, "_collected_at_unix": int(time.time())
        }

    # Item: authenticated and public, to distinguish auth policy vs route policy.
    p = probe("item_auth", f"/items/{item_id}", {"include_attributes":"all"}, True,
              note="Dados do anúncio individual.")
    probes[p["name"]] = p
    if p["status"] == 200:
        item_to_fields(p["response"], fields, "Mercado Livre API /items")
        cp = (p["response"] or {}).get("catalog_product_id")
        up = (p["response"] or {}).get("user_product_id")
        for x in (cp, up):
            if x and x not in product_ids:
                product_ids.append(x)

    p = probe("item_public", f"/items/{item_id}", {"include_attributes":"all"}, False,
              note="Controle: mesma rota sem Bearer.")
    probes[p["name"]] = p

    # New price APIs documented by Mercado Livre in 2026.
    p = probe("prices_auth", f"/items/{item_id}/prices", auth=True,
              extra_headers={"show-all-prices":"true"},
              note="Endpoint oficial de preços.")
    probes[p["name"]] = p
    if p["status"] == 200:
        apply_prices(p["response"], fields, "Mercado Livre API /items/{id}/prices")

    p = probe("sale_price_auth", f"/items/{item_id}/sale_price",
              {"context":"channel_marketplace"}, True,
              note="Preço atual de venda no marketplace.")
    probes[p["name"]] = p
    if p["status"] == 200 and isinstance(p["response"], dict):
        amount = p["response"].get("amount")
        if amount is not None:
            set_field(fields, "price", f"{p['response'].get('currency_id','')} {amount}".strip(),
                      "Mercado Livre API /sale_price")
        set_field(fields, "regular_price", p["response"].get("regular_amount"),
                  "Mercado Livre API /sale_price")

    # Description
    p = probe("description_auth", f"/items/{item_id}/description", auth=True,
              note="Descrição do anúncio.")
    probes[p["name"]] = p
    if p["status"] == 200 and isinstance(p["response"], dict):
        set_field(fields, "description",
                  fix_text(p["response"].get("plain_text") or p["response"].get("text")),
                  "Mercado Livre API /description")

    # Reviews by item.
    p = probe("reviews_item_auth", f"/reviews/item/{item_id}", auth=True,
              note="Reviews diretamente pelo item.")
    probes[p["name"]] = p
    if p["status"] == 200 and isinstance(p["response"], dict):
        set_field(fields, "rating_average", p["response"].get("rating_average"),
                  "Mercado Livre API /reviews/item")
        set_field(fields, "reviews_total", (p["response"].get("paging") or {}).get("total"),
                  "Mercado Livre API /reviews/item")
        set_field(fields, "reviews", p["response"].get("reviews"),
                  "Mercado Livre API /reviews/item")

    # Questions provide seller_id even when /items is blocked.
    qp, qsummary, seller_id = get_questions(item_id)
    probes[qp["name"]] = qp
    sp, seller = get_seller(seller_id)
    if sp:
        probes[sp["name"]] = sp

    # Product/catalog probes.
    for pid in product_ids[:4]:
        p = probe(f"product_{pid}_auth", f"/products/{pid}", auth=True,
                  note="Ficha de catálogo/produto.")
        probes[p["name"]] = p
        if p["status"] == 200:
            product_to_fields(p["response"], fields, f"Mercado Livre API /products/{pid}")

        ppub = probe(f"product_{pid}_public", f"/products/{pid}", auth=False,
                     note="Controle sem token.")
        probes[ppub["name"]] = ppub

        # Catalog-linked reviews, documented by ML for catalog items.
        pr = probe(f"reviews_catalog_{pid}", f"/reviews/item/{item_id}",
                   {"catalog_product_id": pid}, True,
                   note="Reviews usando catalog_product_id.")
        probes[pr["name"]] = pr
        if pr["status"] == 200 and isinstance(pr["response"], dict):
            set_field(fields, "rating_average", pr["response"].get("rating_average"),
                      f"Mercado Livre reviews catálogo {pid}")
            set_field(fields, "reviews_total", (pr["response"].get("paging") or {}).get("total"),
                      f"Mercado Livre reviews catálogo {pid}")
            set_field(fields, "reviews", pr["response"].get("reviews"),
                      f"Mercado Livre reviews catálogo {pid}")

        # Offers/items under product: useful diagnostic if allowed.
        po = probe(f"product_{pid}_items", f"/products/{pid}/items", {"site_id":"MLB"}, True,
                   note="Ofertas/itens ligados ao produto de catálogo.")
        probes[po["name"]] = po

    return {
        "raw": rec.get("raw"),
        "item_id": item_id,
        "product_ids": product_ids,
        "seller_id": seller_id,
        "seller": seller,
        "question_summary": qsummary,
        "fields": fields,
        "probes": probes,
        "_collected_at_unix": int(time.time())
    }

@app.route("/")
def home():
    store = ss()
    return render_template_string(
        HTML,
        configured=configured(),
        token=bool(store.get("access_token")),
        rows=store.get("results"),
        links=store.get("last_links",""),
        error=store.pop("error",None),
        appdiag=store.get("appdiag")
    )

@app.route("/health")
def health():
    return {"ok": True, "version": 6, "mode": "diagnostic"}

@app.route("/notifications", methods=["GET","POST"])
def notifications():
    return {"ok": True}, 200

@app.route("/login")
def login():
    store = ss()
    if not configured():
        store["error"] = "OAuth não configurado."
        return redirect("/")
    state = secrets.token_urlsafe(32)
    store["oauth_state"] = state
    qs = urlencode({
        "response_type":"code",
        "client_id":APP_ID,
        "redirect_uri":REDIRECT_URI,
        "state":state
    })
    return redirect(AUTH_URL + "?" + qs)

@app.route("/reauthorize")
def reauthorize():
    # Remove only local token, preserving last test data.
    store = ss()
    store.pop("access_token", None)
    store.pop("refresh_token", None)
    return redirect("/login")

@app.route("/callback")
def callback():
    store = ss()
    if request.args.get("state") != store.get("oauth_state"):
        store["error"] = "OAuth state inválido."
        return redirect("/")
    code = request.args.get("code")
    if not code:
        store["error"] = "Código OAuth ausente."
        return redirect("/")
    payload = {
        "grant_type":"authorization_code",
        "client_id":APP_ID,
        "client_secret":CLIENT_SECRET,
        "code":code,
        "redirect_uri":REDIRECT_URI
    }
    try:
        r = requests.post(API + "/oauth/token", data=payload,
                          headers={"Accept":"application/json",
                                   "Content-Type":"application/x-www-form-urlencoded"},
                          timeout=20)
        data = safe_json(r)
    except requests.RequestException as e:
        store["error"] = str(e)
        return redirect("/")
    if r.status_code != 200 or not isinstance(data,dict) or not data.get("access_token"):
        store["error"] = f"Falha OAuth HTTP {r.status_code}: {data}"
        return redirect("/")
    store["access_token"] = data["access_token"]
    store["refresh_token"] = data.get("refresh_token")
    store["oauth_state"] = None
    return redirect("/")

@app.route("/logout")
def logout():
    sid = session.get("sid")
    if sid:
        SERVER_SESSIONS.pop(sid, None)
    session.clear()
    return redirect("/")

@app.route("/diagnose-app")
def diagnose_app():
    store = ss()
    if not token():
        store["error"] = "Conecte a conta primeiro."
        return redirect("/")
    diag = {}
    for name,path in [
        ("application", f"/applications/{APP_ID}"),
        ("grants", f"/applications/{APP_ID}/grants"),
        ("me", "/users/me"),
    ]:
        p = probe(name, path, auth=True)
        diag[name] = p
    store["appdiag"] = diag
    return redirect("/")

@app.route("/analyze", methods=["POST"])
def analyze():
    store = ss()
    text = request.form.get("links","")
    store["last_links"] = text
    recs = parse_inputs(text)
    if not recs:
        store["error"] = "Nenhum anúncio reconhecido."
        return redirect("/")
    if len(recs) > 8:
        store["error"] = "Máximo de 8 anúncios."
        return redirect("/")
    store["results"] = [collect(r) for r in recs]
    return redirect("/")

@app.route("/export/json")
def export_json():
    data = ss().get("results") or []
    return Response(
        json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"),
        mimetype="application/json",
        headers={"Content-Disposition":"attachment; filename=ml_v6_diagnostico.json"}
    )

@app.route("/export/csv")
def export_csv():
    data = ss().get("results") or []
    out = StringIO()
    cols = [
        "item_id","seller","questions","title","price","description",
        "rating_average","reviews_total","item_auth","prices_auth",
        "sale_price_auth","description_auth","reviews_item_auth"
    ]
    w = csv.DictWriter(out, fieldnames=cols)
    w.writeheader()
    for r in data:
        f = r.get("fields") or {}
        probes = r.get("probes") or {}
        def fv(k): return (f.get(k) or {}).get("value")
        def ps(k): return (probes.get(k) or {}).get("status")
        w.writerow({
            "item_id": r.get("item_id"),
            "seller": (r.get("seller") or {}).get("nickname"),
            "questions": (r.get("question_summary") or {}).get("total"),
            "title": fv("title"),
            "price": fv("price"),
            "description": bool(fv("description")),
            "rating_average": fv("rating_average"),
            "reviews_total": fv("reviews_total"),
            "item_auth": ps("item_auth"),
            "prices_auth": ps("prices_auth"),
            "sale_price_auth": ps("sale_price_auth"),
            "description_auth": ps("description_auth"),
            "reviews_item_auth": ps("reviews_item_auth"),
        })
    return Response(
        out.getvalue().encode("utf-8-sig"),
        mimetype="text/csv",
        headers={"Content-Disposition":"attachment; filename=ml_v6_resumo.csv"}
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT","8000")), debug=False)
