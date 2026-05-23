from django.shortcuts import redirect, render
from django.urls import reverse

from .forms import ContactForm


def contact(request):
    if request.method == "POST":
        form = ContactForm(request.POST)
        if form.is_valid():
            form.save_and_notify()
            return redirect(reverse("contact:merci"))
    else:
        form = ContactForm()
    return render(request, "contact/form.html", {"form": form})


def merci(request):
    return render(request, "contact/merci.html", {})
