"""Custom form widgets used by /gestion/."""
from django import forms


class RichTextWidget(forms.Textarea):
    """A B/I-only rich text editor wrapping a hidden textarea.

    ``mode='block'`` (default) keeps Enter → new paragraph and lets <p> through
    bleach at render time. ``mode='inline'`` rebinds Enter → <br> and the
    rendered output strips <p> wrappers — use for fields placed inside an
    existing block container like an <h1> or a pull-quote.
    """

    template_name = "core/richtext_widget.html"

    def __init__(self, attrs=None, mode="block"):
        self.mode = mode
        super().__init__(attrs)

    def get_context(self, name, value, attrs):
        ctx = super().get_context(name, value, attrs)
        ctx["widget"]["mode"] = self.mode
        return ctx

    class Media:
        js = ("js/richtext.js",)
