"""The risky pattern, as a sketch (not run): a web handler passes a client-supplied
session ID straight into the SDK. detect.py flags line 12."""

from claude_agent_sdk import ClaudeAgentOptions, query


async def resume_chat(request):
    body = await request.json()
    options = ClaudeAgentOptions(
        cwd="/srv/workspaces/" + body["user"],
        allowed_tools=["Read"],
        resume=body["session_id"],  # untrusted: may start with "-"
    )
    async for message in query(prompt=body["message"], options=options):
        yield message
