from datetime import datetime, timedelta

from app.shoppers import TZ, Shopper


def make_shopper() -> Shopper:
    # Three orders: a Sunday 9:00, then 7 days later (Sunday 10:00), then 3 days later
    # (Wednesday 18:00). Instacart weekdays: 0 = Sunday.
    return Shopper(
        id=1,
        label="t",
        blurb="",
        usual_day="Sunday",
        orders=[[1, 2], [1, 3], [2]],
        order_dow=[0, 0, 3],
        order_hour=[9, 10, 18],
        days_since_prior=[None, 7, 3],
    )


def test_order_times_keep_weekday_hour_and_gaps():
    now = datetime(2026, 11, 8, 12, tzinfo=TZ)  # a Sunday
    times = make_shopper().order_times(now)

    assert [t.hour for t in times] == [9, 10, 18]
    assert times[-1].isoweekday() % 7 == 3  # Wednesday, in Instacart's numbering
    assert [(b.date() - a.date()).days for a, b in zip(times, times[1:], strict=False)] == [7, 3]
    assert times[-1] < now
    assert all(t.tzinfo is not None for t in times)


def test_latest_order_sits_about_one_usual_gap_before_now():
    now = datetime(2026, 11, 8, 12, tzinfo=TZ)
    shopper = make_shopper()
    gap = (now.date() - shopper.order_times(now)[-1].date()).days
    # usual gap is 5 days (median of 7 and 3); stepping back to the right weekday adds < 7
    assert shopper.usual_gap_days <= gap < shopper.usual_gap_days + 7


def test_an_order_placed_in_the_app_joins_the_history_at_its_time():
    shopper = make_shopper()
    at = datetime(2026, 11, 8, 15, tzinfo=TZ)
    before = shopper.order_times(at)
    shopper.add_order([7, 1], at)

    times = shopper.order_times(at)
    assert shopper.n_orders == 4 and shopper.times_bought[7] == 1 and shopper.times_bought[1] == 3
    assert times[-1] == at
    assert times[:-1] == before  # the Instacart timeline doesn't move under it


def test_next_visit_slides_the_whole_history_back():
    shopper = make_shopper()
    now = datetime(2026, 11, 8, 12, tzinfo=TZ)
    shopper.add_order([7], now)
    before = shopper.order_times(now)
    shopper.advance(7)
    shifts = [b - a for a, b in zip(shopper.order_times(now), before, strict=True)]
    assert shifts == [timedelta(days=7)] * 4
