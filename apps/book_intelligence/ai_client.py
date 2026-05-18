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


def detect_chapter_boundaries(page_signals: str, total_pages: int, book_title: str) -> list[dict]:
    """
    Path C AI fallback: detect chapter structure from compact page signals.
    Input: ~1,500 words (every 8th page, first 3 lines each) — respects 8k word rule.
    Returns: list of {chapter_number, title, start_page, end_page}
    """
    prompt = f"""You are detecting chapter boundaries in "{book_title}" ({total_pages} pages total).

Below is a page-signal summary — first 3 lines of every 8th page:
{page_signals}

Identify chapter boundaries from headings, "Chapter N" patterns, or major topic shifts.
Rules:
- end_page of chapter N = start_page of chapter N+1 minus 1.
- end_page of the last chapter = {total_pages}.
- Skip front matter (copyright, dedication, TOC).
- Return [] if you cannot confidently identify chapters.

Return ONLY a valid JSON array, no markdown:
[
  {{"chapter_number": 1, "title": "Descriptive Chapter Title", "start_page": 12, "end_page": 34}},
  {{"chapter_number": 2, "title": "Another Real Title", "start_page": 35, "end_page": 67}}
]"""

    try:
        raw = call_deepseek(prompt, max_tokens=1024, temperature=0.1)
        result = _parse_json_response(raw)
        if isinstance(result, list) and len(result) > 0:
            for ch in result:
                if 'start_page' not in ch or 'end_page' not in ch:
                    return []
            return result
        return []
    except Exception as e:
        logger.warning(f'[DeepSeek] detect_chapter_boundaries failed: {e}')
        return []


def generate_book_brief(
    book_title: str,
    book_author: str,
    chapter_openings: list[dict],
) -> dict:
    """
    Generate the Book Brief from chapter titles + first 150 words of each chapter.
    Input size: ~800 words max for 10 chapters — well within 8k limit.
    chapter_openings: list of {title: str, opening: str (first 150 words)}
    Returns: {what_its_about, who_its_for, core_argument, top_5_ideas, verdict, time_to_read_hours}
    """
    chapters_text = '\n\n'.join(
        f'Chapter {i+1}: {ch["title"]}\n{ch["opening"][:600]}'
        for i, ch in enumerate(chapter_openings[:12])
    )

    prompt = f"""You are creating a Book Brief for "{book_title}" by {book_author}.

Chapter titles and opening paragraphs:
{chapters_text}

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


def synthesise_section_summaries(
    section_summaries: list[str],
    mode: str,
    chapter_title: str,
    book_title: str,
) -> dict:
    """
    Synthesise multiple section summaries into one final chapter summary.
    Used when a chapter exceeds 8,000 words (split into 6,000-word sections).
    Input: list of per-section summaries — always short, never exceeds 8k.
    """
    combined = '\n\n'.join(
        f'Section {i+1}:\n{s}' for i, s in enumerate(section_summaries)
    )

    mode_instructions = {
        'skim': 'Synthesise into ONE punchy one-liner capturing the entire chapter.',
        'concept': 'Synthesise all section concepts into a unified concept map.',
        'deep': 'Synthesise into a cohesive overview, key points, examples, and analogy.',
        'exam': 'Synthesise all Q&A pairs, keeping only the best 5.',
    }
    instruction = mode_instructions.get(mode, mode_instructions['deep'])

    mode_schema = {
        'skim': '{"one_liner": "The single most important takeaway from this chapter"}',
        'concept': '{"concepts": [{"name": "Concept Name", "description": "2-3 sentence explanation"}]}',
        'deep': '{"overview": "3-4 sentence overview", "key_points": ["Point 1", "Point 2"], "examples": ["Example 1"], "analogy": "A memorable analogy", "why_it_matters": "Why this matters"}',
        'exam': '{"qa_pairs": [{"question": "Question", "answer": "Answer"}]}',
    }
    schema = mode_schema.get(mode, mode_schema['deep'])

    prompt = f"""You are synthesising section summaries for chapter "{chapter_title}" from "{book_title}".

{instruction}

Section summaries:
{combined}

Return ONLY valid JSON matching this schema, no markdown:
{schema}"""

    try:
        raw = call_deepseek(prompt, max_tokens=1024, temperature=0.3)
        return _parse_json_response(raw)
    except Exception as e:
        logger.warning(f'[DeepSeek] synthesise_section_summaries ({mode}) failed: {e}')
        return {}


def _words_to_chars(text: str, max_words: int = 6000) -> str:
    """Return text truncated to max_words words (rough char estimate for speed)."""
    words = text.split()
    if len(words) <= max_words:
        return text
    return ' '.join(words[:max_words])


def generate_chapter_summary_for_mode(
    chapter_title: str,
    chapter_text: str,
    mode: str,
    book_title: str,
) -> dict:
    """
    Generate chapter content for a specific reading mode.
    ENFORCES 8,000-word limit: caller is responsible for splitting longer chapters.
    Each call receives at most 6,000 words of chapter text.

    mode: 'skim' | 'concept' | 'deep' | 'exam'
    Returns mode-specific JSON content.
    """
    preview = _words_to_chars(chapter_text, max_words=6000)

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
    conversation_history: list[dict] | None = None,
) -> str:
    """
    RAG-based Q&A: answer using retrieved context + last 3 conversation exchanges.
    Input capped at 3 context chunks (top_k=3) + 3 history turns — always within 8k.
    Never hallucinates — only answers from provided context.
    """
    context_text = '\n\n---\n\n'.join(context_chunks[:3])

    history_text = ''
    if conversation_history:
        history_lines = []
        for exchange in list(conversation_history)[-3:]:
            history_lines.append(f'User: {exchange.get("question", "")}')
            history_lines.append(f'Assistant: {exchange.get("answer", "")}')
        if history_lines:
            history_text = '\n\nPrevious exchanges:\n' + '\n'.join(history_lines)

    prompt = f"""You are answering a question about the book "{book_title}".

Use ONLY the following excerpts from the book to answer. Do not add information not present in these excerpts.
If the answer is not in the provided text, say "I couldn't find a clear answer to that in the book."{history_text}

Book excerpts:
{context_text}

Question: {question}

Answer (2-4 sentences, grounded in the text above):"""

    try:
        return call_deepseek(prompt, max_tokens=512, temperature=0.2)
    except Exception as e:
        logger.warning(f'[DeepSeek] answer_question_with_context failed: {e}')
        return "I couldn't process your question right now. Please try again."
