from decimal import Decimal as D
from pathlib import Path

import httpx
import pytest

from app.connectors.base import Capability, ConnectorError, ReauthRequired
from app.connectors.groww import GrowwConnector
from app.connectors.ibkr_flex import FlexStatementParser, IBKRFlexConnector
from app.connectors.mock import MockGroww, MockIBKR, MockRevolut
from app.connectors.registry import AggregatorConnector
from app.fx.providers import ECBProvider
from app.importers.statements import parse_csv

FIX = Path(__file__).parent / "fixtures"


def test_flex_parser():
    p = FlexStatementParser((FIX / "ibkr_flex_sample.xml").read_text())
    assert p.accounts()[0].currency == "EUR"
    cash = {b.currency: b.balance for b in p.cash_balances()}
    assert cash == {"EUR": D("1200.00"), "USD": D("330.50")}  # BASE_SUMMARY excluded (would double count)
    h = {x.security.ticker: x for x in p.holdings()}
    assert set(h) == {"AAPL", "VWCE"}  # LOT rows ignored
    assert h["VWCE"].average_price == D("5800.00") / D("50.5")
    acts = p.activity()
    kinds = sorted(a.activity_type for a in acts)
    assert kinds == ["buy", "deposit", "dividend", "sell", "withdrawal"]
    sell = next(a for a in acts if a.activity_type == "sell")
    assert sell.realized_pl == D("120.50") and sell.fees == D("1.00")


def _flex_transport(responses):
    it = iter(responses)

    def handler(request):
        return httpx.Response(200, text=next(it))

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_flex_connector_polls_until_ready():
    ok = '<FlexStatementResponse><Status>Success</Status><ReferenceCode>42</ReferenceCode></FlexStatementResponse>'
    wait = '<FlexStatementResponse><Status>Warn</Status><ErrorCode>1019</ErrorCode></FlexStatementResponse>'
    c = IBKRFlexConnector({"flex_token": "t", "query_id": "q"},
                          client=_flex_transport([ok, wait, (FIX / "ibkr_flex_sample.xml").read_text()]), sleep=lambda s: None)
    assert len(c.fetch_holdings()) == 2


def test_flex_connector_expired_token():
    bad = '<FlexStatementResponse><Status>Fail</Status><ErrorCode>1012</ErrorCode><ErrorMessage>Token has expired.</ErrorMessage></FlexStatementResponse>'
    c = IBKRFlexConnector({"flex_token": "t", "query_id": "q"}, client=_flex_transport([bad]), sleep=lambda s: None)
    with pytest.raises(ReauthRequired):
        c.validate_connection()


def test_flex_requires_credentials():
    with pytest.raises(ReauthRequired):
        IBKRFlexConnector({}).validate_connection()


def test_groww_holdings_and_missing_live_data():
    def handler(req: httpx.Request):
        assert req.headers["X-API-VERSION"] == "1.0" and req.headers["Authorization"] == "Bearer tok"
        if req.url.path == "/v1/holdings/user":
            return httpx.Response(200, json={"status": "SUCCESS", "payload": {"holdings": [
                {"isin": "INE002A01018", "trading_symbol": "RELIANCE", "quantity": 10, "average_price": 2400.5},
                {"isin": "X", "trading_symbol": "ZERO", "quantity": 0, "average_price": 1}]}})
        if req.url.path == "/v1/live-data/ltp":
            return httpx.Response(403, json={})
        return httpx.Response(404)

    g = GrowwConnector({"access_token": "tok"}, client=httpx.Client(base_url="https://api.groww.in", transport=httpx.MockTransport(handler)))
    hs = g.fetch_holdings()
    assert len(hs) == 1 and hs[0].price_type == "imported" and hs[0].market_price == D("2400.5")
    assert not g.supports(Capability.TRANSACTIONS)  # honest capability report


def test_groww_401_requires_reauth():
    g = GrowwConnector({"access_token": "tok"}, client=httpx.Client(base_url="https://api.groww.in",
                                                                      transport=httpx.MockTransport(lambda r: httpx.Response(401))))
    with pytest.raises(ReauthRequired):
        g.validate_connection()


def test_aggregator_never_pretends():
    with pytest.raises(ConnectorError):
        AggregatorConnector().validate_connection()


def test_mock_connectors_are_labeled_and_deterministic():
    for cls in (MockRevolut, MockIBKR, MockGroww):
        assert cls.info.is_mock
    a, b = MockRevolut().fetch_transactions(), MockRevolut().fetch_transactions()
    assert [t.external_id for t in a] == [t.external_id for t in b]


def test_mock_brokerage_has_no_future_dates():
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    assert all(t.occurred_at <= now for t in MockRevolut().fetch_transactions())


def test_ecb_parser():
    xml = """<gesmes:Envelope xmlns:gesmes="http://www.gesmes.org/xml/2002-08-01" xmlns="http://www.ecb.int/vocabulary/2002-08-01/eurofxref">
      <Cube><Cube time="2026-10-30"><Cube currency="USD" rate="1.0832"/><Cube currency="INR" rate="95.41"/><Cube currency="JPY" rate="160"/></Cube></Cube>
    </gesmes:Envelope>"""
    rows = ECBProvider.parse(xml, ("USD", "INR"))
    assert {(r[1], r[2]) for r in rows} == {("USD", D("1.0832")), ("INR", D("95.41"))}


def test_csv_unknown_format():
    r = parse_csv(b"foo,bar\n1,2\n", "a")
    assert r.format == "unknown" and r.errors


def test_generic_csv():
    r = parse_csv(b"date,description,amount,currency\n2026-01-05,Coffee,-3.50,eur\n", "a")
    assert r.rows[0].currency == "EUR" and r.rows[0].type_hint == "expense"
