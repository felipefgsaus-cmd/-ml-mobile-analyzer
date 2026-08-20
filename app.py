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
BRAVE_SEARCH_API_KEY = os.getenv("BRAVE_SEARCH_API_KEY", "").strip()

API = "https://api.mercadolibre.com"
AUTH_URL = "https://auth.mercadolivre.com.br/authorization"
BRAVE_API = "https://api.search.brave.com/res/v1/web/search"

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
<title>ML Mobile Analyzer V4 Safe</title>
<style>
body{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;background:#f6f6f6;color:#202020;margin:0}
.wrap{max-width:1180px;margin:auto;padding:18px}
.card{background:#fff;border:1px solid #e3e3e3;border-radius:16px;padding:18px;margin:14px 0}
h1{font-size:26px;margin:4px 0 8px} h2{font-size:19px}
textarea{width:100%;min-height:190px;padding:12px;border:1px solid #ccc;border-radius:12px;font-size:16px;box-sizing:border-box}
button,.btn{background:#111;color:#fff;border:0;border-radius:12px;padding:13px 16px;font-size:16px;text-decoration:none;display:inline-block;cursor:pointer}
.btn.secondary{background:#555}.muted{color:#666;font-size:14px}.ok{color:#087a39}.warn{color:#9a5c00}.bad{color:#a40000}
table{border-collapse:collapse;width:100%;font-size:12px;display:block;overflow-x:auto}
th,td{border-bottom:1px solid #ddd;padding:8px;text-align:left;vertical-align:top;min-width:105px}
.status{font-weight:700}.s200{color:#087a39}.s401,.s403{color:#a40000}.s404{color:#9a5c00}
.small{font-size:12px}.tag{display:inline-block;border:1px solid #ddd;border-radius:999px;padding:3px 7px;margin:2px;font-size:11px}
</style>
</head>
<body><div class="wrap">
<h1>ML Mobile Analyzer V4 Safe</h1>
<p class="muted">API oficial do Mercado Livre + busca web oficial via Brave Search API. Sem scraping direto do Mercado Livre.</p>

<div class="card">
<h2>1. Conexões</h2>
{% if not configured %}
<p class="bad">OAuth do Mercado Livre não configurado.</p>
{% elif token %}
<p class="ok">✓ Conta Mercado Livre autorizada nesta sessão.</p>
<a class="btn secondary" href="/logout">Desconectar ML</a>
{% else %}
<a class="btn" href="/login">Conectar Mercado Livre</a>
{% endif %}
{% if brave %}
<p class="ok">✓ Brave Search API configurada.</p>
{% else %}
<p class="warn">⚠ Brave Search API ainda não configurada. A análise funcionará só com a API oficial do ML.</p>
{% endif %}
</div>

<div class="card">
<h2>2. Cole os links completos</h2>
<p class="muted">A V4 usa os links/IDs como termos de busca no índice público da web e mantém os resultados externos separados dos dados confirmados pela API.</p>
<form method="post" action="/analyze">
<textarea name="links" placeholder="1 link por linha">{{ links or "" }}</textarea>
<p><button type="submit">Analisar concorrentes</button></p>
</form>
</div>

{% if error %}
<div class="card"><strong>Erro:</strong> {{ error }}</div>
{% endif %}

{% if rows %}
<div class="card">
<h2>3. Resultado</h2>
<p><a class="btn" href="/export/json">Baixar JSON completo</a>
<a class="btn secondary" href="/export/csv">Baixar CSV resumo</a></p>
<table>
<thead><tr>
<th>Item</th><th>Seller</th><th>Reputação</th><th>Perguntas</th>
<th>Busca web</th><th>Título provável</th><th>Preço provável</th><th>Fontes externas</th>
</tr></thead>
<tbody>
{% for r in rows %}
<tr>
<td>{{ r.item_id or "—" }}</td>
<td>{{ r.seller.nickname if r.seller else "—" }}</td>
<td>
{% if r.seller and r.seller.seller_reputation %}
{{ r.seller.seller_reputation.level_id or "—" }}
{% else %}—{% endif %}
</td>
<td>{{ r.question_summary.total if r.question_summary else 0 }}</td>
<td>
{% if r.web_search %}
<span class="status s{{ r.web_search.status }}">{{ r.web_search.status }}</span>
{% else %}—{% endif %}
</td>
<td>{{ r.external_summary.title_candidate or "—" }}</td>
<td>{{ r.external_summary.price_candidate or "—" }}</td>
<td>{{ r.external_summary.result_count or 0 }}</td>
</tr>
{% endfor %}
</tbody>
</table>
<p class="small muted">“Título provável” e “Preço provável” vêm de snippets indexados e ficam marcados como não confirmados no JSON. Dados do ML API permanecem separados.</p>
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

def ml_headers():
    tok = access_token()
    return {"Authorization": f"Bearer {tok}"} if tok else {}

def ml_get(path, params=None):
    try:
        r = requests.get(API + path, params=params, headers=ml_headers(), timeout=20)
        try:
            data = r.json()
        except Exception:
            data = {"raw_text": r.text[:4000]}
        return r.status_code, data
    except requests.RequestException as e:
        return 0, {"exception": type(e).__name__, "message": str(e)}

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
        out.append({"raw": raw, "item_id": item_id, "product_ids": product_ids})
    return out

def fix_mojibake(text):
    if not isinstance(text, str):
        return text
    # Corrige o padrão clássico UTF-8 interpretado como latin-1, quando aplicável.
    if "Ã" in text or "â€" in text or "Â" in text:
        try:
            return text.encode("latin1").decode("utf-8")
        except Exception:
            return text
    return text

def get_questions(item_id):
    if not item_id:
        return {"status": 0, "total": 0, "questions": []}
    status, data = ml_get("/questions/search", {"item": item_id, "api_version": 4, "limit": 50})
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
        "raw_error": data if status != 200 else None,
    }

def get_seller(seller_id):
    if not seller_id:
        return None
    status, data = ml_get(f"/users/{seller_id}")
    if status != 200 or not isinstance(data, dict):
        return None
    return {
        "id": data.get("id"),
        "nickname": fix_mojibake(data.get("nickname")),
        "seller_reputation": data.get("seller_reputation"),
        "status": data.get("status"),
        "permalink": data.get("permalink"),
        "address": data.get("address"),
    }

def brave_search(query, count=8):
    if not BRAVE_SEARCH_API_KEY:
        return {"status": 0, "query": query, "results": [], "error": "BRAVE_SEARCH_API_KEY ausente"}
    try:
        r = requests.get(
            BRAVE_API,
            headers={
                "Accept": "application/json",
                "X-Subscription-Token": BRAVE_SEARCH_API_KEY,
            },
            params={
                "q": query,
                "count": max(1, min(count, 10)),
                "country": "br",
                "search_lang": "pt-br",
                "safesearch": "moderate",
            },
            timeout=20,
        )
        try:
            data = r.json()
        except Exception:
            data = {"raw_text": r.text[:4000]}
    except requests.RequestException as e:
        return {"status": 0, "query": query, "results": [], "error": str(e)}

    results = []
    if r.status_code == 200 and isinstance(data, dict):
        for x in ((data.get("web") or {}).get("results") or []):
            results.append({
                "title": fix_mojibake(x.get("title")),
                "url": x.get("url"),
                "description": fix_mojibake(x.get("description")),
                "profile": x.get("profile"),
            })

    return {
        "status": r.status_code,
        "query": query,
        "results": results,
        "error": data if r.status_code != 200 else None,
    }

PRICE_RE = re.compile(r'R\$\s?([\d\.]+(?:,\d{2})?)', re.I)

def infer_from_results(search_results, item_id, product_ids, seller_name=None):
    title_candidate = None
    price_candidate = None
    evidence = []

    ids = [x for x in ([item_id] + (product_ids or [])) if x]

    for r in search_results:
        title = r.get("title") or ""
        desc = r.get("description") or ""
        url = r.get("url") or ""
        hay = " ".join([title, desc, url])

        matched = [x for x in ids if x and x.lower() in hay.lower()]
        if matched:
            evidence.append({
                "matched_ids": matched,
                "title": title,
                "description": desc,
                "url": url,
            })

            if not title_candidate and title:
                # Evita títulos genéricos de páginas de busca/perfil quando possível.
                if "mercado livre" not in title.lower() or len(title) > 20:
                    title_candidate = title

            if not price_candidate:
                m = PRICE_RE.search(hay)
                if m:
                    price_candidate = "R$ " + m.group(1)

    # Se o ID exato não apareceu no snippet, ainda preservamos resultados relevantes,
    # mas não inferimos preço/título automaticamente.
    return {
        "title_candidate": title_candidate,
        "price_candidate": price_candidate,
        "result_count": len(search_results),
        "matched_evidence": evidence,
        "confidence_note": "Candidatos extraídos de snippets indexados; não equivalem a dados confirmados pela API do Mercado Livre.",
    }

def collect_record(rec):
    item_id = rec.get("item_id")
    product_ids = rec.get("product_ids") or []

    questions = get_questions(item_id)
    seller_id = None
    for q in questions.get("questions") or []:
        if q.get("seller_id"):
            seller_id = q["seller_id"]
            break
    seller = get_seller(seller_id)

    # Busca externa via API oficial do Brave. Sem crawl direto no Mercado Livre.
    searches = []
    queries = []

    if item_id:
        queries.append(f'"{item_id}"')
        queries.append(f'site:mercadolivre.com.br "{item_id}"')

    for pid in product_ids[:2]:
        queries.append(f'"{pid}"')

    if seller and seller.get("nickname") and item_id:
        queries.append(f'"{item_id}" "{seller["nickname"]}"')

    # Remove duplicadas, limita chamadas por anúncio.
    dedup = []
    for q in queries:
        if q not in dedup:
            dedup.append(q)
    queries = dedup[:4]

    all_results = []
    status = 0
    for idx, q in enumerate(queries):
        s = brave_search(q, count=8)
        searches.append(s)
        if s.get("status") == 200:
            status = 200
            all_results.extend(s.get("results") or [])
        elif status == 0:
            status = s.get("status") or 0
        # Pequena pausa para manter a coleta conservadora.
        if idx < len(queries) - 1:
            time.sleep(0.35)

    # Dedup de URLs.
    unique = []
    seen = set()
    for r in all_results:
        url = r.get("url")
        if url and url not in seen:
            seen.add(url)
            unique.append(r)

    external_summary = infer_from_results(unique, item_id, product_ids, seller.get("nickname") if seller else None)

    return {
        "raw": rec.get("raw"),
        "item_id": item_id,
        "product_ids": product_ids,
        "seller_id": seller_id,
        "seller": seller,
        "question_summary": questions,
        "web_search": {
            "provider": "Brave Search API",
            "status": status,
            "queries": searches,
            "results": unique,
        },
        "external_summary": external_summary,
        "_collected_at_unix": int(time.time()),
    }

@app.route("/")
def home():
    ss = server_session()
    return render_template_string(
        HTML,
        configured=configured(),
        token=bool(ss.get("access_token")),
        brave=bool(BRAVE_SEARCH_API_KEY),
        rows=ss.get("results"),
        links=ss.get("last_links", ""),
        error=ss.pop("error", None),
    )

@app.route("/health")
def health():
    return {"ok": True, "version": 4, "mode": "safe"}

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
            headers={"accept":"application/json","content-type":"application/x-www-form-urlencoded"},
            timeout=20,
        )
        try:
            data = r.json()
        except Exception:
            data = {"raw_text": r.text[:4000]}
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
        headers={"Content-Disposition":"attachment; filename=ml_resultado_v4_safe.json"},
    )

@app.route("/export/csv")
def export_csv():
    data = server_session().get("results") or []
    out = StringIO()
    fields = [
        "item_id","product_ids","seller_id","seller_nickname","seller_level",
        "seller_transactions","questions_total","web_status","web_results",
        "title_candidate","price_candidate"
    ]
    w = csv.DictWriter(out, fieldnames=fields)
    w.writeheader()

    for r in data:
        seller = r.get("seller") or {}
        rep = seller.get("seller_reputation") or {}
        tx = rep.get("transactions") or {}
        ext = r.get("external_summary") or {}
        web = r.get("web_search") or {}
        qs = r.get("question_summary") or {}

        w.writerow({
            "item_id": r.get("item_id"),
            "product_ids": ",".join(r.get("product_ids") or []),
            "seller_id": r.get("seller_id"),
            "seller_nickname": seller.get("nickname"),
            "seller_level": rep.get("level_id"),
            "seller_transactions": tx.get("total"),
            "questions_total": qs.get("total"),
            "web_status": web.get("status"),
            "web_results": len(web.get("results") or []),
            "title_candidate": ext.get("title_candidate"),
            "price_candidate": ext.get("price_candidate"),
        })

    return Response(
        out.getvalue().encode("utf-8-sig"),
        mimetype="text/csv",
        headers={"Content-Disposition":"attachment; filename=ml_resumo_v4_safe.csv"},
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8000")), debug=False)
