"""
apps/books/toc_detector.py

Smart TOC/Chapter detection module — 3 deterministic paths before any AI.

Path A: PDF Bookmarks  — fitz.get_toc()               ~60 % of books
Path B: Text TOC       — regex on first 30 pages       ~25 % of books
Path C: AI Fallback    — page signals only             ~15 % of books
Final:  Manual split   — 17 pages/chapter              safety net

No AI is called in Path A or B.  AI in Path C receives ~1,500 words maximum.
"""

import re
import logging

logger = logging.getLogger(__name__)


# ── Path A: PDF Bookmarks ─────────────────────────────────────────────────────

def detect_from_bookmarks(pdf_path: str) -> list[dict]:
    """
    Read chapter structure directly from PDF bookmark metadata.
    Uses fitz.get_toc() which returns [[level, title, page], ...].
    Returns empty list if the PDF has no bookmarks.
    """
    try:
        import fitz
    except ImportError:
        logger.error('[TOC-A] PyMuPDF not installed')
        return []

    try:
        doc = fitz.open(pdf_path)
        toc = doc.get_toc()
        total_pages = len(doc)
        doc.close()
    except Exception as exc:
        logger.warning(f'[TOC-A] Could not open PDF: {exc}')
        return []

    if not toc:
        return []

    # Prefer level-1 entries; fall back to level-2 if none exist
    entries = [e for e in toc if e[0] == 1]
    if not entries:
        entries = [e for e in toc if e[0] == 2]
    if not entries:
        return []

    chapters = []
    for i, (_, title, start_page) in enumerate(entries):
        start_page = max(1, min(start_page, total_pages))
        end_page = entries[i + 1][2] - 1 if i + 1 < len(entries) else total_pages
        end_page = min(end_page, total_pages)
        end_page = max(start_page, end_page)

        title = title.strip()
        if not title:
            title = f'Chapter {i + 1}'

        chapters.append({
            'chapter_number': i + 1,
            'title': title,
            'start_page': start_page,
            'end_page': end_page,
            'page_range_display': f'Pages {start_page}–{end_page}',
        })

    logger.info(f'[TOC-A] {len(chapters)} chapters from PDF bookmarks')
    return chapters


# ── Path B: Text TOC Regex ────────────────────────────────────────────────────

def detect_from_text(pages: list[dict], total_pages: int) -> list[dict]:
    """
    Parse chapter structure from a text-based Table of Contents found in the
    first 30 pages.  Matches lines like:
        Chapter 1 ........... 15
        1. Introduction .... 3
        CHAPTER ONE ........ 22
    """
    if not pages:
        return []

    toc_pages = pages[:30]
    toc_text = '\n'.join(p['text'] for p in toc_pages)

    # Primary pattern: anything followed by 3+ dots/spaces then a page number
    pattern = re.compile(r'^(.+?)[\.\s]{3,}(\d+)\s*$', re.MULTILINE)
    matches = pattern.findall(toc_text)

    if not matches:
        return []

    candidates = []
    for raw_title, page_str in matches:
        title = raw_title.strip()
        try:
            page_num = int(page_str)
        except ValueError:
            continue

        if page_num < 1 or page_num > total_pages:
            continue
        if len(title) < 3 or len(title) > 120:
            continue
        if title.isdigit():
            continue

        candidates.append({'title': title, 'page': page_num})

    if len(candidates) < 2:
        return []

    # Deduplicate (same title + page)
    seen = set()
    unique = []
    for c in candidates:
        key = (c['title'].lower(), c['page'])
        if key not in seen:
            seen.add(key)
            unique.append(c)
    candidates = unique

    # Sort by page and validate ascending order
    candidates.sort(key=lambda x: x['page'])
    for i in range(1, len(candidates)):
        if candidates[i]['page'] <= candidates[i - 1]['page']:
            return []

    chapters = []
    for i, c in enumerate(candidates):
        end_page = candidates[i + 1]['page'] - 1 if i + 1 < len(candidates) else total_pages
        chapters.append({
            'chapter_number': i + 1,
            'title': c['title'],
            'start_page': c['page'],
            'end_page': end_page,
            'page_range_display': f"Pages {c['page']}–{end_page}",
        })

    logger.info(f'[TOC-B] {len(chapters)} chapters from text TOC regex')
    return chapters


# ── Path C Prep: Build AI Page Signals ───────────────────────────────────────

def build_page_signals(pages: list[dict]) -> str:
    """
    Build a compact signal string for the AI fallback.
    Takes the first 3 lines of every 8th page.
    Produces roughly 1,500 words — well within the 8,000-word AI limit.
    """
    signals = []
    step = 4 if len(pages) < 60 else 8
    for page in pages[::step]:
        page_num = page['page_number']
        text = page['text'].strip()
        lines = [ln.strip() for ln in text.split('\n') if ln.strip()][:3]
        if lines:
            signals.append(f"Page {page_num}: {' | '.join(lines)}")

    return '\n'.join(signals)


# ── Validation ────────────────────────────────────────────────────────────────

def validate_chapter_structure(chapters: list[dict], total_pages: int) -> bool:
    """
    Safety-check that chapter structure is internally consistent.
    Returns True only if all constraints pass.
    """
    if not chapters:
        return False

    # Require at least 2 chapters; cap at total_pages / 3
    if len(chapters) < 2:
        return False
    max_chapters = max(2, total_pages // 3)
    if total_pages > 0 and len(chapters) > max_chapters:
        logger.warning(
            f'[TOC] Rejected: {len(chapters)} chapters for {total_pages} pages '
            f'(limit={max_chapters})'
        )
        return False

    for i, ch in enumerate(chapters):
        sp = ch.get('start_page', 0)
        ep = ch.get('end_page', 0)

        if sp < 1 or ep < sp:
            logger.warning(f'[TOC] Invalid range ch{i + 1}: {sp}-{ep}')
            return False
        if total_pages > 0 and ep > int(total_pages * 1.3) + 5:
            logger.warning(f'[TOC] ch{i + 1} end_page {ep} > total_pages {total_pages}')
            return False

    return True


# ── Manual Fallback ───────────────────────────────────────────────────────────

def build_manual_chapters(pages: list[dict], pages_per_chapter: int = 17) -> list[dict]:
    """
    Deterministic fallback: group pages into fixed-size chapters.
    Used only when all 3 detection paths fail.
    """
    if not pages:
        return []

    total_pages = len(pages)
    chapters = []

    for i in range(0, total_pages, pages_per_chapter):
        chunk_pages = pages[i:i + pages_per_chapter]
        first = chunk_pages[0]['page_number']
        last = chunk_pages[-1]['page_number']
        num = len(chapters) + 1
        chapters.append({
            'chapter_number': num,
            'title': f'Chapter {num}',
            'start_page': first,
            'end_page': last,
            'page_range_display': f'Pages {first}–{last}',
        })

    logger.info(f'[TOC-Manual] {len(chapters)} manual chapters ({pages_per_chapter} pages each)')
    return chapters
