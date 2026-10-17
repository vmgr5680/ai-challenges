// Same pattern in TypeScript, as a sketch (not run). detect.py flags line 7.
import { query } from "@anthropic-ai/claude-agent-sdk";

export async function* resumeChat(req: { sessionId: string; message: string }) {
  const options = {
    allowedTools: ["Read"],
    resume: req.sessionId, // untrusted
  };
  yield* query({ prompt: req.message, options });
}
