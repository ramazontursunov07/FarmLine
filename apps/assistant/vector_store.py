"""Bilim bo'laklari vektorlarini pgvector da saqlash va savolga ma'nosi yaqinlarini topish.

Faqat PostgreSQL + pgvector da ishlaydi (vector_enabled). Boshqa holatlarda qidiruv oddiy BM25 bilan davom etadi.
"""
import json

from django.conf import settings
from django.db import connection, transaction

from .embeddings import EMBED_TAG, INDEX_TIMEOUT_MS, GeminiEmbeddings
from .models import KnowledgeChunk

# Savol bilan bo'lak orasidagi kosinus o'xshashligi shundan past bo'lsa, bo'lak aloqasiz hisoblanadi.
# Real savollar bilan sinab sozlang: python manage.py knowledge_search "savol"
DEFAULT_MIN_SIMILARITY = 0.60


def disabled_reason():
    """Vektor qidiruv nega o'chiq ekani (yoqilgan bo'lsa None)."""
    if not getattr(settings, 'RAG_VECTOR_SEARCH', True):
        return "RAG_VECTOR_SEARCH=0 (o'chirib qo'yilgan)"
    if not getattr(settings, 'GEMINI_API_KEY', None):
        return "GEMINI_API_KEY berilmagan"
    if connection.vendor != 'postgresql':
        return f"baza PostgreSQL emas ({connection.vendor}); pgvector faqat PostgreSQL da ishlaydi"
    return None


def vector_enabled():
    return disabled_reason() is None


def embedding_text(chunk):
    """Vektorga aylantiriladigan matn: hujjat va sarlavha ma'noni aniqlashtiradi."""
    return f"{chunk['doc']} / {chunk['title']}\n{chunk['text']}"


def sync_index(chunks, embedder=None, force=False):
    """Bazadagi vektorlarni fayllardagi bo'laklarga moslaydi.

    Faqat yangi yoki o'zgargan bo'laklar Gemini orqali qayta hisoblanadi; fayldan o'chirilganlari yoki boshqa
    model/o'lchamda hisoblanganlari bazadan olib tashlanadi. Avval hamma vektor olinadi, keyin bazaga yoziladi,
    shuning uchun Gemini xato bersa indeks buzilmaydi.
    """
    wanted = {c['key']: c for c in chunks}
    existing = set()
    if not force:
        existing = set(KnowledgeChunk.objects.filter(embed_model=EMBED_TAG).values_list('key', flat=True))
    keep = existing & set(wanted)
    new_keys = [key for key in wanted if key not in keep]

    vectors = []
    if new_keys:
        embedder = embedder or GeminiEmbeddings(timeout_ms=INDEX_TIMEOUT_MS)
        vectors = embedder.embed_documents([embedding_text(wanted[key]) for key in new_keys])

    with transaction.atomic():
        removed = KnowledgeChunk.objects.exclude(key__in=list(keep)).delete()[0]
        KnowledgeChunk.objects.bulk_create([
            KnowledgeChunk(
                key=key, source=wanted[key]['source'], title=wanted[key]['title'],
                embedding=vector, embed_model=EMBED_TAG,
            )
            for key, vector in zip(new_keys, vectors)
        ])
    return {'added': len(new_keys), 'removed': removed, 'kept': len(keep)}


def nearest(vector, k):
    """[(kalit, o'xshashlik)] -- eng yaqin k ta bo'lak. O'xshashlik = 1 - kosinus masofa (1 ga yaqin = juda o'xshash)."""
    if connection.vendor != 'postgresql':
        return []
    literal = json.dumps([float(x) for x in vector], separators=(',', ':'))
    quote = connection.ops.quote_name
    table, key_col, vec_col, model_col = (
        quote(KnowledgeChunk._meta.db_table), quote('key'), quote('embedding'), quote('embed_model'))
    with connection.cursor() as cursor:
        cursor.execute(
            f'SELECT {key_col}, 1 - ({vec_col} <=> %s::vector) FROM {table} WHERE {model_col} = %s '
            f'ORDER BY {vec_col} <=> %s::vector LIMIT %s',
            [literal, EMBED_TAG, literal, k],
        )
        return [(key, float(similarity)) for key, similarity in cursor.fetchall()]


def search(query, k, embedder=None):
    """[(kalit, o'xshashlik)] -- savolga ma'nosi yaqin va o'xshashlik chegarasidan o'tgan bo'laklar."""
    if not KnowledgeChunk.objects.filter(embed_model=EMBED_TAG).exists():
        return []  # indeks hali qurilmagan: Gemini ga bekorga murojaat qilmaymiz
    embedder = embedder or GeminiEmbeddings()
    threshold = float(getattr(settings, 'RAG_MIN_SIMILARITY', DEFAULT_MIN_SIMILARITY))
    return [(key, sim) for key, sim in nearest(embedder.embed_query(query), k) if sim >= threshold]
