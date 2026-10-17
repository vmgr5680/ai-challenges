"""Alternative: does a fallback model group rescue a stream dropped before its first
event, when num_retries does not? Each group gets a twin ("chat-b", ...) on the same
upstream. Also prints WHEN the error reaches the caller: during the call, or while
iterating (after the Router has already returned).

    .venv-<ver>/bin/python alternatives/fallbacks_probe.py
"""
import asyncio, sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))
import litellm_probe as p
from litellm import Router
from fake_upstream import FakeUpstream
async def call(r, route, model):
    if route=="chat": return await r.acompletion(model=model,messages=[{"role":"user","content":"hi"}],stream=True)
    if route=="messages": return await r.aanthropic_messages(model=model,max_tokens=16,stream=True,messages=[{"role":"user","content":"hi"}])
    return await r.agenerate_content_stream(model=model,contents=[{"role":"user","parts":[{"text":"hi"}]}])
def router(base, fb):
    ml=[]
    for name,prov,sfx in [("chat","openai/fake","/v1"),("messages","anthropic/fake",""),("genai","gemini/fake","")]:
        for n in (name, name+"-b"):
            ml.append({"model_name":n,"litellm_params":{"model":prov,"api_base":base+sfx,"api_key":"k"}})
    kw=dict(model_list=ml,num_retries=2,retry_after=0)
    if fb: kw["fallbacks"]=[{"chat":["chat-b"]},{"messages":["messages-b"]},{"genai":["genai-b"]}]
    return Router(**kw)
async def m():
    for fb in (False, True):
        for route in ["chat","messages","genai"]:
            with FakeUpstream(drops=1) as up:
                r=router(up.base, fb); phase="call"
                try:
                    s=await call(r,route,route); phase="iterate"
                    b=await p._drain(s); res="ok" if "Hello" in b else "no content"
                except Exception as e: res=f"{type(e).__name__} during {phase}"
                print(f"fallbacks={fb!s:5} {route:8} hits={up.hits} -> {res}")
asyncio.run(m())
