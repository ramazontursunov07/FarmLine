"""Bilimlar bazasi (RAG): knowledge/ papkasidagi .md hujjatlardan savolga mos bo'laklarni topadi.

Qidiruv -- oddiy BM25 (qo'shimcha kutubxona va tashqi API kerak emas). O'zbek tilida qo'shimchalar ko'p
(qoramol, qoramolni, qoramolning), shuning uchun so'zlar boshidagi STEM_LEN harfga qisqartirib solishtiriladi,
apostroflar olib tashlanadi (qo'y = qoy = qo`y).
"""
import math
import re
from functools import lru_cache
from pathlib import Path

KNOWLEDGE_DIR = Path(__file__).resolve().parents[2] / 'knowledge'

STEM_LEN = 6
TOP_K = 4
MAX_CHARS = 4500  # AI ga beriladigan bilim hajmi (token tejash uchun)
MAX_CHUNK_CHARS = 1500
MIN_SCORE = 2.0  # eng yaxshi bo'lak shu balldan past bo'lsa, savol bazaga aloqasiz deb olinadi
REL_SCORE = 0.4  # qolgan bo'laklar eng yaxshisining kamida shu ulushini olishi kerak

K1, B = 1.5, 0.75

STOPWORDS = {
    'va', 'bu', 'bilan', 'uchun', 'ham', 'yoki', 'nima', 'qanday', 'qachon', 'kerak', 'bo', 'bor', 'yoq',
    'men', 'mening', 'bizning', 'qilish', 'qilsa', 'nega', 'necha', 'haqida', 'menga', 'ayt', 'tushuntir',
}

HEADING = re.compile(r'^(#{1,4})\s+(.*)$')

# Eng ko'p uchraydigan o'zbekcha qo'shimchalar (uzundan qisqaga)
SUFFIXES = ('ning', 'lari', 'larni', 'lar', 'dan', 'ga', 'ka', 'qa', 'da', 'ni', 'si', 'ri', 'ki', 'ligi', 'lik')


def _stem(word):
    for _ in range(2):
        for suf in SUFFIXES:
            if word.endswith(suf) and len(word) - len(suf) >= 3:
                word = word[:-len(suf)]
                break
        else:
            break
    return word[:STEM_LEN]


def tokenize(text):
    text = text.lower()
    for ch in "ʻʼ’‘`´'":
        text = text.replace(ch, '')
    words = re.findall(r'[a-zа-яё0-9]+', text)
    return [_stem(w) for w in words if w not in STOPWORDS and len(w) > 1]


def split_markdown(text, source):
    """Sarlavhalar bo'yicha bo'laklarga ajratadi. Har bo'lak o'z sarlavha yo'lini saqlaydi."""
    chunks = []
    stack = []  # [(daraja, sarlavha)]
    body = []

    def flush():
        content = '\n'.join(body).strip()
        if content and stack:
            path = ' > '.join(t for _, t in stack[1:]) or stack[0][1]
            chunks.append({'source': source, 'doc': stack[0][1], 'title': path, 'text': content})
        body.clear()

    for line in text.splitlines():
        m = HEADING.match(line)
        if m:
            flush()
            level, title = len(m.group(1)), m.group(2).strip()
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, title))
        else:
            body.append(line)
    flush()
    return chunks


@lru_cache(maxsize=1)
def _index():
    chunks = []
    if KNOWLEDGE_DIR.is_dir():
        for path in sorted(KNOWLEDGE_DIR.rglob('*.md')):
            rel = path.relative_to(KNOWLEDGE_DIR).as_posix()
            chunks.extend(split_markdown(path.read_text(encoding='utf-8'), rel))
    docs = []
    df = {}
    for c in chunks:
        # sarlavha va hujjat nomi ikki marta: sarlavhadagi moslik muhimroq
        tokens = tokenize(c['doc']) + tokenize(c['title']) * 2 + tokenize(c['text'])
        tf = {}
        for t in tokens:
            tf[t] = tf.get(t, 0) + 1
        docs.append((c, tf, len(tokens)))
        for t in tf:
            df[t] = df.get(t, 0) + 1
    avg = (sum(n for _, _, n in docs) / len(docs)) if docs else 0
    return docs, df, avg


def search(query, k=TOP_K):
    docs, df, avg = _index()
    q = set(tokenize(query))
    if not docs or not q:
        return []
    n = len(docs)
    scored = []
    for chunk, tf, length in docs:
        score = 0.0
        for t in q:
            f = tf.get(t)
            if not f:
                continue
            idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
            score += idf * f * (K1 + 1) / (f + K1 * (1 - B + B * length / avg))
        if score > 0:
            scored.append((score, chunk))
    scored.sort(key=lambda x: -x[0])
    if not scored or scored[0][0] < MIN_SCORE:
        return []
    top = scored[0][0]
    return [c for sc, c in scored[:k] if sc >= top * REL_SCORE]


def build_knowledge_prompt(queries):
    """queries -- foydalanuvchining oxirgi savol(lar)i. Mos bo'lak topilmasa, bo'sh matn qaytaradi."""
    found = search(' '.join(queries))
    if not found:
        return ''
    parts, total = [], 0
    for c in found:
        text = c['text'][:MAX_CHUNK_CHARS]
        block = f"[{c['doc']} / {c['title']}]\n{text}"
        if total + len(block) > MAX_CHARS:
            break
        parts.append(block)
        total += len(block)
    return (
            "Bilimlar bazasi (emlash, veterinariya, yem ratsioni, qonun hujjatlaridan olingan ma'lumot). "
            "Foydalanuvchi savoli shu mavzularga oid bo'lsa, javobni shu ma'lumotga tayanib ber. "
            "Baza savolga yetmasa, buni ayt, o'zingdan aniq doza yoki raqam o'ylab topma. "
            "Kasallik shubhasi yoki og'ir holatda veterinarga murojaat qilishni tavsiya qil.\n\n"
            + "\n\n".join(parts)
    )
