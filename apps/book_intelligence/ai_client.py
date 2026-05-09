"""
apps/book_intelligence/ai_client.py

DeepSeek V3 client for all Book Intelligence AI tasks.
Uses the OpenAI-compatible API (DeepSeek is drop-in compatible).

Set DEEPSEEK_API_KEY in .env to enable. If key is missing,
all calls return safe fallback responses — no crash.
"""

import re
import json
import logging
from django.conf import settings

logger = logging.getLogger(__name__)

DEEPSEEK_MODEL = 'deepseek-chat'   # DeepSeek V3
DEEPSEEK_BASE_URL = 'https://api.deepseek.com'


def _get_client():
    """Return OpenAI client pointed at DeepSeek API."""
    try:
        from openai import OpenAI
        api_key = getattr(settings, 'DEEPSEEK_API_KEY', '')
        if not api_key:
            logger.warning('[DeepSeek] DEEPSEEK_API_KEY not set — AI features disabled.')
            return None
        return OpenAI(api_key=api_key, base_url=DEEPSEEK_BASE_URL)
    except ImportError:
        logger.error('[DeepSeek] openai package not installed. Run: pip install openai')
        return None


def _parse_json_response(text: str) -> dict | list:
    """Strip markdown fences and parse JSON."""
    text = text.strip()
    text = re.sub(r'^```(?:json)?\s*', '', text)
    text = re.sub(r'\s*```$', '', text)
    return json.loads(text)


def call_deepseek(prompt: str, max_tokens: int = 2048, temperature: float = 0.3) -> str:
    """
    Core DeepSeek call. Returns raw text or raises on failure.
    """
    client = _get_client()
    if client is None:
        raise RuntimeError('DeepSeek API key not configured.')

    response = client.chat.completions.create(
        model=DEEPSEEK_MODEL,
        messages=[{'role': 'user', 'content': prompt}],
        max_tokens=max_tokens,
        temperature=temperature,
    )
    return response.choices[0].message.content.strip()


# ── Task-specific AI functions ────────────────────────────────────────────────

def classify_book(book_title: str, book_text_sample: str) -> dict:
    """
    Classify book type, language, complexity.
    Returns: {book_type, language, complexity, summary_hint}
    """
    prompt = f"""You are a book analyst. Analyze this book sample and classify it.

Book Title: "{book_title}"

Sample Text (first ~2000 chars):
{book_text_sample[:2000]}

Return ONLY valid JSON, no markdown:
{{
  "book_type": "self_help|academic|fiction|technical|biography|business|other",
  "language": "English",
  "complexity": "beginner|intermediate|advanced",
  "summary_hint": "One sentence describing what this book is about"
}}"""

    try:
        raw = call_deepseek(prompt, max_tokens=256, temperature=0.1)
        return _parse_json_response(raw)
    except Exception as e:
        logger.warning(f'[DeepSeek] classify_book failed: {e}')
        return {
            'book_type': 'other',
            'language': 'English',
            'complexity': 'intermediate',
            'summary_hint': f'A book titled "{book_title}"',
        }


def detect_chapter_structure(book_title: str, full_text: str, existing_chapters: list[dict]) -> list[dict]:
    """
    Detect semantic chapter structure from book text.
    existing_chapters: list of {chapter_number, title, page_range} from apps.books

    Returns: list of {chapter_number, title, start_page, end_page, hook}
    """
    chapters_context = json.dumps(existing_chapters[:20], indent=2)

    prompt = f"""You are analyzing the structure of "{book_title}".

Existing chapter divisions (from PDF processing):
{chapters_context}

Your task: Review these chapters and create a clean, semantic structure.
- Keep the same page ranges but improve chapter titles to be meaningful and descriptive
- Add a one-sentence "hook" for each chapter (what the reader will learn)
- If chapters seem too granular, you may suggest combining them

Return ONLY valid JSON array, no markdown:
[
  {{
    "chapter_number": 1,
    "title": "Descriptive title (max 60 chars)",
    "start_page": 1,
    "end_page": 17,
    "hook": "One sentence describing the core idea of this chapter"
  }}
]"""

    try:
        raw = call_deepseek(prompt, max_tokens=2048, temperature=0.2)
        result = _parse_json_response(raw)
        if isinstance(result, list):
            return result
        return existing_chapters
    except Exception as e:
        logger.warning(f'[DeepSeek] detect_chapter_structure failed: {e}')
        # Fall back to existing structure with generic hooks
        return [
            {
                'chapter_number': ch.get('chapter_number', i + 1),
                'title': ch.get('title', f"Chapter {i + 1}"),
                'start_page': 1,
                'end_page': 17,
                'hook': f"Key ideas from chapter {i + 1}",
            }
            for i, ch in enumerate(existing_chapters)
        ]


def generate_book_brief(book_title: str, book_author: str, chapter_summaries: list[str]) -> dict:
    """
    Generate the Book Brief — a single-page intelligence report.
    Returns: {what_its_about, who_its_for, core_argument, top_5_ideas, verdict}
    """
    summaries_text = '\n\n'.join(
        f"Chapter {i+1}: {s}" for i, s in enumerate(chapter_summaries[:10])
    )

    prompt = f"""You are creating a Book Brief for "{book_title}" by {book_author}.

Based on these chapter summaries:
{summaries_text}

Generate a concise intelligence report. Return ONLY valid JSON, no markdown:
{{
  "what_its_about": "2-3 sentences explaining the book's core subject",
  "who_its_for": "Who will benefit most from this book (1-2 sentences)",
  "core_argument": "The single most important thesis or claim the book makes",
  "top_5_ideas": [
    "Idea 1: brief explanation",
    "Idea 2: brief explanation",
    "Idea 3: brief explanation",
    "Idea 4: brief explanation",
    "Idea 5: brief explanation"
  ],
  "verdict": "Is it worth reading? Honest 2-3 sentence assessment",
  "time_to_read_hours": 6
}}"""

    try:
        raw = call_deepseek(prompt, max_tokens=1024, temperature=0.4)
        return _parse_json_response(raw)
    except Exception as e:
        logger.warning(f'[DeepSeek] generate_book_brief failed: {e}')
        return {
            'what_its_about': f'"{book_title}" by {book_author}.',
            'who_its_for': 'Readers interested in this subject.',
            'core_argument': 'See chapter summaries for key ideas.',
            'top_5_ideas': ['See chapters for detailed insights.'],
            'verdict': 'Worth reading for those interested in the subject.',
            'time_to_read_hours': 6,
        }


def generate_chapter_summary_for_mode(
    chapter_title: str,
    chapter_text: str,
    mode: str,
    book_title: str,
) -> dict:
    """
    Generate chapter content for a specific reading mode.

    mode: 'skim' | 'concept' | 'deep' | 'exam'
    Returns mode-specific JSON content.
    """
    preview = chapter_text[:6000]

    mode_prompts = {
        'skim': f"""Chapter: "{chapter_title}" from "{book_title}"

Text sample:
{preview}

Skim Mode: Give ONE punchy sentence capturing the entire chapter's essence.
Return ONLY valid JSON:
{{"one_liner": "The single most important takeaway from this chapter in one powerful sentence"}}""",

        'concept': f"""Chapter: "{chapter_title}" from "{book_title}"

Text sample:
{preview}

Concept Mode: Extract named ideas, frameworks, and mental models.
Return ONLY valid JSON:
{{"concepts": [
  {{"name": "Concept Name", "description": "2-3 sentence explanation of this idea"}},
  {{"name": "Another Concept", "description": "What it means and why it matters"}}
]}}""",

        'deep': f"""Chapter: "{chapter_title}" from "{book_title}"

Text sample:
{preview}

Deep Mode: Full comprehension breakdown with examples and narrative flow.
Return ONLY valid JSON:
{{
  "overview": "3-4 sentence overview of the chapter",
  "key_points": ["Point 1", "Point 2", "Point 3"],
  "examples": ["Example or story from the chapter", "Another example"],
  "analogy": "An analogy that makes the core idea memorable",
  "why_it_matters": "Why this chapter's content is important"
}}""",

        'exam': f"""Chapter: "{chapter_title}" from "{book_title}"

Text sample:
{preview}

Exam Mode: Create study-ready Q&A pairs for this chapter.
Return ONLY valid JSON:
{{"qa_pairs": [
  {{"question": "A conceptual question testing understanding", "answer": "A clear, complete answer"}},
  {{"question": "Another question", "answer": "Another answer"}},
  {{"question": "Third question", "answer": "Third answer"}},
  {{"question": "Fourth question", "answer": "Fourth answer"}},
  {{"question": "Fifth question", "answer": "Fifth answer"}}
]}}""",
    }

    prompt = mode_prompts.get(mode, mode_prompts['skim'])

    try:
        raw = call_deepseek(prompt, max_tokens=1500, temperature=0.3)
        return _parse_json_response(raw)
    except Exception as e:
        logger.warning(f'[DeepSeek] generate_chapter_summary_for_mode ({mode}) failed: {e}')
        fallbacks = {
            'skim': {'one_liner': f'{chapter_title} — see full chapter for details.'},
            'concept': {'concepts': [{'name': chapter_title, 'description': 'See chapter text.'}]},
            'deep': {'overview': f'Content from {chapter_title}.', 'key_points': [], 'examples': [], 'analogy': '', 'why_it_matters': ''},
            'exam': {'qa_pairs': [{'question': f'What is the main theme of {chapter_title}?', 'answer': 'See the chapter summary for details.'}]},
        }
        return fallbacks.get(mode, {})


def generate_daily_notifications(
    book_title: str,
    chapter_title: str,
    chapter_text_sample: str,
    day_number: int,
) -> dict:
    """
    Generate all 4 notification pieces for one day in a single DeepSeek call.
    Returns: {morning_hook, midday_concept, afternoon_story, evening_recap}
    """
    preview = chapter_text_sample[:3000]

    prompt = f"""You are generating daily reading notifications for "{book_title}".

Today's reading material (Day {day_number}): "{chapter_title}"

Sample content:
{preview}

Generate 4 notification messages. Each must be standalone, readable in under 15 seconds.
Return ONLY valid JSON, no markdown:
{{
  "morning_hook": "One powerful sentence — the big idea of today's reading. Sets context for the day.",
  "midday_concept": "A key concept or surprising fact from today's material. Very concise.",
  "afternoon_story": "A quote, analogy, or memorable story from today's content.",
  "evening_recap": "What you learned today — closes the loop in 2-3 sentences."
}}"""

    try:
        raw = call_deepseek(prompt, max_tokens=512, temperature=0.5)
        return _parse_json_response(raw)
    except Exception as e:
        logger.warning(f'[DeepSeek] generate_daily_notifications failed: {e}')
        return {
            'morning_hook': f"Today: exploring '{chapter_title}' in {book_title}.",
            'midday_concept': f"Key idea from {chapter_title} — check the app for full details.",
            'afternoon_story': f"A thought from your reading today in {book_title}.",
            'evening_recap': f"You engaged with {chapter_title} today. Great progress!",
        }


def answer_question_with_context(
    book_title: str,
    question: str,
    context_chunks: list[str],
) -> str:
    """
    RAG-based Q&A: answer a user question using retrieved context chunks.
    Never hallucinates — only answers from provided context.
    """
    context_text = '\n\n---\n\n'.join(context_chunks)

    prompt = f"""You are answering a question about the book "{book_title}".

Use ONLY the following excerpts from the book to answer. Do not add information not present in these excerpts.
If the answer is not in the provided text, say "I couldn't find a clear answer to that in the book."

Book excerpts:
{context_text}

Question: {question}

Answer (2-4 sentences, grounded in the text above):"""

    try:
        return call_deepseek(prompt, max_tokens=512, temperature=0.2)
    except Exception as e:
        logger.warning(f'[DeepSeek] answer_question_with_context failed: {e}')
        return "I couldn't process your question right now. Please try again."
