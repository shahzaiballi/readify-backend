"""
apps/books/cover_service.py
"""

import requests
import logging
import os
import fitz  # PyMuPDF
from uuid import uuid4
from urllib.parse import quote_plus
from django.conf import settings

logger = logging.getLogger(__name__)

_REQUEST_TIMEOUT = 8


# ─────────────────────────────────────────────────────────────
# MAIN FUNCTION
# ─────────────────────────────────────────────────────────────

def fetch_cover_image_url(title: str, author: str = '', pdf_path: str = None) -> str:
    """
    Priority:
    1. Extract from uploaded PDF
    2. Google Books API
    3. Open Library API
    4. Placeholder
    """

    # ✅ 1. PDF FIRST PAGE (NEW FEATURE)
    if pdf_path:
        url = extract_first_page_cover(pdf_path)
        if url:
            logger.info(f"[Cover] Extracted from PDF for '{title}'")
            return url

    # ✅ 2. GOOGLE BOOKS
    url = _try_google_books(title, author)
    if url:
        logger.info(f"[Cover] Google Books found cover for '{title}'")
        return url

    # ✅ 3. OPEN LIBRARY
    url = _try_open_library(title, author)
    if url:
        logger.info(f"[Cover] Open Library found cover for '{title}'")
        return url

    # ✅ 4. PLACEHOLDER
    logger.info(f"[Cover] Using placeholder for '{title}'")
    return _generate_placeholder_url(title)


# ─────────────────────────────────────────────────────────────
# NEW: PDF → IMAGE
# ─────────────────────────────────────────────────────────────

def extract_first_page_cover(pdf_path: str) -> str | None:
    try:
        doc = fitz.open(pdf_path)
        page = doc.load_page(0)

        # Increase quality
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))

        filename = f"covers/{uuid4().hex}.png"
        full_path = os.path.join(settings.MEDIA_ROOT, filename)

        os.makedirs(os.path.dirname(full_path), exist_ok=True)

        pix.save(full_path)
        doc.close()

        return f"{settings.MEDIA_URL}{filename}"

    except Exception as e:
        logger.warning(f"[Cover] PDF extraction failed: {e}")
        return None


# ─────────────────────────────────────────────────────────────
# GOOGLE BOOKS
# ─────────────────────────────────────────────────────────────

def _try_google_books(title: str, author: str = '') -> str | None:
    try:
        query = f'intitle:{quote_plus(title)}'
        if author.strip():
            query += f'+inauthor:{quote_plus(author.strip())}'

        resp = requests.get(
            'https://www.googleapis.com/books/v1/volumes',
            params={'q': query, 'maxResults': 1},
            timeout=_REQUEST_TIMEOUT,
        )

        if resp.status_code != 200:
            return None

        items = resp.json().get('items', [])
        if not items:
            return None

        image_links = items[0].get('volumeInfo', {}).get('imageLinks', {})

        raw_url = (
            image_links.get('thumbnail')
            or image_links.get('smallThumbnail')
        )

        if not raw_url:
            return None

        return (
            raw_url
            .replace('http://', 'https://')
            .replace('&edge=curl', '')
            .replace('zoom=1', 'zoom=0')
        )

    except Exception as e:
        logger.warning(f"[Cover] Google Books error: {e}")
        return None


# ─────────────────────────────────────────────────────────────
# OPEN LIBRARY
# ─────────────────────────────────────────────────────────────

def _try_open_library(title: str, author: str = '') -> str | None:
    try:
        query = f"{title} {author}".strip()

        resp = requests.get(
            'https://openlibrary.org/search.json',
            params={'q': query, 'limit': 1},
            timeout=_REQUEST_TIMEOUT,
        )

        if resp.status_code != 200:
            return None

        docs = resp.json().get('docs', [])
        if not docs:
            return None

        doc = docs[0]

        if doc.get('cover_i'):
            return f"https://covers.openlibrary.org/b/id/{doc['cover_i']}-L.jpg"

        if doc.get('isbn'):
            return f"https://covers.openlibrary.org/b/isbn/{doc['isbn'][0]}-L.jpg"

        return None

    except Exception as e:
        logger.warning(f"[Cover] Open Library error: {e}")
        return None


# ─────────────────────────────────────────────────────────────
# PLACEHOLDER
# ─────────────────────────────────────────────────────────────

def _generate_placeholder_url(title: str) -> str:
    colours = [
        '6A4CFF', 'B062FF', '3861FB', '00B4D8',
        'E83E8C', 'FF6B35', '00C49A', 'FFB703',
    ]

    index = ord(title[0].upper()) % len(colours) if title else 0
    bg = colours[index]

    words = title.split()[:2]
    initials = '+'.join(w[:2].upper() for w in words) if words else 'BK'

    return (
        f'https://ui-avatars.com/api/?name={quote_plus(initials)}'
        f'&size=300&background={bg}&color=fff&bold=true&format=png'
    )