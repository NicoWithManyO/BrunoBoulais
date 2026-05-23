"""Custom allauth adapter — keeps signup closed.

The site has a single trusted user (Bruno). Anyone needing access is created
by a superuser via `manage.py createsuperuser` or the admin.
"""
from allauth.account.adapter import DefaultAccountAdapter


class NoSignupAccountAdapter(DefaultAccountAdapter):
    def is_open_for_signup(self, request):
        return False
