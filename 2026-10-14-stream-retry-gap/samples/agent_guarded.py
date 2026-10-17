# Sample app code for detect.py to scan. Never run.
from stream_guard import first_chunk_retry

async def answer(router, question):
    async def open_stream():
        return await router.acompletion(model="chat", messages=[{"role": "user", "content": question}], stream=True)
    async for chunk in await first_chunk_retry(open_stream, retries=2):
        yield chunk
