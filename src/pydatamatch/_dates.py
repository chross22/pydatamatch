"""Date parsing and sanity checks shared by the access functions.

Ports the behaviour of datamatch's parse_dates() and stop_if_future():
survey databases hold YYYYMMDD, R and Python print YYYY-MM-DD, and both
are accepted along with date/datetime objects and a mixture of the three.
An invalid date is an error naming the offending value, never a silently
dropped request.
"""

from __future__ import annotations

import datetime as _dt
from collections.abc import Iterable

DateLike = "str | int | _dt.date | _dt.datetime"


def parse_dates(dates) -> list[_dt.date]:
    """Parse the ``dates`` argument into a sorted, unique list of dates.

    Accepts YYYYMMDD strings or ints, YYYY-MM-DD strings, ``date`` and
    ``datetime`` objects, or a mixture. A date the calendar does not have,
    such as 20150230, raises rather than being dropped: fetching fewer days
    than were asked for and saying nothing leaves the gap to be found much
    later as a missing row.
    """
    if isinstance(dates, (str, int, _dt.date)):
        dates = [dates]
    dates = list(dates)
    if len(dates) == 0:
        raise ValueError("`dates` is empty, so the request names no dates to fetch.")

    parsed: list[_dt.date] = []
    bad: list[str] = []
    for d in dates:
        if isinstance(d, _dt.datetime):
            parsed.append(d.date())
            continue
        if isinstance(d, _dt.date):
            parsed.append(d)
            continue
        text = str(d).strip()
        fmt = "%Y%m%d" if text.isdigit() and len(text) == 8 else "%Y-%m-%d"
        try:
            parsed.append(_dt.datetime.strptime(text, fmt).date())
        except ValueError:
            bad.append(text)

    if bad:
        shown = ", ".join(bad[:10])
        more = f" (and {len(bad) - 10} more)" if len(bad) > 10 else ""
        raise ValueError(
            f"`dates` could not be read as dates: {shown}{more}\n"
            "Use YYYYMMDD, YYYY-MM-DD, or date objects. A date the calendar "
            "does not have, such as 20150230, cannot be read."
        )

    # Sorted and deduplicated so the result comes back in date order however
    # the argument was written, and a date named twice is fetched once.
    return sorted(set(parsed))


def stop_if_future(days: Iterable[_dt.date], source: str, ahead: int = 0) -> None:
    """Refuse days that have not happened yet.

    A date in the future cannot have been observed, and outside a forecast
    horizon it cannot have been modelled either. Checked before anything is
    fetched, so the cost is a second rather than however long the failed
    downloads took to give up.

    ``ahead`` is how many days past today this source can legitimately reach:
    zero for anything observational, about ten for a Copernicus
    analysis-and-forecast product.
    """
    today = _dt.date.today()
    horizon = today + _dt.timedelta(days=ahead)
    future = [d for d in days if d > horizon]
    if not future:
        return

    if ahead > 0:
        reach = f"It reaches about {ahead} days past today, to {horizon.isoformat()}."
    else:
        reach = f"It reaches today, {today.isoformat()}, at the furthest."
    raise ValueError(
        f"{len(future)} requested day(s) have not happened yet - the furthest "
        f"is {max(future).isoformat()}.\n  {source} cannot have data for them. "
        f"{reach}\n  If this came from a projection window, it is asking for "
        "months no covariate can exist for."
    )
