#!/usr/bin/env python
"""
Test if the upload endpoint exists and is properly registered.
"""

import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
django.setup()

from django.urls import reverse
from django.test import Client
from django.contrib.auth import get_user_model
import json

User = get_user_model()

print("\n" + "="*60)
print("UPLOAD ENDPOINT TEST")
print("="*60)

# Check if URL is registered
try:
    url = reverse('user-book-upload')
    print(f"\n✓ Upload endpoint URL registered: {url}")
except Exception as e:
    print(f"\n✗ Upload endpoint NOT registered: {e}")
    exit(1)

# Get or create a test user
user, created = User.objects.get_or_create(
    username='test_upload_user',
    defaults={
        'email': 'test_upload@test.com',
        'first_name': 'Test',
        'last_name': 'User',
    }
)
if created:
    user.set_password('testpass123')
    user.save()
    print(f"✓ Created test user: {user.email}")
else:
    print(f"✓ Using existing test user: {user.email}")

# Create a test client and login
client = Client()
login_success = client.login(username='test_upload_user', password='testpass123')
print(f"✓ Login test: {'Success' if login_success else 'Failed - user may need password reset'}")

# Try a GET request to see if endpoint exists
print(f"\nTesting endpoint {url}...")
try:
    response = client.get(url)
    print(f"✓ GET request returned status: {response.status_code}")
    if response.status_code == 405:  # Method Not Allowed - expected
        print("  (405 is expected - POST is required)")
except Exception as e:
    print(f"✗ Error: {e}")

print("\n" + "="*60)
print("ENDPOINT REGISTRATION SUCCESSFUL")
print("="*60 + "\n")
