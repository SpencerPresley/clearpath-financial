from allauth.account.adapter import DefaultAccountAdapter
from django.http import HttpRequest


class AccountAdapter(DefaultAccountAdapter):
    """Admins provision every account (accounts/api.py), so allauth's public signup is closed. allauth's default
    leaves it open: anyone who reaches /_allauth/*/v1/auth/signup would get a signed-in, role-less account."""

    def is_open_for_signup(self, request: HttpRequest) -> bool:  # noqa: ARG002  # allauth's signature
        return False
