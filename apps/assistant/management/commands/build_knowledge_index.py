"""Bilimlar bazasi (knowledge/*.md) vektorlarini pgvector da yangilaydi.

Faqat yangi yoki o'zgargan bo'laklar Gemini orqali qayta hisoblanadi, shuning uchun har ishga tushirishda
chaqirish arzon (start.sh shunday qiladi). PostgreSQL yoki GEMINI_API_KEY bo'lmasa, hech narsa qilmaydi va xato bermaydi.
"""
from django.core.management.base import BaseCommand, CommandError

from apps.assistant import rag, vector_store
from apps.assistant.embeddings import EmbeddingError


class Command(BaseCommand):
    help = "Bilimlar bazasi vektorlarini (pgvector) fayllarga moslab yangilaydi"

    def add_arguments(self, parser):
        parser.add_argument('--force', action='store_true', help="Hamma bo'lakni qaytadan hisoblash")

    def handle(self, *args, **options):
        reason = vector_store.disabled_reason()
        if reason:
            self.stdout.write(f"Vektor indeks yangilanmadi: {reason}. Qidiruv oddiy (BM25) rejimda ishlaydi.")
            return
        chunks = rag.load_chunks()
        try:
            stats = vector_store.sync_index(chunks, force=options['force'])
        except EmbeddingError as exc:
            raise CommandError(f"Gemini embedding xatosi: {exc}") from exc
        self.stdout.write(self.style.SUCCESS(
            f"Bilimlar indeksi tayyor: {len(chunks)} ta bo'lak "
            f"(yangi {stats['added']}, o'zgarmagan {stats['kept']}, olib tashlangan {stats['removed']})."
        ))
        