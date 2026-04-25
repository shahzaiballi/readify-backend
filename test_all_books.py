#!/usr/bin/env python
"""
Show ALL books and their source values.
"""

import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
django.setup()

from apps.books.models import Book

print("\n" + "="*70)
print("ALL BOOKS IN DATABASE")
print("="*70)

books = Book.objects.all()
print(f"\nTotal books: {books.count()}\n")

for book in books:
    print(f"ID: {book.id}")
    print(f"  Title: {book.title}")
    print(f"  Author: {book.author}")
    print(f"  Source: {book.source} (should be 'user_upload' or 'admin')")
    print(f"  Category: {book.category}")
    print(f"  Processing Status: {book.processing_status}")
    print()

print("="*70)
print("If user-uploaded books show source='admin', that's the BUG!")
print("="*70 + "\n")
