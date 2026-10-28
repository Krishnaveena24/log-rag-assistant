"""Log RAG assistant: answers questions about a log file stored in S3.

Flow: load log from S3 -> split into chunks -> embed chunks (Titan) ->
embed the question -> pick the closest chunks -> ask the LLM (Amazon Nova)
to answer using only those chunks.
"""
import json
import os
import time

import boto3  # already included in the AWS Lambda Python runtime
from botocore.config import Config
from botocore.exceptions import ClientError

from rag import chunk_lines, keyword_top_k, top_k

s3 = boto3.client("s3")
# Embeddings: give up fast when throttled, so the keyword fallback kicks in quickly.
bedrock_embed = boto3.client(
    "bedrock-runtime",
    config=Config(retries={"max_attempts": 2, "mode": "standard"}, read_timeout=20),
)
# Answer model: be patient; "adaptive" retries slow down when Bedrock throttles.
bedrock_chat = boto3.client(
    "bedrock-runtime",
    config=Config(retries={"max_attempts": 3, "mode": "adaptive"}, read_timeout=60),
)

LOG_BUCKET = os.environ["LOG_BUCKET"]
DEFAULT_LOG_KEY = os.environ.get("LOG_KEY", "logs/app.log")
CHAT_MODEL_ID = os.environ.get("CHAT_MODEL_ID", "apac.amazon.nova-lite-v1:0")
EMBED_MODEL_ID = os.environ.get("EMBED_MODEL_ID", "amazon.titan-embed-text-v2:0")
TOP_K = int(os.environ.get("TOP_K", "3"))
MAX_QUESTION_CHARS = 500

SYSTEM_PROMPT = (
    "You are a site reliability assistant. Answer the question using ONLY the "
    "log excerpts provided. Quote timestamps and service names from the logs. "
    "Structure the answer as: What happened, Root cause, What fixed it. "
    "If the excerpts do not contain the answer, say "
    "'I could not find this in the logs.' Do not guess."
)

# Embeddings are cached while the Lambda stays warm, keyed by the file's ETag,
# so the log is only re-embedded when the file changes.
_cache = {}


def embed(text):
    response = bedrock_embed.invoke_model(
        modelId=EMBED_MODEL_ID,
        contentType="application/json",
        accept="application/json",
        body=json.dumps({"inputText": text, "dimensions": 256, "normalize": True}),
    )
    return json.loads(response["body"].read())["embedding"]


def is_throttled(error):
    return error.response.get("Error", {}).get("Code") == "ThrottlingException"


def load_chunks(key):
    obj = s3.get_object(Bucket=LOG_BUCKET, Key=key)
    text = obj["Body"].read().decode("utf-8", errors="replace")
    return (key, obj["ETag"]), chunk_lines(text)


def load_index(cache_key, chunks):
    """Embed every chunk once and cache it. Pauses between calls to stay under rate limits."""
    if cache_key not in _cache:
        index = []
        for chunk in chunks:
            index.append((chunk, embed(chunk)))
            time.sleep(0.5)
        _cache.clear()
        _cache[cache_key] = index
    return _cache[cache_key]


def retrieve(question, cache_key, chunks):
    """Semantic search with embeddings; falls back to keyword search if Bedrock is throttling."""
    try:
        index = load_index(cache_key, chunks)
        return top_k(embed(question), index, TOP_K), "embeddings"
    except ClientError as error:
        if not is_throttled(error):
            raise
        print("Embeddings throttled, using keyword retrieval instead")
        return keyword_top_k(question, chunks, TOP_K), "keyword"


def ask_model(question, chunks):
    context = "\n\n---\n\n".join(chunks)
    response = bedrock_chat.converse(
        modelId=CHAT_MODEL_ID,
        system=[{"text": SYSTEM_PROMPT}],
        messages=[{
            "role": "user",
            "content": [{"text": f"Log excerpts:\n{context}\n\nQuestion: {question}"}],
        }],
        inferenceConfig={"maxTokens": 400, "temperature": 0.2},
    )
    return response["output"]["message"]["content"][0]["text"]


def lambda_handler(event, context):
    event = event or {}
    question = str(event.get("question", "")).strip()
    if not question:
        return {"error": 'Send a JSON payload like {"question": "Why did the service fail?"}'}
    if len(question) > MAX_QUESTION_CHARS:
        return {"error": f"Question is too long (max {MAX_QUESTION_CHARS} characters)."}

    cache_key, all_chunks = load_chunks(event.get("log_key", DEFAULT_LOG_KEY))
    chunks, retrieval = retrieve(question, cache_key, all_chunks)
    try:
        answer = ask_model(question, chunks)
        mode = "ai-answer"
    except ClientError as error:
        if not is_throttled(error):
            raise
        # Graceful degradation: still return the most relevant log lines.
        answer = (
            f"AI answer unavailable right now: Bedrock limit reached for {CHAT_MODEL_ID} "
            f"({error.response['Error'].get('Message', 'throttled')}). "
            "The most relevant log lines for your question are shown below."
        )
        mode = "retrieval-only"
    print(json.dumps({"question": question, "retrieval": retrieval, "mode": mode, "model": CHAT_MODEL_ID}))
    return {
        "question": question,
        "answer": answer,
        "mode": mode,
        "model": CHAT_MODEL_ID,
        "retrieval": retrieval,
        "sources": chunks,
    }
