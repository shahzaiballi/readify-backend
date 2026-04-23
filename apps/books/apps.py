"""
apps/books/apps.py

AppConfig for the books app.
Connects Django signals so that saving a Book with a PDF
automatically kicks off background processing.
"""

from django.apps import AppConfig


class BooksConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.books'

    def ready(self):
        """
        Called once when Django starts up.
        We import signals here so they get registered.
        """
        import apps.books.signals  # noqa: F401