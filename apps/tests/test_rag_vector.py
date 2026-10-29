"""Bilimlar bazasi: bo'laklash, vektor indeksni yangilash va hybrid qidiruv.

Gemini ga murojaat qilinmaydi: o'rniga so'zlar sumkasi (bag-of-words) asosidagi soxta embedding ishlatiladi.
Indeksni yangilash SQLite da ham sinaladi; pgvector ning o'zi (<=> qidiruvi) faqat PostgreSQL da sinaladi.
"""
import hashlib
from unittest import skipUnless
from unittest.mock import patch

from django.db import connection
from django.test import SimpleTestCase, TestCase, override_settings

from apps.assistant import rag, vector_store
from apps.assistant.embeddings import DIMENSIONS, EMBED_TAG, EmbeddingError
from apps.assistant.models import KnowledgeChunk


class FakeEmbeddings:
    """Gemini o'rnida: umumiy so'zlari ko'p matnlar o'xshash vektor beradi."""

    def __init__(self):
        self.calls = 0  # embed_documents orqali hisoblangan matnlar soni

    @staticmethod
    def vector(text):
        vec = [0.0] * DIMENSIONS
        for token in rag.tokenize(text):
            vec[int(hashlib.md5(token.encode()).hexdigest(), 16) % DIMENSIONS] += 1.0
        return vec

    def embed_documents(self, texts):
        self.calls += len(texts)
        return [self.vector(t) for t in texts]

    def embed_query(self, text):
        return self.vector(text)


class FailingEmbeddings:
    def embed_documents(self, texts):
        raise EmbeddingError("limit tugadi")


class ChunkTests(SimpleTestCase):
    def test_long_blocks_are_split_not_truncated(self):
        chunks = rag.load_chunks()
        self.assertTrue(chunks)
        self.assertTrue(all(len(c['text']) <= rag.MAX_CHUNK_CHARS for c in chunks))

    def test_keys_are_unique_and_stable(self):
        first, second = rag.load_chunks(), rag.load_chunks()
        keys = [c['key'] for c in first]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual(keys, [c['key'] for c in second])

    def test_changed_text_changes_key(self):
        chunk = {'source': 'a.md', 'title': 'b', 'text': 'x'}
        self.assertNotEqual(rag.chunk_key(chunk), rag.chunk_key({**chunk, 'text': 'y'}))

    def test_model_dimensions_match_embedding_dimensions(self):
        self.assertEqual(KnowledgeChunk._meta.get_field('embedding').dimensions, DIMENSIONS)


class FuseTests(SimpleTestCase):
    def test_chunk_found_by_both_searches_goes_first(self):
        a, b, c = {'key': 'a'}, {'key': 'b'}, {'key': 'c'}
        self.assertEqual([x['key'] for x in rag.fuse([a, b], [c, b], 3)], ['b', 'a', 'c'])

    def test_limit_is_respected(self):
        a, b, c = {'key': 'a'}, {'key': 'b'}, {'key': 'c'}
        self.assertEqual([x['key'] for x in rag.fuse([a, b], [c, b], 1)], ['b'])


class VectorSwitchTests(SimpleTestCase):
    @override_settings(GEMINI_API_KEY=None)
    def test_off_without_api_key(self):
        self.assertIn('GEMINI_API_KEY', vector_store.disabled_reason())
        self.assertFalse(vector_store.vector_enabled())

    @override_settings(GEMINI_API_KEY='kalit', RAG_VECTOR_SEARCH=False)
    def test_can_be_switched_off(self):
        self.assertIn('RAG_VECTOR_SEARCH', vector_store.disabled_reason())

    @skipUnless(connection.vendor != 'postgresql', "bu test PostgreSQL emas bazada ishlaydi")
    @override_settings(GEMINI_API_KEY='kalit', RAG_VECTOR_SEARCH=True)
    def test_off_when_database_is_not_postgres(self):
        self.assertIn('PostgreSQL', vector_store.disabled_reason())


class SyncIndexTests(TestCase):
    def setUp(self):
        self.chunks = rag.load_chunks()[:6]
        self.fake = FakeEmbeddings()

    def test_second_sync_computes_nothing(self):
        self.assertEqual(vector_store.sync_index(self.chunks, self.fake), {'added': 6, 'removed': 0, 'kept': 0})
        self.assertEqual(vector_store.sync_index(self.chunks, self.fake), {'added': 0, 'removed': 0, 'kept': 6})
        self.assertEqual(self.fake.calls, 6)
        self.assertEqual(KnowledgeChunk.objects.count(), 6)

    def test_only_changed_chunk_is_recomputed(self):
        vector_store.sync_index(self.chunks, self.fake)
        changed = dict(self.chunks[0], text=self.chunks[0]['text'] + ' Yangi gap.')
        changed['key'] = rag.chunk_key(changed)
        stats = vector_store.sync_index([changed] + self.chunks[1:], self.fake)
        self.assertEqual(stats, {'added': 1, 'removed': 1, 'kept': 5})
        self.assertEqual(self.fake.calls, 7)

    def test_chunks_missing_from_files_are_removed(self):
        vector_store.sync_index(self.chunks, self.fake)
        stats = vector_store.sync_index(self.chunks[:4], self.fake)
        self.assertEqual(stats, {'added': 0, 'removed': 2, 'kept': 4})

    def test_vectors_of_another_model_are_replaced(self):
        vector_store.sync_index(self.chunks, self.fake)
        KnowledgeChunk.objects.update(embed_model='eski-model:3072')
        stats = vector_store.sync_index(self.chunks, self.fake)
        self.assertEqual(stats, {'added': 6, 'removed': 6, 'kept': 0})
        self.assertEqual(set(KnowledgeChunk.objects.values_list('embed_model', flat=True)), {EMBED_TAG})

    def test_force_recomputes_everything(self):
        vector_store.sync_index(self.chunks, self.fake)
        stats = vector_store.sync_index(self.chunks, self.fake, force=True)
        self.assertEqual(stats, {'added': 6, 'removed': 6, 'kept': 0})

    def test_vector_survives_database_roundtrip(self):
        vector_store.sync_index(self.chunks, self.fake)
        row = KnowledgeChunk.objects.get(key=self.chunks[2]['key'])
        self.assertEqual(len(row.embedding), DIMENSIONS)
        self.assertEqual(row.embedding, self.fake.vector(vector_store.embedding_text(self.chunks[2])))

    def test_failed_embedding_leaves_existing_index_untouched(self):
        vector_store.sync_index(self.chunks, self.fake)
        changed = dict(self.chunks[0], text='boshqa matn')
        changed['key'] = rag.chunk_key(changed)
        with self.assertRaises(EmbeddingError):
            vector_store.sync_index([changed] + self.chunks[1:], FailingEmbeddings())
        self.assertEqual(KnowledgeChunk.objects.count(), 6)
        self.assertTrue(KnowledgeChunk.objects.filter(key=self.chunks[0]['key']).exists())


class HybridSearchTests(TestCase):
    QUERY = "mastit nima"

    def test_semantic_hit_is_added_to_keyword_results(self):
        target = next(c for c in rag.load_chunks() if c['source'].startswith('qonun_qoidalar'))
        best_keyword = rag.bm25_search(self.QUERY)[0]['key']
        with patch('apps.assistant.vector_store.vector_enabled', return_value=True), \
                patch('apps.assistant.vector_store.search', return_value=[(target['key'], 0.9)]):
            keys = [c['key'] for c in rag.search(self.QUERY)]
        self.assertIn(target['key'], keys)
        self.assertIn(best_keyword, keys)

    def test_embedding_failure_falls_back_to_keyword_search(self):
        expected = [c['key'] for c in rag.bm25_search(self.QUERY, rag.TOP_K)]
        with patch('apps.assistant.vector_store.vector_enabled', return_value=True), \
                patch('apps.assistant.vector_store.search', side_effect=EmbeddingError("limit")):
            with self.assertLogs('apps.assistant.rag', level='WARNING'):
                found = rag.search(self.QUERY)
        self.assertEqual([c['key'] for c in found], expected)

    def test_vector_search_disabled_gives_plain_keyword_results(self):
        with patch('apps.assistant.vector_store.vector_enabled', return_value=False), \
                patch('apps.assistant.vector_store.search') as search:
            found = rag.search(self.QUERY)
        search.assert_not_called()
        self.assertEqual([c['key'] for c in found], [c['key'] for c in rag.bm25_search(self.QUERY, rag.TOP_K)])

    def test_blank_question_never_reaches_gemini(self):
        with patch('apps.assistant.vector_store.search') as search:
            self.assertEqual(rag.search('   '), [])
        search.assert_not_called()


@skipUnless(connection.vendor == 'postgresql', "pgvector faqat PostgreSQL da ishlaydi")
class PgvectorTests(TestCase):
    def setUp(self):
        self.chunks = rag.load_chunks()[:12]
        self.fake = FakeEmbeddings()
        vector_store.sync_index(self.chunks, self.fake)

    def test_nearest_returns_the_identical_text_first(self):
        target = self.chunks[5]
        hits = vector_store.nearest(self.fake.embed_query(vector_store.embedding_text(target)), 3)
        self.assertEqual(hits[0][0], target['key'])
        self.assertAlmostEqual(hits[0][1], 1.0, places=4)

    @override_settings(RAG_MIN_SIMILARITY=0.999)
    def test_weak_matches_are_filtered_by_threshold(self):
        target = self.chunks[2]
        hits = vector_store.search(vector_store.embedding_text(target), 5, embedder=self.fake)
        self.assertEqual([key for key, _ in hits], [target['key']])

    @override_settings(GEMINI_API_KEY='kalit', RAG_VECTOR_SEARCH=True, RAG_MIN_SIMILARITY=0.2)
    def test_rag_search_goes_through_pgvector(self):
        with patch('apps.assistant.vector_store.GeminiEmbeddings', return_value=self.fake), \
                patch.object(vector_store, 'nearest', wraps=vector_store.nearest) as spy:
            found = rag.search("mastit nima")
        spy.assert_called_once()
        self.assertTrue(found)
