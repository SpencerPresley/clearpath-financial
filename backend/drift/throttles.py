"""Per-user rate limits for the endpoints that make the server fetch a page.

Each limit has its own scope: ninja's `UserRateThrottle` keys its cache history by scope and user only
(`throttle_auth_<user>`), so two plain instances on different endpoints would share one history.
"""

from ninja.throttling import UserRateThrottle


class FetchUrlThrottle(UserRateThrottle):
    scope = "drift_fetch_url"


class CheckNowThrottle(UserRateThrottle):
    scope = "drift_check_now"


def fetch_url_throttle() -> FetchUrlThrottle:
    return FetchUrlThrottle("20/m")


def check_now_throttle() -> CheckNowThrottle:
    return CheckNowThrottle("10/m")
