"""Log RAG assistant: answers questions about a log file stored in S3.

Flow: load log from S3 -> split into chunks -> embed chunks (Titan) ->
embed the question -> pick the closest chunks -> ask the LLM (Amazon Nova)
to answer using only those chunks.
"""
import json
import os

import boto3  # already included in the AWS Lambda Python runtime

from rag import chunk_lines, top_k

s3 = boto3.client("s3")
bedrock = boto3.client("bedrock-runtime")

LOG_BUCKET = os.environ["LOG_BUCKET"]
DEFAULT_LOG_KEY = os.environ.get("LOG_KEY", "logs/app.log")
CHAT_MODEL_ID = os.environ.get("CHAT_MODEL_ID", "us.amazon.nova-lite-v1:0")
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
    response = bedrock.invoke_model(
        modelId=EMBED_MODEL_ID,
        contentType="application/json",
        accept="application/json",
        body=json.dumps({"inputText": text, "dimensions": 256, "normalize": True}),
    )
    return json.loads(response["body"].read())["embedding"]


def load_index(key):
    obj = s3.get_object(Bucket=LOG_BUCKET, Key=key)
    cache_key = (key, obj["ETag"])
    if cache_key not in _cache:
        text = obj["Body"].read().decode("utf-8", errors="replace")
        _cache.clear()
        _cache[cache_key] = [(chunk, embed(chunk)) for chunk in chunk_lines(text)]
    return _cache[cache_key]


def ask_model(question, chunks):
    context = "\n\n---\n\n".join(chunks)
    response = bedrock.converse(
        modelId=CHAT_MODEL_ID,
        system=[{"text": SYSTEM_PROMPT}],
        messages=[{
            "role": "user",
            "content": [{"text": f"Log excerpts:\n{context}\n\nQuestion: {question}"}],
        }],
        inferenceConfig={"maxTokens": 600, "temperature": 0.2},
    )
    return response["output"]["message"]["content"][0]["text"]


def lambda_handler(event, context):
    event = event or {}
    question = str(event.get("question", "")).strip()
    if not question:
        return {"error": 'Send a JSON payload like {"question": "Why did the service fail?"}'}
    if len(question) > MAX_QUESTION_CHARS:
        return {"error": f"Question is too long (max {MAX_QUESTION_CHARS} characters)."}

    index = load_index(event.get("log_key", DEFAULT_LOG_KEY))
    chunks = top_k(embed(question), index, TOP_K)
    answer = ask_model(question, chunks)
    print(json.dumps({"question": question, "chunks_used": len(chunks)}))
    return {"question": question, "answer": answer, "sources": chunks}
