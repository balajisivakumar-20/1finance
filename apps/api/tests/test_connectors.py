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


def test_flex_day_first_dates_give_one_snapshot():
    # dd/MM/yyyy query settings (04/11/2026 = 4 Nov): every position and cash row must share one timestamp
    xml = """<FlexQueryResponse><FlexStatements count="1">
      <FlexStatement accountId="U1" fromDate="01/01/2026" toDate="04/11/2026" whenGenerated="05/11/2026;050326">
        <CashReport>
          <CashReportCurrency currency="BASE_SUMMARY" endingCash="10.06"/>
          <CashReportCurrency currency="EUR" endingCash="10.06"/>
          <CashReportCurrency currency="USD" endingCash="0"/>
        </CashReport>
        <OpenPositions>
          <OpenPosition currency="USD" assetCategory="STK" symbol="AMD" position="4" markPrice="488.78" levelOfDetail="SUMMARY" reportDate="04/11/2026"/>
          <OpenPosition currency="USD" assetCategory="STK" symbol="NVDA" position="7" markPrice="200.13" levelOfDetail="SUMMARY" reportDate="04/11/2026"/>
        </OpenPositions>
      </FlexStatement></FlexStatements></FlexQueryResponse>"""
    from datetime import datetime, timezone
    from unittest.mock import patch

    with patch("app.connectors.ibkr_flex.datetime", wraps=datetime) as dt:
        dt.now.return_value = datetime(2026, 11, 5, 6, tzinfo=timezone.utc)
        p = FlexStatementParser(xml)
    stamps = {b.as_of for b in p.cash_balances()} | {h.as_of for h in p.holdings()}
    assert stamps == {datetime(2026, 11, 4, tzinfo=timezone.utc)}


def test_flex_date_formats():
    from datetime import datetime, timezone

    from app.connectors.ibkr_flex import _dt

    d = datetime(2026, 11, 4, tzinfo=timezone.utc)
    assert _dt("20261104") == _dt("2026-11-04") == _dt("11/04/2026") == _dt("04/11/2026", day_first=True) == _dt("04-Nov-26") == d
    assert _dt("05/11/2026;050326", day_first=True) == datetime(2026, 11, 5, 5, 3, 26, tzinfo=timezone.utc)
    assert _dt("2026-11-04 15:30:00") == datetime(2026, 11, 4, 15, 30, tzinfo=timezone.utc)


def test_flex_cost_basis_and_realized_from_trades_when_ibkr_reports_zero():
    xml = """<FlexQueryResponse><FlexStatements count="1">
      <FlexStatement accountId="U1" toDate="20261104" whenGenerated="20261105;050326">
        <OpenPositions>
          <OpenPosition currency="USD" assetCategory="STK" symbol="AMD" position="4" markPrice="488.78" costBasisPrice="0" costBasisMoney="0" levelOfDetail="SUMMARY"/>
          <OpenPosition currency="USD" assetCategory="STK" symbol="OLD" position="5" markPrice="10" costBasisPrice="0" levelOfDetail="SUMMARY"/>
        </OpenPositions>
        <Trades>
          <Trade tradeID="1" assetCategory="STK" symbol="AMD" currency="USD" quantity="6" netCash="-601" fifoPnlRealized="0" levelOfDetail="EXECUTION" tradeDate="20260301"/>
          <Trade tradeID="2" assetCategory="STK" symbol="AMD" currency="USD" quantity="-2" netCash="299" fifoPnlRealized="0" levelOfDetail="EXECUTION" tradeDate="20260401"/>
          <Trade tradeID="3" assetCategory="STK" symbol="OLD" currency="USD" quantity="-1" netCash="10" fifoPnlRealized="0" levelOfDetail="EXECUTION" tradeDate="20260301"/>
          <Trade tradeID="4" assetCategory="CASH" symbol="EUR.USD" currency="USD" quantity="-500" netCash="0" levelOfDetail="EXECUTION" tradeDate="20260301"/>
        </Trades>
      </FlexStatement></FlexStatements></FlexQueryResponse>"""
    p = FlexStatementParser(xml)
    h = {x.security.ticker: x for x in p.holdings()}
    assert h["AMD"].average_price == D("601") / 6  # bought 6 for 601 incl. commission; selling 2 keeps the average
    assert h["OLD"].average_price == 0  # sold before any buy in the statement: history incomplete, so no guess
    acts = {a.external_id: a for a in p.activity()}
    assert "4" not in acts  # currency conversions are not investment trades
    assert acts["2"].realized_pl == D("299") - D("601") * 2 / 6
    assert acts["3"].realized_pl is None
