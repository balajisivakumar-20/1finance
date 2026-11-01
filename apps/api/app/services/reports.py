"""Report builders → CSV / XLSX / PDF. Never includes credentials or tokens."""
from __future__ import annotations

import csv
import io
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.api.fmt import m, pct
from app.models import Account, Category, Transaction
from app.services import analytics
from app.services.ledger import Ledger, load_fx, to_base

KINDS = {
    "monthly": "Monthly financial summary",
    "annual": "Annual financial summary",
    "income-expense": "Income and expense report",
    "categories": "Spending category report",
    "holdings": "Investment holdings report",
    "net-worth": "Net worth report",
    "allocation": "Asset allocation report",
    "transactions": "Transaction statement",
}


class Report:
    def __init__(self, title: str, period: tuple[date, date], currency: str):
        self.title, self.period, self.currency = title, period, currency
        self.summary: list[tuple[str, str]] = []
        self.tables: list[tuple[str, list[str], list[list]]] = []
        self.notes: list[str] = []
        self.chart: list[tuple[str, float]] | None = None
        self.generated_at = datetime.now(timezone.utc)


def _period(kind: str, start: date | None, end: date | None) -> tuple[date, date]:
    today = datetime.now(timezone.utc).date()
    if start and end:
        return start, end
    if kind == "monthly":
        s = (today.replace(day=1) - relativedelta(months=1))
        return s, today.replace(day=1) - timedelta(days=1)
    if kind == "annual":
        return date(today.year, 1, 1), today
    return today - relativedelta(months=12), today


def build(db: Session, user_id: int, kind: str, base: str, start: date | None = None, end: date | None = None) -> Report:
    if kind not in KINDS:
        raise KeyError(kind)
    s, e = _period(kind, start, end)
    r = Report(KINDS[kind], (s, e), base)
    fx = load_fx(db)
    now = datetime.now(timezone.utc)
    ledger = Ledger(db, user_id)
    if ledger.accounts and any(a.is_demo for a in ledger.accounts.values()):
        r.notes.append("Contains DEMONSTRATION data — not real financial information.")
    if kind in ("monthly", "annual", "income-expense", "categories"):
        summ = analytics.period_summary(db, user_id, fx, base, s, e + timedelta(days=1))
        r.summary += [("Income", f"{m(summ.income, base)}"), ("Expenses", f"{m(summ.expenses, base)}"),
                      ("Net savings", f"{m(summ.savings, base)}"),
                      ("Savings rate", f"{pct(summ.savings_rate)} %" if summ.savings_rate is not None else "n/a (no income)")]
        groups = analytics.group_by_parent(summ.by_category, analytics.category_parent_map(db, user_id))
        r.tables.append(("Spending by category", ["Category", f"Amount ({base})", "Share %"],
                         [[g["name"], m(g["amount"], base), pct(g["share"])] for g in groups]))
        r.chart = [(g["name"], float(g["amount"])) for g in groups[:8]]
        if summ.pending_excluded:
            r.notes.append(f"{summ.pending_excluded} pending transactions excluded.")
        if kind in ("annual", "income-expense"):
            months = analytics.monthly_series(db, user_id, fx, base, 12, e)
            r.tables.append(("Monthly cash flow", ["Month", "Income", "Expenses", "Net"],
                             [[x["month"], m(x["income"], base), m(x["expenses"], base), m(x["net"], base)] for x in months]))
    if kind in ("monthly", "annual", "net-worth", "allocation"):
        nw, meta = ledger.net_worth_at(now, base)
        r.summary += [("Total assets", f"{m(nw.total_assets, base)}"), ("Total liabilities", f"{m(nw.total_liabilities, base)}"),
                      ("Net worth", f"{m(nw.net_worth, base)}")]
        tot = nw.total_assets or Decimal(1)
        r.tables.append(("Asset allocation", ["Bucket", f"Value ({base})", "Share %"],
                         [[k.replace("_", " ").title(), m(v, base), pct(v / tot * 100)] for k, v in sorted(nw.allocation.items(), key=lambda kv: -kv[1])]))
        if nw.includes_estimates:
            r.notes.append("Includes manually estimated valuations.")
        if "delayed" in meta["price_types"] or "close" in meta["price_types"]:
            r.notes.append("Security prices are delayed or last available close.")
        if kind == "net-worth":
            pts = ledger.history(s, e, base, 7)
            r.tables.append(("Net worth history (weekly)", ["Date", "Assets", "Liabilities", "Net worth"],
                             [[p["date"], m(p["assets"], base), m(p["liabilities"], base), m(p["net_worth"], base)] for p in pts]))
            r.chart = [(p["date"][5:], float(p["net_worth"])) for p in pts[:: max(1, len(pts) // 12)]]
    if kind == "holdings":
        rows = []
        for a in ledger.accounts.values():
            for h in ledger.latest_holdings(a.id):
                rows.append([h.security.ticker, h.security.name, a.connection.institution.name if a.connection else "",
                             h.quantity.normalize(), m(h.average_price, h.currency), m(h.market_price, h.currency),
                             m(h.market_value, h.currency), h.currency, m(to_base(fx, h.market_value, h.currency, base, now), base), h.price_type])
        r.tables.append(("Holdings", ["Ticker", "Name", "Broker", "Qty", "Avg price", "Price", "Value", "Ccy", f"Value ({base})", "Price type"], rows))
    if kind == "transactions":
        cats = {c.id: c.name for c in db.scalars(select(Category))}
        q = (select(Transaction).join(Account).where(Account.user_id == user_id,
             Transaction.transaction_date >= datetime.combine(s, datetime.min.time(), tzinfo=timezone.utc),
             Transaction.transaction_date < datetime.combine(e + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc))
             .options(joinedload(Transaction.account)).order_by(Transaction.transaction_date))
        rows = [[t.transaction_date.date(), t.raw_description, t.account.nickname or t.account.account_name,
                 cats.get(t.user_category_id or t.category_id, ""), t.user_type or t.transaction_type, m(t.amount, t.currency), t.currency,
                 m(to_base(fx, t.amount, t.currency, base, t.transaction_date), base), t.transaction_status] for t in db.scalars(q)]
        r.tables.append(("Transactions", ["Date", "Description", "Account", "Category", "Type", "Amount", "Ccy", f"Amount ({base})", "Status"], rows))
        r.summary.append(("Transactions", str(len(rows))))
    return r


def to_csv(r: Report) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([r.title])
    w.writerow(["Period", r.period[0], r.period[1]])
    w.writerow(["Base currency", r.currency])
    w.writerow(["Generated (UTC)", r.generated_at.isoformat(timespec="seconds")])
    for n in r.notes:
        w.writerow(["Note", n])
    w.writerow([])
    for k, v in r.summary:
        w.writerow([k, v])
    for name, headers, rows in r.tables:
        w.writerow([])
        w.writerow([name])
        w.writerow(headers)
        w.writerows(rows)
    return buf.getvalue().encode("utf-8-sig")


def to_xlsx(r: Report) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    wb = Workbook()
    ws = wb.active
    ws.title = "Summary"
    ws["A1"] = f"1Finance — {r.title}"
    ws["A1"].font = Font(size=14, bold=True, color="047857")
    meta = [("Period", f"{r.period[0]} → {r.period[1]}"), ("Base currency", r.currency),
            ("Generated (UTC)", r.generated_at.strftime("%Y-%m-%d %H:%M"))] + [("Note", n) for n in r.notes]
    for i, (k, v) in enumerate(meta + [("", "")] + r.summary, start=3):
        ws.cell(i, 1, k).font = Font(bold=True)
        ws.cell(i, 2, _cell(v))
    ws.column_dimensions["A"].width = 24
    ws.column_dimensions["B"].width = 28
    head = PatternFill("solid", fgColor="E6F4EF")
    for name, headers, rows in r.tables:
        t = wb.create_sheet(name[:31])
        for j, h in enumerate(headers, 1):
            c = t.cell(1, j, h)
            c.font, c.fill, c.alignment = Font(bold=True), head, Alignment(horizontal="center")
            t.column_dimensions[c.column_letter].width = max(12, min(40, len(h) + 6))
        for i, row in enumerate(rows, 2):
            for j, v in enumerate(row, 1):
                c = t.cell(i, j, _cell(v))
                if isinstance(v, Decimal):
                    c.number_format = "#,##0.00"
        t.freeze_panes = "A2"
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _cell(v):
    if isinstance(v, Decimal):
        return float(v) if abs(v) < Decimal("1e15") else str(v)  # Excel stores numbers as IEEE doubles
    return v


def to_pdf(r: Report) -> bytes:
    from reportlab.graphics.charts.barcharts import HorizontalBarChart
    from reportlab.graphics.shapes import Drawing
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    emerald, ink, muted, line = colors.HexColor("#047857"), colors.HexColor("#111827"), colors.HexColor("#6B7280"), colors.HexColor("#E5E7EB")
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=16 * mm,
                            title=f"1Finance — {r.title}", author="1Finance")
    ss = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=ss["Title"], alignment=0, fontSize=20, textColor=ink, spaceAfter=4)
    h2 = ParagraphStyle("h2", parent=ss["Heading2"], fontSize=12, textColor=ink, spaceBefore=12, spaceAfter=6)
    small = ParagraphStyle("s", parent=ss["Normal"], fontSize=8.5, textColor=muted)
    brand = ParagraphStyle("b", parent=ss["Normal"], fontSize=10, textColor=emerald, fontName="Helvetica-Bold")
    story = [Paragraph("1Finance", brand), Paragraph(r.title, h1),
             Paragraph(f"Period {r.period[0]:%d %b %Y} – {r.period[1]:%d %b %Y} · Base currency {r.currency} · "
                       f"Generated {r.generated_at:%d %b %Y %H:%M} UTC", small)]
    for n in r.notes:
        story.append(Paragraph(f"⚠ {n}", small))
    if r.summary:
        story += [Paragraph("Summary", h2)]
        t = Table([[k, v] for k, v in r.summary], colWidths=[70 * mm, 60 * mm])
        t.setStyle(TableStyle([("FONT", (0, 0), (-1, -1), "Helvetica", 9.5), ("TEXTCOLOR", (0, 0), (0, -1), muted),
                               ("ALIGN", (1, 0), (1, -1), "RIGHT"), ("LINEBELOW", (0, 0), (-1, -1), 0.4, line),
                               ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
        story.append(t)
    if r.chart:
        d = Drawing(170 * mm, 6 * mm * len(r.chart) + 10)
        c = HorizontalBarChart()
        c.x, c.y, c.width, c.height = 45 * mm, 5, 115 * mm, 6 * mm * len(r.chart)
        c.data = [[v for _, v in reversed(r.chart)]]
        c.categoryAxis.categoryNames = [k for k, _ in reversed(r.chart)]
        c.categoryAxis.labels.fontSize = 8
        c.valueAxis.labels.fontSize = 7
        c.valueAxis.valueMin = min(0, min(v for _, v in r.chart))
        c.bars[0].fillColor = emerald
        c.bars[0].strokeColor = None
        d.add(c)
        story += [Spacer(1, 6), d]
    for name, headers, rows in r.tables:
        story.append(Paragraph(name, h2))
        if not rows:
            story.append(Paragraph("No data for this period.", small))
            continue
        data = [headers] + [[_fmt(v) for v in row] for row in rows]
        t = Table(data, repeatRows=1)
        t.setStyle(TableStyle([("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8), ("FONT", (0, 1), (-1, -1), "Helvetica", 7.5),
                               ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#ECFDF5")), ("TEXTCOLOR", (0, 0), (-1, 0), emerald),
                               ("LINEBELOW", (0, 0), (-1, -1), 0.3, line), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                               ("ALIGN", (1, 1), (-1, -1), "RIGHT")]))
        story.append(t)

    def footer(canvas, _doc):
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(muted)
        canvas.drawString(18 * mm, 9 * mm, "1Finance · Personal financial report · Read-only aggregation · Not financial advice")
        canvas.drawRightString(A4[0] - 18 * mm, 9 * mm, f"Page {_doc.page}")

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue()


def _fmt(v) -> str:
    if isinstance(v, Decimal):
        return f"{v:,.2f}" if v == v.quantize(Decimal("0.01")) else f"{v:,}"
    return "" if v is None else str(v)[:60]


__all__ = ["KINDS", "build", "to_csv", "to_xlsx", "to_pdf", "func"]
