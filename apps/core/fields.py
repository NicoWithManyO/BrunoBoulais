"""Custom model fields."""
from django.db import models

from .widgets import RichTextWidget


class RichTextField(models.TextField):
    """A TextField whose admin form widget is RichTextWidget.

    The DB column type is unchanged (LONGTEXT/TEXT). Rendering is the caller's
    responsibility: pass the value through the ``richtext`` templatetag so
    bleach gates what reaches the page (see apps.core.templatetags.richtext).
    """

    def __init__(self, *args, mode="block", **kwargs):
        self.mode = mode
        super().__init__(*args, **kwargs)

    def formfield(self, **kwargs):
        kwargs.setdefault("widget", RichTextWidget(mode=self.mode))
        return super().formfield(**kwargs)

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        if self.mode != "block":
            kwargs["mode"] = self.mode
        return name, path, args, kwargs
