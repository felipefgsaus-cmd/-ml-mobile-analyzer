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

# Mantém token e resultados fora do cookie do navegador.
SERVER_SESSIONS = {}

HTML = """
<!doctype html>
<html lang="pt-br">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ML Mobile Analyzer V3</title>
<style>
body{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;background:#f6f6f6;color:#202020;margin:0}
.wrap{max-width:1180px;margin:auto;padding:18px}
.card{background:#fff;border:1px solid #e3e3e3;border-radius:16px;padding:18px;margin:14px 0}
h1{font-size:26px;margin:4px 0 8px} h2{font-size:19px}
textarea{width:100%;min-height:190px;padding:12px;border:1px solid #ccc;border-radius:12px;font-size:16px;box-sizing:border-box}
button,.btn{background:#111;color:#fff;border:0;border-radius:12px;padding:13px 16px;font-size:16px;text-decoration:none;display:inline-block;cursor:pointer}
.btn.secondary{background:#555}.muted{color:#666;font-size:14px}.ok{color:#087a39}.bad{color:#a40000}
table{border-collapse:collapse;width:100%;font-size:12px;display:block;overflow-x:auto}
th,td{border-bottom:1px solid #ddd;padding:8px;text-align:left;vertical-align:top;min-width:95px}
.status{font-weight:700}.s200{color:#087a39}.s401,.s403{color:#a40000}.s404{color:#9a5c00}
.small{font-size:12px}
</style>
</head>
<body><div class="wrap">
<h1>ML Mobile Analyzer V3</h1>
<p class="muted">Coleta por múltiplas rotas oficiais, sem insistir em endpoints bloqueados.</p>

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
<h2>2. Cole links completos</h2>
<p class="muted">Use os links completos. A V3 extrai item_id e product/catalog ID quando existirem.</p>
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
<h2>3. Resumo recuperado</h2>
<p><a class="btn" href="/export/json">Baixar JSON completo</a>
<a class="btn secondary" href="/export/csv">Baixar CSV resumo</a></p>

<table>
<thead><tr>
<th>Item</th><th>Produto</th><th>Perguntas</th><th>Seller ID</th><th>Vendedor</th>
<th>Reputação</th><th>Catálogo</th><th>Ofertas catálogo</th><th>Busca vendedor</th>
<th>Título</th><th>Preço</th>
</tr></thead>
<tbody>
{% for r in rows %}
<tr>
<td>{{ r.item_id or "—" }}</td>
<td>{{ (r.product_ids or [])|join(", ") or "—" }}</td>
<td>
{% set qp = r.probes.get("questions_auth") %}
{% if qp %}<span class="status s{{ qp.status }}">{{ qp.status }}</span>
{% if r.question_summary %}<br>{{ r.question_summary.total }} encontradas{% endif %}
{% else %}—{% endif %}
</td>
<td>{{ r.seller_id or "—" }}</td>
<td>{{ r.seller.nickname if r.seller else "—" }}</td>
<td>
{% if r.seller and r.seller.seller_reputation %}
{{ r.seller.seller_reputation.level_id or "—" }}<br>
{{ r.seller.seller_reputation.power_seller_status or "" }}
{% else %}—{% endif %}
</td>
<td>
{% set cp = r.probes.get("catalog_best") %}
{% if cp %}<span class="status s{{ cp.status }}">{{ cp.status }}</span>{% else %}—{% endif %}
</td>
<td>
{% set op = r.probes.get("catalog_offers_best") %}
{% if op %}<span class="status s{{ op.status }}">{{ op.status }}</span>{% else %}—{% endif %}
</td>
<td>
{% set sp = r.probes.get("seller_items_auth") %}
{% if sp %}<span class="status s{{ sp.status }}">{{ sp.status }}</span>{% else %}—{% endif %}
</td>
<td>{{ r.best.title if r.best else "—" }}</td>
<td>{{ r.best.currency_id if r.best else "" }} {{ r.best.price if r.best and r.best.price is not none else "—" }}</td>
</tr>
{% endfor %}
</tbody>
</table>

<p class="small muted">A V3 usa apenas GET nas rotas de análise. 403 é registrado e a coleta continua por outras rotas.</p>
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

def headers(use_auth=True):
    if use_auth and access_token():
        return {"Authorization": f"Bearer {access_token()}"}
    return {}

def request_json(path, params=None, use_auth=True):
    try:
        r = requests.get(API + path, params=params, headers=headers(use_auth), timeout=25)
        try:
            data = r.json()
        except Exception:
            data = {"raw_text": r.text[:5000]}
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
        "path": path,
        "params": params or {},
        "auth": use_auth,
        "data": data,
    }

def parse_input(text):
    records = []
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

        for x in all_mlb:
            if x != item_id and x in path_products and x not in product_ids:
                product_ids.append(x)

        records.append({"raw": raw, "item_id": item_id, "product_ids": product_ids})
    return records

def summarize_item(data):
    if not isinstance(data, dict):
        return None
    if not data.get("id"):
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
        "source": "item"
    }

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
        "source": "catalog"
    }

def extract_questions(probe_obj):
    if not probe_obj or probe_obj.get("status") != 200:
        return []
    d = probe_obj.get("data")
    if not isinstance(d, dict):
        return []
    return d.get("questions") or []

def seller_from_questions(questions):
    for q in questions:
        sid = q.get("seller_id")
        if sid:
            return sid
    return None

def seller_summary(data):
    if not isinstance(data, dict) or not data.get("id"):
        return None
    return {
        "id": data.get("id"),
        "nickname": data.get("nickname"),
        "registration_date": data.get("registration_date"),
        "seller_reputation": data.get("seller_reputation"),
        "status": data.get("status"),
    }

def list_candidates_from_catalog_offers(data):
    # A resposta pode variar. Varremos estruturas comuns sem assumir uma única forma.
    candidates = []

    def walk(obj):
        if isinstance(obj, dict):
            iid = obj.get("id") or obj.get("item_id")
            title = obj.get("title")
            price = obj.get("price")
            seller_id = obj.get("seller_id")
            permalink = obj.get("permalink")
            if isinstance(iid, str) and iid.startswith("MLB"):
                candidates.append({
                    "id": iid,
                    "title": title,
                    "price": price,
                    "currency_id": obj.get("currency_id"),
                    "seller_id": seller_id,
                    "permalink": permalink,
                    "raw": obj,
                })
            for v in obj.values():
                walk(v)
        elif isinstance(obj, list):
            for x in obj:
                walk(x)

    walk(data)

    seen, out = set(), []
    for c in candidates:
        key = c.get("id")
        if key and key not in seen:
            seen.add(key)
            out.append(c)
    return out

def item_from_seller_search(data, target_item):
    if not isinstance(data, dict):
        return None
    results = data.get("results")
    if not isinstance(results, list):
        return None
    if target_item in results:
        return {"id": target_item, "source": "seller_items_search"}
    # Algumas respostas podem conter objetos.
    for r in results:
        if isinstance(r, dict) and r.get("id") == target_item:
            x = summarize_item(r)
            if x:
                x["source"] = "seller_items_search"
                return x
    return None

def collect_record(rec):
    item_id = rec.get("item_id")
    product_ids = list(rec.get("product_ids") or [])
    probes = {}
    best = None

    # 1) ITEM principal: uma tentativa autenticada e uma pública.
    if item_id:
        probes["item_auth"] = probe(f"/items/{item_id}", {"include_attributes":"all"}, True)
        best = summarize_item(probes["item_auth"]["data"])

        probes["item_public"] = probe(f"/items/{item_id}", {"include_attributes":"all"}, False)
        if not best:
            best = summarize_item(probes["item_public"]["data"])

        # 2) Questions: sabemos que este endpoint pode funcionar para terceiros.
        probes["questions_auth"] = probe(
            "/questions/search",
            {"item": item_id, "api_version": 4, "limit": 50},
            True
        )

    questions = extract_questions(probes.get("questions_auth"))
    seller_id = seller_from_questions(questions)

    question_summary = {
        "total": len(questions),
        "seller_id": seller_id,
        "questions": [
            {
                "id": q.get("id"),
                "date_created": q.get("date_created"),
                "text": q.get("text"),
                "status": q.get("status"),
                "answer": (q.get("answer") or {}).get("text"),
            }
            for q in questions
        ],
    }

    # 3) Seller e reputação usando seller_id descoberto pelas perguntas.
    seller = None
    if seller_id:
        probes["seller_auth"] = probe(f"/users/{seller_id}", use_auth=True)
        if probes["seller_auth"]["status"] == 200:
            seller = seller_summary(probes["seller_auth"]["data"])
        else:
            probes["seller_public"] = probe(f"/users/{seller_id}", use_auth=False)
            if probes["seller_public"]["status"] == 200:
                seller = seller_summary(probes["seller_public"]["data"])

        # 4) Lista de itens do vendedor. Pode ou não estar liberada.
        probes["seller_items_auth"] = probe(f"/users/{seller_id}/items/search", use_auth=True)
        if not best and probes["seller_items_auth"]["status"] == 200:
            best = item_from_seller_search(probes["seller_items_auth"]["data"], item_id)

        # 5) Busca no site filtrada por seller_id como rota alternativa.
        probes["site_search_seller_auth"] = probe(
            "/sites/MLB/search",
            {"seller_id": seller_id, "limit": 50},
            True
        )

        # Se a busca retorna resultados com o item alvo, use o objeto.
        if not best and probes["site_search_seller_auth"]["status"] == 200:
            d = probes["site_search_seller_auth"]["data"]
            if isinstance(d, dict):
                for obj in d.get("results") or []:
                    if isinstance(obj, dict) and obj.get("id") == item_id:
                        best = summarize_item(obj)
                        if best:
                            best["source"] = "site_search_seller"
                            break

    # 6) Catálogo/produto e ofertas relacionadas ao product_id dos links.
    catalog_summaries = []
    catalog_offer_candidates = []

    for pid in product_ids:
        ca = probe(f"/products/{pid}", use_auth=True)
        cp = None
        if ca["status"] == 200:
            cp = ca
        else:
            cpub = probe(f"/products/{pid}", use_auth=False)
            probes[f"catalog_{pid}_public"] = cpub
            cp = cpub if cpub["status"] == 200 else ca

        probes[f"catalog_{pid}_auth"] = ca

        summary = summarize_product(cp["data"]) if cp and cp["status"] == 200 else None
        catalog_summaries.append((pid, cp, summary))
        if not best and summary:
            best = summary

        # Ofertas/itens vinculados ao produto de catálogo.
        # Testamos duas formas de endpoint usadas por diferentes famílias de produto.
        offer_probes = [
            probe(f"/products/{pid}/items", use_auth=True),
            probe(f"/products/{pid}/items", {"site_id":"MLB"}, True),
        ]
        probes[f"catalog_{pid}_items"] = offer_probes[0]
        probes[f"catalog_{pid}_items_site"] = offer_probes[1]

        for op in offer_probes:
            if op["status"] == 200:
                cands = list_candidates_from_catalog_offers(op["data"])
                catalog_offer_candidates.extend(cands)
                if not best:
                    for c in cands:
                        if c.get("id") == item_id:
                            best = {
                                "id": c.get("id"),
                                "title": c.get("title"),
                                "price": c.get("price"),
                                "original_price": None,
                                "currency_id": c.get("currency_id"),
                                "seller_id": c.get("seller_id"),
                                "category_id": None,
                                "catalog_product_id": pid,
                                "sold_quantity": None,
                                "available_quantity": None,
                                "pictures": [],
                                "attributes": [],
                                "shipping": {},
                                "permalink": c.get("permalink"),
                                "source": "catalog_offers",
                            }
                            break

    # Resumos de status para UI.
    if catalog_summaries:
        chosen = None
        for _, cp, _ in catalog_summaries:
            if cp and cp["status"] == 200:
                chosen = cp
                break
        if chosen is None:
            chosen = catalog_summaries[0][1]
        probes["catalog_best"] = {
            "status": chosen["status"],
            "code": chosen.get("code"),
            "message": chosen.get("message"),
        }

    # Melhor status de ofertas.
    offer_statuses = []
    for k, v in probes.items():
        if k.startswith("catalog_") and (k.endswith("_items") or k.endswith("_items_site")):
            offer_statuses.append(v)
    if offer_statuses:
        chosen = next((x for x in offer_statuses if x["status"] == 200), offer_statuses[0])
        probes["catalog_offers_best"] = {
            "status": chosen["status"],
            "code": chosen.get("code"),
            "message": chosen.get("message"),
        }

    # 7) Se conseguimos descobrir um item via rotas alternativas, fazemos UMA consulta adicional
    # apenas se for o mesmo item alvo e ainda não houver dados completos.
    if best and best.get("id") == item_id and not best.get("title") and item_id:
        alt = probe(f"/items/{item_id}", use_auth=True)
        probes["item_retry_from_alternative"] = alt
        if alt["status"] == 200:
            best = summarize_item(alt["data"])

    return {
        "raw": rec.get("raw"),
        "item_id": item_id,
        "product_ids": product_ids,
        "seller_id": seller_id,
        "seller": seller,
        "question_summary": question_summary,
        "catalog_offer_candidates": catalog_offer_candidates,
        "best": best,
        "probes": probes,
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
    return {"ok": True, "version": 3}

@app.route("/notifications", methods=["GET", "POST"])
def notifications():
    # Endpoint cadastrado no Mercado Livre. A ferramenta não processa webhooks.
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
        ss["error"] = "Falha de segurança OAuth: state inválido."
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
            headers={"accept": "application/json", "content-type": "application/x-www-form-urlencoded"},
            timeout=25,
        )
        try:
            d = r.json()
        except Exception:
            d = {"raw_text": r.text[:5000]}
    except requests.RequestException as e:
        ss["error"] = f"Falha OAuth: {type(e).__name__}: {e}"
        return redirect("/")

    if r.status_code != 200 or not d.get("access_token"):
        ss["error"] = f"Falha ao obter token: HTTP {r.status_code} — {d.get('message', d)}"
        return redirect("/")

    ss["access_token"] = d["access_token"]
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
        ss["error"] = "Nenhum link ou ID reconhecido."
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
    payload = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    return Response(
        payload,
        mimetype="application/json",
        headers={"Content-Disposition": "attachment; filename=ml_resultado_v3.json"},
    )

@app.route("/export/csv")
def export_csv():
    data = server_session().get("results") or []
    out = StringIO()
    fields = [
        "item_id","product_ids","questions_total","seller_id","seller_nickname",
        "seller_level","power_seller_status","catalog_status","catalog_offers_status",
        "seller_items_status","title","price","currency_id","source"
    ]
    w = csv.DictWriter(out, fieldnames=fields)
    w.writeheader()

    for r in data:
        p = r.get("probes") or {}
        seller = r.get("seller") or {}
        rep = seller.get("seller_reputation") or {}
        best = r.get("best") or {}
        def st(k):
            return (p.get(k) or {}).get("status")

        w.writerow({
            "item_id": r.get("item_id"),
            "product_ids": ",".join(r.get("product_ids") or []),
            "questions_total": (r.get("question_summary") or {}).get("total"),
            "seller_id": r.get("seller_id"),
            "seller_nickname": seller.get("nickname"),
            "seller_level": rep.get("level_id"),
            "power_seller_status": rep.get("power_seller_status"),
            "catalog_status": st("catalog_best"),
            "catalog_offers_status": st("catalog_offers_best"),
            "seller_items_status": st("seller_items_auth"),
            "title": best.get("title"),
            "price": best.get("price"),
            "currency_id": best.get("currency_id"),
            "source": best.get("source"),
        })

    return Response(
        out.getvalue().encode("utf-8-sig"),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=ml_resumo_v3.csv"},
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8000")), debug=False)
