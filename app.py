import os
import re
import csv
import json
import time
import secrets
from io import StringIO
from urllib.parse import urlencode, quote_plus

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
<title>ML Mobile Analyzer V5</title>
<style>
body{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;background:#f6f6f6;color:#202020;margin:0}
.wrap{max-width:1180px;margin:auto;padding:18px}
.card{background:#fff;border:1px solid #e3e3e3;border-radius:16px;padding:18px;margin:14px 0}
h1{font-size:26px;margin:4px 0 8px} h2{font-size:19px;margin-top:0}
textarea{width:100%;min-height:185px;padding:12px;border:1px solid #ccc;border-radius:12px;font-size:16px;box-sizing:border-box}
button,.btn{background:#111;color:#fff;border:0;border-radius:12px;padding:13px 16px;font-size:16px;text-decoration:none;display:inline-block;cursor:pointer}
.btn.secondary{background:#555}.muted{color:#666;font-size:14px}.ok{color:#087a39}.bad{color:#a40000}
.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}
.metric{background:#fafafa;border:1px solid #e5e5e5;border-radius:12px;padding:14px}
.metric b{display:block;font-size:13px;color:#666;margin-bottom:6px}.metric span{font-size:18px;font-weight:700}
.qa{border-top:1px solid #e7e7e7;padding:12px 0}.qa:first-child{border-top:0}.q{font-weight:700;margin-bottom:7px}.a{color:#444}
.meta{font-size:12px;color:#777;margin-top:6px}.src{font-size:11px;color:#777;margin-top:6px}
.pill{display:inline-block;padding:3px 7px;border:1px solid #ddd;border-radius:999px;font-size:11px;margin:2px}
table{border-collapse:collapse;width:100%;font-size:12px;display:block;overflow-x:auto}
th,td{border-bottom:1px solid #ddd;padding:8px;text-align:left;vertical-align:top;min-width:105px}
@media(max-width:650px){.grid{grid-template-columns:1fr}}
</style>
</head>
<body><div class="wrap">
<h1>ML Mobile Analyzer V5</h1>
<p class="muted">Máximo de dados possível com rotas oficiais/gratuitas, sem insistir em 403 e sem serviços pagos.</p>

<div class="card">
<h2>1. Conectar conta</h2>
{% if not configured %}
<p class="bad">OAuth do Mercado Livre não configurado.</p>
{% elif token %}
<p class="ok">✓ Conta Mercado Livre autorizada nesta sessão.</p>
<a class="btn secondary" href="/logout">Desconectar</a>
{% else %}
<a class="btn" href="/login">Conectar Mercado Livre</a>
{% endif %}
</div>

<div class="card">
<h2>2. Colar anúncios</h2>
<form method="post" action="/analyze">
<textarea name="links" placeholder="Cole 1 link completo ou ID por linha">{{ links or "" }}</textarea>
<p><button type="submit">Analisar concorrentes</button></p>
</form>
<p class="muted">Máximo de 8 anúncios por análise.</p>
</div>

{% if error %}
<div class="card"><strong>Erro:</strong> {{ error }}</div>
{% endif %}

{% if rows %}
<div class="card">
<h2>3. Resultados</h2>
<p><a class="btn" href="/export/json">Baixar JSON completo</a>
<a class="btn secondary" href="/export/csv">Baixar CSV resumo</a></p>
</div>

{% for r in rows %}
<div class="card">
<h2>{{ r.item_id or "Item não identificado" }}</h2>

<div class="grid">
<div class="metric"><b>Título</b><span>{{ r.fields.title.value if r.fields.title else "Indisponível" }}</span>
{% if r.fields.title %}<div class="src">{{ r.fields.title.source }} · confiança {{ r.fields.title.confidence }}</div>{% endif %}</div>

<div class="metric"><b>Preço</b><span>{{ r.fields.price.value if r.fields.price else "Indisponível" }}</span>
{% if r.fields.price %}<div class="src">{{ r.fields.price.source }} · confiança {{ r.fields.price.confidence }}</div>{% endif %}</div>

<div class="metric"><b>Vendedor</b><span>{{ r.seller.nickname if r.seller else "Indisponível" }}</span></div>

<div class="metric"><b>Reputação</b><span>
{% if r.seller and r.seller.seller_reputation %}{{ r.seller.seller_reputation.level_id or "Indisponível" }}
{% else %}Indisponível{% endif %}
</span></div>

<div class="metric"><b>Transações históricas do vendedor</b><span>
{% if r.seller and r.seller.seller_reputation and r.seller.seller_reputation.transactions %}
{{ r.seller.seller_reputation.transactions.total or 0 }}{% else %}0{% endif %}
</span></div>

<div class="metric"><b>Perguntas</b><span>{{ r.question_summary.total if r.question_summary else 0 }}</span></div>

<div class="metric"><b>Descrição</b><span>{{ "Disponível" if r.fields.description else "Indisponível" }}</span>
{% if r.fields.description %}<div class="src">{{ r.fields.description.source }} · confiança {{ r.fields.description.confidence }}</div>{% endif %}</div>

<div class="metric"><b>Atributos</b><span>{{ r.fields.attributes.value|length if r.fields.attributes else 0 }}</span>
{% if r.fields.attributes %}<div class="src">{{ r.fields.attributes.source }} · confiança {{ r.fields.attributes.confidence }}</div>{% endif %}</div>
</div>

{% if r.fields.description %}
<h2 style="margin-top:22px">Descrição recuperada</h2>
<p>{{ r.fields.description.value }}</p>
{% endif %}

{% if r.fields.attributes %}
<h2 style="margin-top:22px">Atributos recuperados</h2>
<table>
<thead><tr><th>Atributo</th><th>Valor</th></tr></thead>
<tbody>
{% for a in r.fields.attributes.value %}
<tr><td>{{ a.name or a.id or "—" }}</td><td>{{ a.value_name or a.value or "—" }}</td></tr>
{% endfor %}
</tbody>
</table>
{% endif %}

{% if r.question_summary and r.question_summary.questions %}
<h2 style="margin-top:22px">Perguntas e respostas</h2>
{% for q in r.question_summary.questions %}
<div class="qa">
<div class="q">{{ q.text or "Pergunta sem texto" }}</div>
<div class="a">{{ q.answer or "Sem resposta" }}</div>
<div class="meta">{{ q.date_created or "" }}</div>
</div>
{% endfor %}
{% endif %}

{% if r.fallback_links %}
<h2 style="margin-top:22px">Buscas públicas sugeridas</h2>
{% for x in r.fallback_links %}
<div><span class="pill">{{ x.label }}</span> <span class="muted">{{ x.query }}</span></div>
{% endfor %}
{% endif %}
</div>
{% endfor %}
{% endif %}

<div class="card">
<p class="muted">A V5 tenta cada rota uma vez. Se receber 403/401, ela segue para as próximas fontes e não insiste.</p>
</div>
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

def get_json(path, params=None, use_auth=True):
    try:
        r = requests.get(
            API + path,
            params=params,
            headers=auth_headers() if use_auth else {},
            timeout=20
        )
        try:
            data = r.json()
        except Exception:
            data = {"raw_text": r.text[:4000]}
        return r.status_code, data
    except requests.RequestException as e:
        return 0, {"exception": type(e).__name__, "message": str(e)}

def fix_mojibake(text):
    if not isinstance(text, str):
        return text
    if "Ã" in text or "â€" in text or "Â" in text:
        try:
            return text.encode("latin1").decode("utf-8")
        except Exception:
            return text
    return text

def parse_input(text):
    out = []
    for raw in [x.strip() for x in text.splitlines() if x.strip()]:
        all_mlb = re.findall(r'\bMLB\d{6,}\b', raw.upper())
        all_mlbu = re.findall(r'\bMLBU\d{6,}\b', raw.upper())
        q_item = re.findall(r'item_id(?:%3A|:|=)+(MLB\d{6,})', raw, flags=re.I)
        q_item = [x.upper() for x in q_item]
        path_products = re.findall(r'/(?:p|up)/(MLB(?:U)?\d{6,})', raw, flags=re.I)
        path_products = [x.upper() for x in path_products]
        item_id = q_item[0] if q_item else (all_mlb[-1] if all_mlb else None)

        product_ids = []
        for x in all_mlbu + path_products:
            if x != item_id and x not in product_ids:
                product_ids.append(x)

        out.append({
            "raw": raw,
            "item_id": item_id,
            "product_ids": product_ids
        })
    return out

def set_field(fields, key, value, source, confidence):
    if value in (None, "", [], {}):
        return
    if key not in fields:
        fields[key] = {
            "value": value,
            "source": source,
            "confidence": confidence
        }

def summarize_item(data):
    if not isinstance(data, dict) or not data.get("id"):
        return {}
    return {
        "title": fix_mojibake(data.get("title")),
        "price": data.get("price"),
        "original_price": data.get("original_price"),
        "currency_id": data.get("currency_id"),
        "sold_quantity": data.get("sold_quantity"),
        "available_quantity": data.get("available_quantity"),
        "pictures": data.get("pictures") or [],
        "attributes": data.get("attributes") or [],
        "shipping": data.get("shipping") or {},
        "permalink": data.get("permalink"),
        "catalog_product_id": data.get("catalog_product_id"),
        "seller_id": data.get("seller_id"),
    }

def summarize_product(data):
    if not isinstance(data, dict):
        return {}
    return {
        "title": fix_mojibake(data.get("name") or data.get("title")),
        "pictures": data.get("pictures") or [],
        "attributes": data.get("attributes") or [],
        "category_id": data.get("category_id"),
        "permalink": data.get("permalink"),
    }

def get_questions(item_id):
    status, data = get_json("/questions/search", {
        "item": item_id,
        "api_version": 4,
        "limit": 50
    }, True)

    questions = []
    if status == 200 and isinstance(data, dict):
        for q in data.get("questions") or []:
            questions.append({
                "id": q.get("id"),
                "date_created": q.get("date_created"),
                "seller_id": q.get("seller_id"),
                "status": q.get("status"),
                "text": fix_mojibake(q.get("text")),
                "answer": fix_mojibake((q.get("answer") or {}).get("text")),
            })

    return {
        "status": status,
        "total": len(questions),
        "questions": questions
    }

def get_seller(seller_id):
    if not seller_id:
        return None
    status, data = get_json(f"/users/{seller_id}", use_auth=True)
    if status != 200 or not isinstance(data, dict):
        return None

    rep = data.get("seller_reputation") or {}
    tx = rep.get("transactions") or {}
    return {
        "id": data.get("id"),
        "nickname": fix_mojibake(data.get("nickname")),
        "seller_reputation": {
            "level_id": rep.get("level_id"),
            "power_seller_status": rep.get("power_seller_status"),
            "transactions": {
                "period": tx.get("period"),
                "total": tx.get("total")
            }
        },
        "status": data.get("status"),
        "address": data.get("address"),
        "permalink": data.get("permalink")
    }

def collect_record(rec):
    item_id = rec.get("item_id")
    product_ids = list(rec.get("product_ids") or [])
    fields = {}
    diagnostics = {}

    # 1) Item autenticado
    if item_id:
        st, data = get_json(f"/items/{item_id}", {"include_attributes":"all"}, True)
        diagnostics["item_auth"] = st
        if st == 200:
            s = summarize_item(data)
            set_field(fields, "title", s.get("title"), "Mercado Livre API /items", "alta")
            if s.get("price") is not None:
                cur = s.get("currency_id") or ""
                set_field(fields, "price", f"{cur} {s.get('price')}".strip(), "Mercado Livre API /items", "alta")
            set_field(fields, "sold_quantity", s.get("sold_quantity"), "Mercado Livre API /items", "alta")
            set_field(fields, "available_quantity", s.get("available_quantity"), "Mercado Livre API /items", "alta")
            set_field(fields, "pictures", s.get("pictures"), "Mercado Livre API /items", "alta")
            set_field(fields, "attributes", s.get("attributes"), "Mercado Livre API /items", "alta")
            set_field(fields, "shipping", s.get("shipping"), "Mercado Livre API /items", "alta")
            if s.get("catalog_product_id") and s.get("catalog_product_id") not in product_ids:
                product_ids.append(s.get("catalog_product_id"))

    # 2) Descrição
    if item_id:
        st, data = get_json(f"/items/{item_id}/description", use_auth=True)
        diagnostics["description_auth"] = st
        if st == 200 and isinstance(data, dict):
            desc = fix_mojibake(data.get("plain_text") or data.get("text"))
            set_field(fields, "description", desc, "Mercado Livre API /description", "alta")

    # 3) Reviews
    if item_id:
        st, data = get_json(f"/reviews/item/{item_id}", use_auth=True)
        diagnostics["reviews_auth"] = st
        if st == 200 and isinstance(data, dict):
            set_field(fields, "rating_average", data.get("rating_average"), "Mercado Livre API /reviews", "alta")
            paging = data.get("paging") or {}
            set_field(fields, "reviews_total", paging.get("total"), "Mercado Livre API /reviews", "alta")
            revs = data.get("reviews") or []
            if revs:
                slim = []
                for r in revs[:50]:
                    slim.append({
                        "rating": r.get("rate") or r.get("rating"),
                        "content": fix_mojibake(r.get("content") or r.get("text")),
                        "date_created": r.get("date_created")
                    })
                set_field(fields, "reviews", slim, "Mercado Livre API /reviews", "alta")

    # 4) Questions
    qs = get_questions(item_id) if item_id else {"status":0,"total":0,"questions":[]}
    seller_id = None
    for q in qs.get("questions") or []:
        if q.get("seller_id"):
            seller_id = q["seller_id"]
            break

    seller = get_seller(seller_id)

    # 5) Catálogo
    for pid in product_ids[:3]:
        st, data = get_json(f"/products/{pid}", use_auth=True)
        diagnostics[f"product_{pid}"] = st
        if st == 200:
            s = summarize_product(data)
            set_field(fields, "title", s.get("title"), f"Mercado Livre API /products/{pid}", "alta")
            set_field(fields, "pictures", s.get("pictures"), f"Mercado Livre API /products/{pid}", "alta")
            set_field(fields, "attributes", s.get("attributes"), f"Mercado Livre API /products/{pid}", "alta")

    # 6) Seller/profile can sometimes expose indirect clues but not item fields.
    # We keep it separate and do not infer unsupported item facts from seller history.

    # 7) Fallback gratuito: montar buscas públicas sugeridas para o usuário/ChatGPT,
    # sem chamar uma API paga e sem fazer scraping direto do ML.
    fallback_links = []
    qterms = [item_id] + product_ids
    for q in qterms:
        if not q:
            continue
        fallback_links.append({
            "label": "Busca por ID",
            "query": f'"{q}" Mercado Livre'
        })
    if seller and seller.get("nickname") and item_id:
        fallback_links.append({
            "label": "Busca por vendedor",
            "query": f'"{item_id}" "{seller.get("nickname")}"'
        })

    return {
        "raw": rec.get("raw"),
        "item_id": item_id,
        "product_ids": product_ids,
        "seller_id": seller_id,
        "seller": seller,
        "question_summary": qs,
        "fields": fields,
        "fallback_links": fallback_links,
        "diagnostics": diagnostics,
        "_collected_at_unix": int(time.time())
    }

@app.route("/")
def home():
    ss = server_session()
    return render_template_string(
        HTML,
        configured=configured(),
        token=bool(ss.get("access_token")),
        rows=ss.get("results"),
        links=ss.get("last_links", ""),
        error=ss.pop("error", None),
    )

@app.route("/health")
def health():
    return {"ok": True, "version": 5, "mode": "max-free"}

@app.route("/notifications", methods=["GET", "POST"])
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

    qs = urlencode({
        "response_type": "code",
        "client_id": APP_ID,
        "redirect_uri": REDIRECT_URI,
        "state": state
    })
    return redirect(AUTH_URL + "?" + qs)

@app.route("/callback")
def callback():
    ss = server_session()

    if request.args.get("state") != ss.get("oauth_state"):
        ss["error"] = "Falha OAuth: state inválido."
        return redirect("/")

    code = request.args.get("code")
    if not code:
        ss["error"] = "Código de autorização não recebido."
        return redirect("/")

    payload = {
        "grant_type": "authorization_code",
        "client_id": APP_ID,
        "client_secret": CLIENT_SECRET,
        "code": code,
        "redirect_uri": REDIRECT_URI
    }

    try:
        r = requests.post(
            API + "/oauth/token",
            data=payload,
            headers={"accept":"application/json","content-type":"application/x-www-form-urlencoded"},
            timeout=20
        )
        try:
            data = r.json()
        except Exception:
            data = {"raw_text": r.text[:3000]}
    except requests.RequestException as e:
        ss["error"] = f"Falha OAuth: {e}"
        return redirect("/")

    if r.status_code != 200 or not data.get("access_token"):
        ss["error"] = f"Falha ao obter token: HTTP {r.status_code}"
        return redirect("/")

    ss["access_token"] = data["access_token"]
    ss["oauth_state"] = None
    return redirect("/")

@app.route("/logout")
def logout():
    sid = session.get("sid")
    if sid:
        SERVER_SESSIONS.pop(sid, None)
    session.clear()
    return redirect("/")

@app.route("/analyze", methods=["POST"])
def analyze():
    ss = server_session()
    text = request.form.get("links", "")
    ss["last_links"] = text

    records = parse_input(text)

    if not records:
        ss["error"] = "Nenhum link/ID reconhecido."
        return redirect("/")

    if len(records) > 8:
        ss["error"] = "Use no máximo 8 anúncios por análise."
        return redirect("/")

    try:
        ss["results"] = [collect_record(r) for r in records]
    except Exception as e:
        ss["error"] = f"{type(e).__name__}: {e}"

    return redirect("/")

@app.route("/export/json")
def export_json():
    data = server_session().get("results") or []
    return Response(
        json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"),
        mimetype="application/json",
        headers={"Content-Disposition":"attachment; filename=ml_resultado_v5.json"}
    )

@app.route("/export/csv")
def export_csv():
    data = server_session().get("results") or []
    out = StringIO()

    fields = [
        "item_id","product_ids","seller_id","seller_nickname","seller_level",
        "seller_transactions","questions_total","title","title_source",
        "price","price_source","description_available","attributes_count",
        "rating_average","reviews_total","sold_quantity"
    ]

    w = csv.DictWriter(out, fieldnames=fields)
    w.writeheader()

    for r in data:
        seller = r.get("seller") or {}
        rep = seller.get("seller_reputation") or {}
        tx = rep.get("transactions") or {}
        f = r.get("fields") or {}
        q = r.get("question_summary") or {}

        def fv(k):
            return (f.get(k) or {}).get("value")
        def fs(k):
            return (f.get(k) or {}).get("source")

        attrs = fv("attributes") or []

        w.writerow({
            "item_id": r.get("item_id"),
            "product_ids": ",".join(r.get("product_ids") or []),
            "seller_id": r.get("seller_id"),
            "seller_nickname": seller.get("nickname"),
            "seller_level": rep.get("level_id"),
            "seller_transactions": tx.get("total"),
            "questions_total": q.get("total"),
            "title": fv("title"),
            "title_source": fs("title"),
            "price": fv("price"),
            "price_source": fs("price"),
            "description_available": bool(fv("description")),
            "attributes_count": len(attrs),
            "rating_average": fv("rating_average"),
            "reviews_total": fv("reviews_total"),
            "sold_quantity": fv("sold_quantity")
        })

    return Response(
        out.getvalue().encode("utf-8-sig"),
        mimetype="text/csv",
        headers={"Content-Disposition":"attachment; filename=ml_resumo_v5.csv"}
    )

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT","8000")),
        debug=False
    )
