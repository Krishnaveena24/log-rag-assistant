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
