"""Matnni vektorga aylantirish (Gemini embedding).

LangChain `Embeddings` interfeysi bilan yozilgan: keyinchalik istalgan LangChain vektor bazasi yoki retriever
shu klassni o'zgartirishsiz ishlata oladi. Ichida esa loyihada allaqachon bor `google-genai` kutubxonasi ishlaydi
(`langchain-google-genai` va uning og'ir bog'liqliklari kerak emas, bepul serverda xotira tejaladi).

GEMINI_API_KEY bo'lmasa yoki Gemini javob bermasa EmbeddingError ko'tariladi; qidiruv shunda oddiy kalit so'z
(BM25) qidiruviga qaytadi, ya'ni AI yordamchi ishlashda davom etadi.
"""
from django.conf import settings
from langchain_core.embeddings import Embeddings

MODEL = 'gemini-embedding-001'
# 768 -- Google tavsiya qiladigan ixcham o'lcham. Bu raqam models.KnowledgeChunk.embedding va 0002 migratsiyadagi bilan bir xil bo'lishi shart
DIMENSIONS = 768
# Bazadagi vektor qaysi model va o'lchamda hisoblangani. O'zgarsa, eski vektorlar qayta hisoblanadi
EMBED_TAG = f'{MODEL}:{DIMENSIONS}'

BATCH_SIZE = 50  # Gemini bir so'rovda ko'p matnni qabul qiladi; 50 tadan yuboramiz
QUERY_TIMEOUT_MS = 5000  # savol vektori: sekin bo'lsa kutib o'tirmaymiz, BM25 ga qaytamiz
INDEX_TIMEOUT_MS = 60000  # indeksni yangilash: shoshilinch emas
MAX_QUERY_CHARS = 2000


class EmbeddingError(Exception):
    """Vektorni olib bo'lmadi (kalit yo'q, tarmoq, limit va h.k.)."""


class GeminiEmbeddings(Embeddings):
    def __init__(self, timeout_ms=QUERY_TIMEOUT_MS):
        self.timeout_ms = timeout_ms
        self._client = None

    def _get_client(self):
        if self._client is None:
            api_key = getattr(settings, 'GEMINI_API_KEY', None)
            if not api_key:
                raise EmbeddingError("GEMINI_API_KEY berilmagan")
            from google import genai
            from google.genai import types

            self._client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=self.timeout_ms))
        return self._client

    def _embed(self, texts, task_type):
        from google.genai import types

        client = self._get_client()
        vectors = []
        for start in range(0, len(texts), BATCH_SIZE):
            batch = texts[start:start + BATCH_SIZE]
            try:
                response = client.models.embed_content(
                    model=MODEL,
                    contents=batch,
                    config=types.EmbedContentConfig(task_type=task_type, output_dimensionality=DIMENSIONS),
                )
            except Exception as exc:  # noqa: BLE001 - tarmoq, limit, kalit xatosi: hammasi EmbeddingError
                raise EmbeddingError(str(exc)) from exc
            part = [list(item.values) for item in (response.embeddings or [])]
            if len(part) != len(batch) or any(len(v) != DIMENSIONS for v in part):
                raise EmbeddingError("Gemini kutilmagan o'lchamdagi vektor qaytardi")
            vectors.extend(part)
        return vectors

    def embed_documents(self, texts):
        texts = list(texts)
        return self._embed(texts, 'RETRIEVAL_DOCUMENT') if texts else []

    def embed_query(self, text):
        return self._embed([text[:MAX_QUERY_CHARS]], 'RETRIEVAL_QUERY')[0]
    