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
<title>ML Mobile Analyzer V4 Free</title>
<style>
body{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;background:#f6f6f6;color:#202020;margin:0}
.wrap{max-width:980px;margin:auto;padding:18px}
.card{background:#fff;border:1px solid #e3e3e3;border-radius:16px;padding:18px;margin:14px 0}
h1{font-size:26px;margin:4px 0 8px}
h2{font-size:19px;margin-top:0}
textarea{width:100%;min-height:180px;padding:12px;border:1px solid #ccc;border-radius:12px;font-size:16px;box-sizing:border-box}
button,.btn{background:#111;color:#fff;border:0;border-radius:12px;padding:13px 16px;font-size:16px;text-decoration:none;display:inline-block;cursor:pointer}
.btn.secondary{background:#555}
.muted{color:#666;font-size:14px}
.ok{color:#087a39}
.warn{color:#9a5c00}
.bad{color:#a40000}
.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}
.metric{background:#fafafa;border:1px solid #e5e5e5;border-radius:12px;padding:14px}
.metric b{display:block;font-size:13px;color:#666;margin-bottom:6px}
.metric span{font-size:19px;font-weight:700}
.qa{border-top:1px solid #e7e7e7;padding:12px 0}
.qa:first-child{border-top:0}
.q{font-weight:700;margin-bottom:7px}
.a{color:#444}
.meta{font-size:12px;color:#777;margin-top:6px}
@media(max-width:650px){.grid{grid-template-columns:1fr}}
</style>
</head>
<body><div class="wrap">
<h1>ML Mobile Analyzer V4 Free</h1>
<p class="muted">Versão enxuta: mostra apenas dados que a API oficial do Mercado Livre está liberando para o seu app.</p>

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
<p class="muted">Máximo de 10 anúncios por análise.</p>
</div>

{% if error %}
<div class="card"><strong>Erro:</strong> {{ error }}</div>
{% endif %}

{% if rows %}
<div class="card">
<h2>3. Resultados</h2>
<p>
<a class="btn" href="/export/json">Baixar JSON</a>
<a class="btn secondary" href="/export/csv">Baixar CSV</a>
</p>
</div>

{% for r in rows %}
<div class="card">
<h2>{{ r.item_id or "Item não identificado" }}</h2>

<div class="grid">
<div class="metric">
<b>Vendedor</b>
<span>{{ r.seller.nickname if r.seller else "Indisponível" }}</span>
</div>

<div class="metric">
<b>Reputação</b>
<span>
{% if r.seller and r.seller.seller_reputation %}
{{ r.seller.seller_reputation.level_id or "Indisponível" }}
{% else %}
Indisponível
{% endif %}
</span>
</div>

<div class="metric">
<b>Transações históricas do vendedor</b>
<span>
{% if r.seller and r.seller.seller_reputation and r.seller.seller_reputation.transactions %}
{{ r.seller.seller_reputation.transactions.total or 0 }}
{% else %}
0
{% endif %}
</span>
</div>

<div class="metric">
<b>Perguntas encontradas</b>
<span>{{ r.question_summary.total if r.question_summary else 0 }}</span>
</div>
</div>

{% if r.seller and r.seller.address %}
<p class="muted">
Local do vendedor:
{{ r.seller.address.city or "" }}
{% if r.seller.address.state %} / {{ r.seller.address.state }}{% endif %}
</p>
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
{% else %}
<p class="muted">Nenhuma pergunta disponível para este anúncio.</p>
{% endif %}
</div>
{% endfor %}
{% endif %}

<div class="card">
<p class="muted">
Esta versão não exibe preço, título, reviews, descrição, estoque, catálogo ou vendas do anúncio
quando esses dados não estão liberados pela API. Isso evita telas vazias e reduz chamadas inúteis.
</p>
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

def ml_headers():
    tok = access_token()
    return {"Authorization": f"Bearer {tok}"} if tok else {}

def ml_get(path, params=None):
    try:
        r = requests.get(API + path, params=params, headers=ml_headers(), timeout=20)
        try:
            data = r.json()
        except Exception:
            data = {"raw_text": r.text[:3000]}
        return r.status_code, data
    except requests.RequestException as e:
        return 0, {"exception": type(e).__name__, "message": str(e)}

def parse_input(text):
    out = []
    for raw in [x.strip() for x in text.splitlines() if x.strip()]:
        all_mlb = re.findall(r'\bMLB\d{6,}\b', raw.upper())
        q_item = re.findall(r'item_id(?:%3A|:|=)+(MLB\d{6,})', raw, flags=re.I)
        q_item = [x.upper() for x in q_item]
        item_id = q_item[0] if q_item else (all_mlb[-1] if all_mlb else None)
        out.append({"raw": raw, "item_id": item_id})
    return out

def fix_mojibake(text):
    if not isinstance(text, str):
        return text
    if "Ã" in text or "â€" in text or "Â" in text:
        try:
            return text.encode("latin1").decode("utf-8")
        except Exception:
            return text
    return text

def get_questions(item_id):
    if not item_id:
        return {"status": 0, "total": 0, "questions": []}

    status, data = ml_get("/questions/search", {
        "item": item_id,
        "api_version": 4,
        "limit": 50
    })

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
        "questions": questions,
    }

def get_seller(seller_id):
    if not seller_id:
        return None

    status, data = ml_get(f"/users/{seller_id}")
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
                "total": tx.get("total"),
            }
        },
        "status": data.get("status"),
        "permalink": data.get("permalink"),
        "address": data.get("address"),
    }

def collect_record(rec):
    item_id = rec.get("item_id")
    questions = get_questions(item_id)

    seller_id = None
    for q in questions.get("questions") or []:
        if q.get("seller_id"):
            seller_id = q["seller_id"]
            break

    seller = get_seller(seller_id)

    return {
        "raw": rec.get("raw"),
        "item_id": item_id,
        "seller_id": seller_id,
        "seller": seller,
        "question_summary": questions,
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
        links=ss.get("last_links", ""),
        error=ss.pop("error", None),
    )

@app.route("/health")
def health():
    return {"ok": True, "version": 4, "mode": "free-clean"}

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
        "state": state,
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
        "redirect_uri": REDIRECT_URI,
    }

    try:
        r = requests.post(
            API + "/oauth/token",
            data=payload,
            headers={
                "accept": "application/json",
                "content-type": "application/x-www-form-urlencoded"
            },
            timeout=20,
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

    if len(records) > 10:
        ss["error"] = "Use no máximo 10 anúncios por análise."
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
        headers={
            "Content-Disposition": "attachment; filename=ml_resultado_v4_free.json"
        },
    )

@app.route("/export/csv")
def export_csv():
    data = server_session().get("results") or []

    out = StringIO()

    fields = [
        "item_id",
        "seller_id",
        "seller_nickname",
        "seller_level",
        "power_seller_status",
        "seller_transactions_historic",
        "questions_total",
    ]

    w = csv.DictWriter(out, fieldnames=fields)
    w.writeheader()

    for r in data:
        seller = r.get("seller") or {}
        rep = seller.get("seller_reputation") or {}
        tx = rep.get("transactions") or {}
        qs = r.get("question_summary") or {}

        w.writerow({
            "item_id": r.get("item_id"),
            "seller_id": r.get("seller_id"),
            "seller_nickname": seller.get("nickname"),
            "seller_level": rep.get("level_id"),
            "power_seller_status": rep.get("power_seller_status"),
            "seller_transactions_historic": tx.get("total"),
            "questions_total": qs.get("total"),
        })

    return Response(
        out.getvalue().encode("utf-8-sig"),
        mimetype="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=ml_resumo_v4_free.csv"
        },
    )

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
        debug=False
    )
