from unittest import TestCase

from apps.assistant import rag


class RagSearchTests(TestCase):
    def sources(self, query):
        return {c['source'].split('/')[0] for c in rag.search(query)}

    def test_vaccination_question_finds_vaccination_doc(self):
        self.assertIn('emlash', self.sources("Buzoqni qachon emlash kerak?"))

    def test_feed_question_finds_ration_doc(self):
        self.assertIn('yem_ratsion', self.sources("qo'yga qancha pichan beraman"))

    def test_disease_question_finds_veterinary_doc(self):
        self.assertIn('veterinariya', self.sources("mastit nima"))

    def test_apostrophe_variants_match(self):
        self.assertEqual(rag.tokenize("qo'y"), rag.tokenize("qoy"))
        self.assertEqual(rag.tokenize("qo`y"), rag.tokenize("qo‘y"))

    def test_empty_query_returns_nothing(self):
        self.assertEqual(rag.search(""), [])
        self.assertEqual(rag.build_knowledge_prompt([""]), '')

    def test_prompt_is_size_limited(self):
        prompt = rag.build_knowledge_prompt(["emlash va ratsion va veterinariya"])
        self.assertLessEqual(len(prompt), rag.MAX_CHARS + 1000)
