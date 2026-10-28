"""Small, dependency-free helpers for retrieval: chunk a log file and rank chunks.

Kept separate from handler.py so they can be unit tested without AWS.
"""


def chunk_lines(text, size=15, overlap=3):
    """Split log text into overlapping chunks of `size` non-empty lines."""
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return []
    step = max(size - overlap, 1)
    chunks = []
    for start in range(0, len(lines), step):
        chunks.append("\n".join(lines[start:start + size]))
        if start + size >= len(lines):
            break
    return chunks


def dot(a, b):
    """Dot product. Titan embeddings are normalized, so this equals cosine similarity."""
    return sum(x * y for x, y in zip(a, b))


def top_k(query_vector, index, k=3):
    """Return the k chunk texts most similar to the query.

    index is a list of (chunk_text, embedding) pairs.
    """
    ranked = sorted(index, key=lambda item: dot(query_vector, item[1]), reverse=True)
    return [text for text, _ in ranked[:k]]


def _tokens(text):
    cleaned = "".join(ch.lower() if ch.isalnum() else " " for ch in text)
    # Cut words to 5 letters as a simple stem: "reconciliation", "reconciled" -> "recon"
    return [t[:5] for t in cleaned.split() if len(t) > 1]


def keyword_top_k(question, chunks, k=3):
    """Fallback retrieval without embeddings: rank chunks by shared words.

    Rare words (found in few chunks) count more than common ones, like a simple TF-IDF.
    """
    import math

    chunk_tokens = [set(_tokens(c)) for c in chunks]
    n = len(chunks)

    def weight(word):
        found_in = sum(1 for tokens in chunk_tokens if word in tokens)
        return math.log((n + 1) / (found_in + 1)) + 1 if found_in else 0

    q_words = set(_tokens(question))
    scores = [sum(weight(w) for w in q_words if w in tokens) for tokens in chunk_tokens]
    ranked = sorted(range(n), key=lambda i: scores[i], reverse=True)
    return [chunks[i] for i in ranked[:k]]
