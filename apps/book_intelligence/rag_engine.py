"""
apps/book_intelligence/rag_engine.py

RAG (Retrieval-Augmented Generation) engine for Ask Your Book.

Embedding strategy:
  - Uses Google Gemini free embedding API (text-embedding-004, 768-dim)
  - Falls back to simple TF-IDF keyword matching if Gemini key missing
  - Cosine similarity computed in pure Python/numpy — no pgvector needed

Cost: $0 (Gemini free tier handles embeddings)
"""

import logging
import math
import json
from django.conf import settings

logger = logging.getLogger(__name__)


# ── Embedding ─────────────────────────────────────────────────────────────────

def get_embedding(text: str) -> list[float]:
    """
    Get text embedding using Google Gemini free API.
    Falls back to keyword-based vector if Gemini unavailable.
    """
    gemini_key = getattr(settings, 'GEMINI_API_KEY', '')

    if gemini_key:
        try:
            import google.generativeai as genai
            genai.configure(api_key=gemini_key)
            result = genai.embed_content(
                model='models/text-embedding-004',
                content=text,
                task_type='retrieval_document',
            )
            return result['embedding']
        except Exception as e:
            logger.warning(f'[RAG] Gemini embedding failed: {e} — using fallback')

    # Fallback: simple normalized bag-of-words vector (768-dim hash trick)
    return _keyword_vector(text)


def get_query_embedding(text: str) -> list[float]:
    """Embedding optimized for query (vs document)."""
    gemini_key = getattr(settings, 'GEMINI_API_KEY', '')

    if gemini_key:
        try:
            import google.generativeai as genai
            genai.configure(api_key=gemini_key)
            result = genai.embed_content(
                model='models/text-embedding-004',
                content=text,
                task_type='retrieval_query',
            )
            return result['embedding']
        except Exception as e:
            logger.warning(f'[RAG] Gemini query embedding failed: {e} — using fallback')

    return _keyword_vector(text)


def _keyword_vector(text: str, dims: int = 768) -> list[float]:
    """
    Simple hash-based bag-of-words vector. Used when Gemini is unavailable.
    Not as accurate as real embeddings but works for basic retrieval.
    """
    words = text.lower().split()
    vec = [0.0] * dims
    for word in words:
        idx = hash(word) % dims
        vec[idx] += 1.0
    # L2 normalize
    magnitude = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / magnitude for v in vec]


# ── Similarity ────────────────────────────────────────────────────────────────

def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """Pure Python cosine similarity between two equal-length vectors."""
    if len(vec_a) != len(vec_b):
        return 0.0
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    mag_a = math.sqrt(sum(a * a for a in vec_a)) or 1e-9
    mag_b = math.sqrt(sum(b * b for b in vec_b)) or 1e-9
    return dot / (mag_a * mag_b)


# ── RAG Retrieval ─────────────────────────────────────────────────────────────

def find_relevant_chunks(
    profile_id: str,
    question: str,
    top_k: int = 3,
) -> list[dict]:
    """
    Find the most relevant text chunks for a question using cosine similarity.

    Returns list of: {text, page_number, score}
    """
    from apps.book_intelligence.models import PageEmbedding

    embeddings = PageEmbedding.objects.filter(
        profile_id=profile_id
    ).values('id', 'text_content', 'page_number', 'embedding')

    if not embeddings:
        logger.warning(f'[RAG] No embeddings for profile {profile_id}')
        return []

    query_vec = get_query_embedding(question)

    scored = []
    for row in embeddings:
        stored_vec = row['embedding']
        if not stored_vec:
            continue
        score = cosine_similarity(query_vec, stored_vec)
        scored.append({
            'text': row['text_content'],
            'page_number': row['page_number'],
            'score': score,
        })

    scored.sort(key=lambda x: x['score'], reverse=True)
    return scored[:top_k]


def build_embeddings_for_book(profile_id: str, book_id: str):
    """
    Build and store embeddings for all chunks of a book.
    Called once per book after classification.
    """
    from apps.book_intelligence.models import BookIntelligenceProfile, PageEmbedding
    from apps.books.models import Chunk

    logger.info(f'[RAG] Building embeddings for profile {profile_id}')

    try:
        profile = BookIntelligenceProfile.objects.get(id=profile_id)
    except BookIntelligenceProfile.DoesNotExist:
        logger.error(f'[RAG] Profile {profile_id} not found')
        return

    # Delete old embeddings
    PageEmbedding.objects.filter(profile=profile).delete()

    # Get all chunks for this book
    chunks = Chunk.objects.filter(
        chapter__book_id=book_id
    ).select_related('chapter').order_by('chapter__chapter_number', 'chunk_index')

    created = 0
    for chunk in chunks:
        try:
            vec = get_embedding(chunk.text)
            PageEmbedding.objects.create(
                profile=profile,
                page_number=chunk.chapter.chapter_number,
                chunk_index=chunk.chunk_index,
                text_content=chunk.text[:1000],  # store first 1000 chars
                embedding=vec,
            )
            created += 1
        except Exception as e:
            logger.warning(f'[RAG] Failed to embed chunk {chunk.id}: {e}')

    profile.embeddings_built = True
    profile.save(update_fields=['embeddings_built'])

    logger.info(f'[RAG] ✅ Built {created} embeddings for "{profile.book.title}"')
