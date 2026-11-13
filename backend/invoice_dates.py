"""Invoice dates use Auckland calendar days and Monday-Friday payment terms."""
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo


def invoice_created_date(value):
    if isinstance(value, datetime):
        moment = value
    elif isinstance(value, date):
        return value
    elif len(str(value)) == 10:
        return date.fromisoformat(str(value))
    else:
        moment = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(ZoneInfo('Pacific/Auckland')).date()


def invoice_due_date(created_at):
    day = invoice_created_date(created_at)
    remaining = 3
    while remaining:
        day += timedelta(days=1)
        if day.weekday() < 5:
            remaining -= 1
    return day.isoformat()
