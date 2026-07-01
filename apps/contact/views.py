import logging
import math

from django.shortcuts import redirect, render
from django.urls import reverse

from apps.core.ratelimit import bucket_usage, log_ip_unresolved_dedup, ratelimit_bucket
from apps.core.seo import seo

from .forms import ContactForm
from .models import ContactPage

logger = logging.getLogger(__name__)

# Rate-limit : 5 POST/heure par bucket IP (helpers partagés dans apps.core.ratelimit).
_RL_GROUP = "contact:contact"
_RL_RATE = "5/h"
_RL_LOG_KEY = "apps.contact.views:ip-unresolved-logged"


def contact(request):
    rate_limited = False
    ip_unresolved = False
    retry_after = None
    if request.method == "POST":
        form = ContactForm(request.POST)
        # Honeypot trip = bot. On burn le bucket (pénaliser) puis on redirect
        # /merci/ pour ne pas révéler qu'on a détecté le piège (anti-fingerprint).
        if (request.POST.get("website") or "").strip():
            bucket = ratelimit_bucket(request)
            if bucket is None:
                log_ip_unresolved_dedup(request, log_key=_RL_LOG_KEY, label="Contact")
            else:
                bucket_usage(request, bucket, group=_RL_GROUP, rate=_RL_RATE, increment=True)
            return redirect(reverse("contact:merci"))
        if form.is_valid():
            bucket = ratelimit_bucket(request)
            if bucket is None:
                log_ip_unresolved_dedup(request, log_key=_RL_LOG_KEY, label="Contact")
                ip_unresolved = True
            else:
                usage = bucket_usage(request, bucket, group=_RL_GROUP, rate=_RL_RATE, increment=False)
                if usage is not None and usage["count"] >= usage["limit"]:
                    rate_limited = True
                    retry_after = max(1, math.ceil(usage["time_left"]))
                else:
                    form.save_and_notify()
                    bucket_usage(request, bucket, group=_RL_GROUP, rate=_RL_RATE, increment=True)
                    return redirect(reverse("contact:merci"))
    else:
        form = ContactForm()
    response = render(
        request,
        "contact/form.html",
        {
            "form": form,
            "page": ContactPage.get_solo(),
            "rate_limited": rate_limited,
            "ip_unresolved": ip_unresolved,
            **seo(
                request,
                title="Contact · Bruno Boulais",
                description="Écrire à Bruno Boulais.",
            ),
        },
    )
    if ip_unresolved:
        response.status_code = 503
        response["Cache-Control"] = "no-store"
    elif rate_limited:
        response.status_code = 429
        response["Retry-After"] = str(retry_after)
        response["Cache-Control"] = "no-store"
    return response


def merci(request):
    return render(
        request,
        "contact/merci.html",
        {
            "page": ContactPage.get_solo(),
            **seo(request, title="Message envoyé · Bruno Boulais"),
        },
    )
