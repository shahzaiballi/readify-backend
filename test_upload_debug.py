#!/usr/bin/env python
"""
Quick test to check if UserBook table exists and has the right structure.
Run this with: python manage.py shell < test_upload_debug.py
Or: python test_upload_debug.py
"""

import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
django.setup()

from apps.library.models import UserBook
from apps.books.models import Book
from django.contrib.auth import get_user_model

User = get_user_model()

print("\n" + "="*60)
print("UPLOAD DEBUG TEST")
print("="*60)

# Check UserBook model
print("\n✓ UserBook model imported successfully")
print(f"  - Status choices: {UserBook.Status.choices}")
print(f"  - NOT_STARTED value: {UserBook.Status.NOT_STARTED}")

# Check Book model
print("\n✓ Book model imported successfully")
print(f"  - Source choices: {Book.Source.choices}")
print(f"  - USER_UPLOAD value: {Book.Source.USER_UPLOAD}")

# Check if any books exist
book_count = Book.objects.count()
print(f"\n✓ Total books in DB: {book_count}")

user_book_count = UserBook.objects.count()
print(f"✓ Total UserBook entries in DB: {user_book_count}")

# Check user-uploaded books specifically
user_upload_books = Book.objects.filter(source=Book.Source.USER_UPLOAD)
print(f"\n✓ User-uploaded books: {user_upload_books.count()}")
if user_upload_books.exists():
    for book in user_upload_books:
        print(f"  - {book.title} (by {book.author})")
        user_books = UserBook.objects.filter(book=book)
        print(f"    Users with this book: {user_books.count()}")
        for ub in user_books:
            print(f"      - {ub.user.email}")

# List all users
print(f"\n✓ Total users: {User.objects.count()}")
users = User.objects.all()
for user in users[:5]:  # Show first 5 users
    user_books = UserBook.objects.filter(user=user)
    print(f"  - {user.email}: {user_books.count()} books")

print("\n" + "="*60)
print("If you just uploaded a book, check if:")
print("1. It appears in 'User-uploaded books' section")
print("2. The UserBook entries show your user email")
print("="*60 + "\n")
