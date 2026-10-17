# Sample app code for detect.py to scan. Never run.
async def answer(router, question):
    stream = await router.acompletion(model="chat", messages=[{"role": "user", "content": question}], stream=True)
    async for chunk in stream:
        yield chunk
