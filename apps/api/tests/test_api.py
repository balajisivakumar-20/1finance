from decimal import Decimal as D
from pathlib import Path

from sqlalchemy import select

from app.models import Account, Connection, Transaction

FIX = Path(__file__).parent / "fixtures"


# ---------------- auth & security ----------------
def test_requires_auth(anon):
    assert anon.get("/api/v1/dashboard/summary").status_code == 401


def test_bad_login_is_generic_and_audited(anon):
    r = anon.post("/api/v1/auth/login", json={"email": "demo@1finance.app", "password": "wrong"})
    assert r.status_code == 401 and r.json()["detail"] == "Incorrect email or password"


def test_session_cookie_is_httponly(anon):
    r = anon.post("/api/v1/auth/login", json={"email": "demo@1finance.app", "password": "demo-1finance"})
    cookie = [h for h in r.headers.get_list("set-cookie") if h.startswith("1f_session")][0]
    assert "HttpOnly" in cookie and "SameSite=lax" in cookie


def test_csrf_required_for_writes(client):
    tok = client.headers.pop("X-CSRF-Token")
    assert client.post("/api/v1/notifications/read-all").status_code == 403
    client.headers["X-CSRF-Token"] = tok
    assert client.post("/api/v1/notifications/read-all").status_code == 200


def test_security_headers_and_no_store(client):
    r = client.get("/api/v1/accounts")
    assert r.headers["cache-control"] == "no-store" and r.headers["x-frame-options"] == "DENY"


def test_money_is_serialized_as_string(client):
    nw = client.get("/api/v1/dashboard/summary").json()["net_worth"]["value"]
    assert isinstance(nw, str) and D(nw) > 0


def test_logout_revokes_session(client):
    assert client.post("/api/v1/auth/logout").status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 401


# ---------------- dashboard consistency ----------------
def test_net_worth_equals_assets_minus_liabilities(client):
    s = client.get("/api/v1/dashboard/summary").json()
    assert abs(D(s["assets"]["value"]) - D(s["liabilities"]["value"]) - D(s["net_worth"]["value"])) <= D("0.01")
    assert s["data_quality"]["includes_demo"] is True
    alloc_total = sum(D(a["value"]) for a in s["allocation"])
    assert abs(alloc_total - D(s["assets"]["value"])) <= D("0.05")


def test_history_last_point_matches_current(client):
    s = client.get("/api/v1/dashboard/summary").json()
    h = client.get("/api/v1/dashboard/history?range=3M").json()
    assert h["points"][-1]["net_worth"] == s["net_worth"]["value"]


def test_invalid_range_rejected(client):
    assert client.get("/api/v1/dashboard/history?range=7Y").status_code == 422


def test_currency_switch_changes_values_not_meaning(client):
    eur = D(client.get("/api/v1/dashboard/summary?currency=EUR").json()["net_worth"]["value"])
    inr = D(client.get("/api/v1/dashboard/summary?currency=INR").json()["net_worth"]["value"])
    assert inr > eur * 80  # EURINR demo rates are ~96


def test_transfers_not_counted_as_income_or_expense(client, db):
    r = client.get("/api/v1/analytics/cashflow?months=3").json()
    for m in r["months"]:
        assert "transfers" not in m["categories"]


# ---------------- transactions ----------------
def test_transaction_filters_and_pagination(client):
    r = client.get("/api/v1/transactions?page_size=10&category=food&sort=amount&order=asc").json()
    assert r["total"] > 0 and len(r["items"]) <= 10
    assert all(it["category"]["slug"] in ("groceries", "restaurants", "coffee", "food_delivery") for it in r["items"])
    assert all(it["external_reference"].startswith("••••") for it in r["items"])


def test_edit_category_keeps_raw_and_learns(client, db):
    item = client.get("/api/v1/transactions?q=tesco&page_size=1").json()["items"][0]
    cats = client.get("/api/v1/categories").json()
    household = next(c["id"] for p in cats for c in p["children"] if c["slug"] == "household")
    r = client.patch(f"/api/v1/transactions/{item['id']}", json={"category_id": household, "apply_to_future": True})
    assert r.status_code == 200
    t = db.get(Transaction, item["id"])
    assert t.user_category_id == household and t.category_id != household  # system category preserved
    assert t.raw_description == item["description"]
    rules = client.get("/api/v1/categorization-rules").json()
    assert any(x["kind"] == "learned" for x in rules)


# ---------------- imports ----------------
def test_statement_import_preview_commit_and_reimport_dedup(client, db):
    acct = db.scalar(select(Account).where(Account.account_type == "checking"))
    files = {"file": ("revolut.csv", (FIX / "revolut_statement.csv").read_bytes(), "text/csv")}
    p = client.post("/api/v1/imports/preview", files=files, data={"account_id": str(acct.id)}).json()
    assert p["format"] == "revolut" and p["rows"] == 5 and p["skipped"] == 1
    assert p["errors"] and p["errors"][0]["row"] == 8
    c = client.post(f"/api/v1/imports/{p['batch_id']}/commit").json()
    assert c["stats"]["new"] == 5
    # second import of the same file → all duplicates
    p2 = client.post("/api/v1/imports/preview", files=files, data={"account_id": str(acct.id)}).json()
    assert p2["dedup"]["duplicate"] == 5 and p2["dedup"]["new"] == 0
    assert client.post(f"/api/v1/imports/{p['batch_id']}/commit").status_code == 409


def test_import_rejects_non_csv(client, db):
    acct = db.scalar(select(Account).where(Account.account_type == "checking"))
    r = client.post("/api/v1/imports/preview", files={"file": ("x.pdf", b"%PDF", "application/pdf")}, data={"account_id": str(acct.id)})
    assert r.status_code == 415


# ---------------- connections ----------------
def test_cannot_connect_real_provider_without_valid_credentials(client):
    r = client.post("/api/v1/connections", json={"connector": "ibkr_flex", "credentials": {}})
    assert r.status_code == 400
    r = client.post("/api/v1/connections", json={"connector": "aggregator_revolut", "credentials": {}})
    assert r.status_code == 400 and "not configured" in r.json()["detail"]


def test_manual_sync_is_idempotent(client, db):
    conn = db.scalar(select(Connection).where(Connection.connector == "mock_revolut"))
    before = db.query(Transaction).count()
    r = client.post(f"/api/v1/connections/{conn.id}/sync").json()
    assert r["status"] == "succeeded"
    db.expire_all()
    assert db.query(Transaction).count() == before


def test_disconnect_retains_history_by_default(client, db):
    r = client.post("/api/v1/accounts/manual", json={"name": "Wallet", "account_type": "cash", "currency": "EUR", "balance": "120.50"})
    acct = db.get(Account, r.json()["id"])
    client.post(f"/api/v1/connections/{acct.connection_id}/disconnect", json={"delete_data": False})
    db.expire_all()
    assert db.get(Account, acct.id).status == "disconnected"


def test_investments_endpoints(client):
    s = client.get("/api/v1/investments/summary").json()
    assert D(s["total_value"]) == D(s["holdings_value"]) + D(s["cash"])
    h = client.get("/api/v1/investments/holdings?scope=institution:groww").json()
    assert all(i["currency"] == "INR" for i in h["items"])
    hist = client.get("/api/v1/investments/history?range=6M").json()
    assert hist["twr"] is not None and "decomposition" in hist


def test_reports_export(client):
    for fmt, magic in (("pdf", b"%PDF"), ("xlsx", b"PK"), ("csv", b"\xef\xbb\xbf")):
        r = client.get(f"/api/v1/reports/monthly?format={fmt}")
        assert r.status_code == 200 and r.content.startswith(magic)
        assert b"token" not in r.content.lower() or fmt == "pdf"


def test_budgets_and_goals(client):
    b = client.get("/api/v1/budgets").json()
    assert b["items"] and all(i["status"] in ("ok", "warning", "over") for i in b["items"])
    g = client.get("/api/v1/goals").json()["items"]
    assert all(D(x["progress_pct"]) <= 100 for x in g)


def test_manual_goal_tracking(client):
    r = client.post("/api/v1/goals", json={"name": "Buy Car", "goal_type": "car", "target_amount": "20000", "currency": "EUR",
                                           "target_date": "2028-06-01"})
    assert r.status_code == 201
    gid = r.json()["id"]
    get = lambda: next(x for x in client.get("/api/v1/goals").json()["items"] if x["id"] == gid)  # noqa: E731
    assert D(get()["current"]) == 0 and get()["contributions"] == []

    c1 = client.post(f"/api/v1/goals/{gid}/contributions", json={"amount": "1500", "on": "2026-09-01", "note": "Bonus"}).json()["id"]
    client.post(f"/api/v1/goals/{gid}/contributions", json={"amount": "500", "on": "2026-10-01"})
    g = get()
    assert D(g["current"]) == 2000 and len(g["contributions"]) == 2
    assert g["contributions"][-1]["note"] == "Bonus"
    assert client.post(f"/api/v1/goals/{gid}/contributions", json={"amount": "0"}).status_code == 422

    assert client.patch(f"/api/v1/goals/{gid}/contributions/{c1}", json={"amount": "1000", "note": None}).status_code == 200
    g = get()
    assert D(g["current"]) == 1500 and g["contributions"][-1]["note"] is None

    assert client.patch(f"/api/v1/goals/{gid}", json={"name": "Buy EV", "target_amount": "30000", "target_date": None,
                                                      "currency": "INR"}).status_code == 200
    g = get()
    assert g["name"] == "Buy EV" and D(g["target"]) == 30000 and g["target_date"] is None and g["type"] == "car"
    assert g["currency"] == "INR" and D(g["current"]) == 1500

    assert client.delete(f"/api/v1/goals/{gid}/contributions/{c1}").status_code == 200
    assert D(get()["current"]) == 500
    other = client.get("/api/v1/goals").json()["items"][0]["id"]
    assert client.delete(f"/api/v1/goals/{other}/contributions/{c1}").status_code == 404
    client.delete(f"/api/v1/goals/{gid}")
