"""Bitta savol uchun bilimlar bazasi qidiruvi qanday ishlayotganini ko'rsatadi.

RAG_MIN_SIMILARITY chegarasini sozlash uchun: avval bazaga tegishli savollarni, keyin aloqasiz savollarni
(masalan "bugun ob-havo qanday") sinab ko'ring va o'xshashlik ballarini solishtiring. Chegara ikkalasining orasida bo'lsin.

    python manage.py knowledge_search "sigirim ovqat yemayapti"
"""
from django.conf import settings
from django.core.management.base import BaseCommand

from apps.assistant import rag, vector_store
from apps.assistant.embeddings import EMBED_TAG, EmbeddingError, GeminiEmbeddings
from apps.assistant.models import KnowledgeChunk


class Command(BaseCommand):
    help = "Savol uchun BM25 va vektor qidiruv natijalarini ballari bilan ko'rsatadi"

    def add_arguments(self, parser):
        parser.add_argument('query', nargs='+', help="Savol matni")

    def handle(self, *args, **options):
        query = ' '.join(options['query'])
        by_key = {c['key']: c for c in rag.load_chunks()}
        label = lambda c: f"{c['doc']} / {c['title']}"[:90]  # noqa: E731

        self.stdout.write(f"\nSavol: {query}\n")
        self.stdout.write(f"== BM25 (kalit so'z); chegara: {rag.MIN_SCORE} ball")
        for score, chunk in rag.bm25_scored(query)[:5]:
            self.stdout.write(f"  {score:6.2f}  {label(chunk)}")

        threshold = float(getattr(settings, 'RAG_MIN_SIMILARITY', vector_store.DEFAULT_MIN_SIMILARITY))
        self.stdout.write(f"\n== Vektor (ma'no); chegara: {threshold} o'xshashlik")
        reason = vector_store.disabled_reason()
        if reason:
            self.stdout.write(f"  o'chiq: {reason}")
        elif not KnowledgeChunk.objects.filter(embed_model=EMBED_TAG).exists():
            self.stdout.write("  indeks hali qurilmagan: avval `python manage.py build_knowledge_index`")
        else:
            try:
                hits = vector_store.nearest(GeminiEmbeddings().embed_query(query), 6)
            except EmbeddingError as exc:
                self.stdout.write(f"  Gemini xatosi: {exc}")
            else:
                for key, similarity in hits:
                    mark = '+' if similarity >= threshold else '-'
                    chunk = by_key.get(key)
                    title = label(chunk) if chunk else "(fayldan o'chirilgan bo'lak)"
                    self.stdout.write(f"  {mark} {similarity:.3f}  {title}")

        self.stdout.write("\n== AI ga beriladigan yakuniy bo'laklar")
        for chunk in rag.search(query):
            self.stdout.write(f"  {label(chunk)}")
        self.stdout.write("")
        