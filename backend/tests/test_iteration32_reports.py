"""Regression tests for iteration 32: automated sales report + multi-currency."""
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

import reports


MX = ZoneInfo("America/Mexico_City")


def test_is_due_weekly_matches_day_and_hour():
    cfg = {"frequency": "weekly", "day": 0, "hour": 8}  # Monday 08:00
    monday_8 = datetime(2026, 6, 15, 8, 0, tzinfo=MX)  # 2026-06-15 is a Monday
    assert reports._is_due(cfg, monday_8, "") is True


def test_is_due_weekly_wrong_hour():
    cfg = {"frequency": "weekly", "day": 0, "hour": 8}
    monday_9 = datetime(2026, 6, 15, 9, 0, tzinfo=MX)
    assert reports._is_due(cfg, monday_9, "") is False


def test_is_due_monthly_matches_day():
    cfg = {"frequency": "monthly", "day": 1, "hour": 8}
    first_8 = datetime(2026, 6, 1, 8, 0, tzinfo=MX)
    assert reports._is_due(cfg, first_8, "") is True
    second_8 = datetime(2026, 6, 2, 8, 0, tzinfo=MX)
    assert reports._is_due(cfg, second_8, "") is False


def test_is_due_dedup_recent_send():
    cfg = {"frequency": "weekly", "day": 0, "hour": 8}
    monday_8 = datetime(2026, 6, 15, 8, 0, tzinfo=MX)
    recent = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    assert reports._is_due(cfg, monday_8, recent) is False


def test_build_workbook_has_all_sheets():
    data = {
        "period": "week", "days": 7, "currency": "MXN",
        "revenue_total": 1000.0, "collected_total": 500.0,
        "trend": [], "conversion": {"total": 3, "won": 1, "lost": 1, "rate": 33.3},
        "executives": [{"name": "Ana", "created": 2, "won": 1, "revenue": 1000.0}],
        "clients": [{"name": "Cliente X", "count": 2, "revenue": 1000.0}],
        "packages": [{"name": "Pkg", "count": 1, "revenue": 1000.0}],
        "services": [{"name": "Tour", "count": 1, "revenue": 200.0}],
        "lost": [{"code": "COT-1", "client": "Y", "amount": 500.0, "reason": "precio", "date": "2026-06-10"}],
    }
    from routes import stats
    buf = stats.build_workbook(data)
    import openpyxl
    wb = openpyxl.load_workbook(buf)
    assert set(["Resumen", "Ejecutivos", "Clientes", "Paquetes", "Servicios", "Perdidas"]).issubset(set(wb.sheetnames))
