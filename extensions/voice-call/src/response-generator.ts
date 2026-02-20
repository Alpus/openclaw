/**
 * Voice call response generator - uses the embedded Pi agent for tool support.
 * Routes voice responses through the same agent infrastructure as messaging.
 */

import crypto from "node:crypto";
import type { VoiceCallConfig } from "./config.js";
import { loadCoreAgentDeps, type CoreConfig } from "./core-bridge.js";

export type VoiceResponseParams = {
  /** Voice call config */
  voiceConfig: VoiceCallConfig;
  /** Core OpenClaw config */
  coreConfig: CoreConfig;
  /** Call ID for session tracking */
  callId: string;
  /** Caller's phone number */
  from: string;
  /** Conversation transcript */
  transcript: Array<{ speaker: "user" | "bot"; text: string }>;
  /** Latest user message */
  userMessage: string;
  /** Optional abort signal for cancelling speculative requests */
  signal?: AbortSignal;
  /** Optional extra hint to prepend to the system prompt */
  systemPromptHint?: string;
  /** Callback for partial (accumulated) LLM reply text — for streaming TTS */
  onPartialReply?: (info: { text: string }) => void;
  /** Override model (e.g. "anthropic/claude-haiku-3-5"). Uses responseModel if not set. */
  modelOverride?: string;
  /** Override max tokens for LLM response */
  maxTokens?: number;
  /** If true, use an ephemeral session (no history loaded, no history saved) */
  ephemeralSession?: boolean;
};

export type VoiceResponseResult = {
  text: string | null;
  error?: string;
};

type SessionEntry = {
  sessionId: string;
  updatedAt: number;
};

/**
 * Generate a voice response using the embedded Pi agent with full tool support.
 * Uses the same agent infrastructure as messaging for consistent behavior.
 *
 * If `onPartialReply` is provided, it will be called with accumulated text
 * as the LLM streams its response, enabling real-time TTS pipelining.
 */
export async function generateVoiceResponse(
  params: VoiceResponseParams,
): Promise<VoiceResponseResult> {
  const {
    voiceConfig,
    callId,
    from,
    transcript,
    userMessage,
    coreConfig,
    signal,
    systemPromptHint,
    onPartialReply,
    modelOverride,
    maxTokens,
    ephemeralSession,
  } = params;

  // Check if already aborted before doing any work
  if (signal?.aborted) {
    return { text: null, error: "Aborted before start" };
  }

  if (!coreConfig) {
    return { text: null, error: "Core config unavailable for voice response" };
  }

  let deps: Awaited<ReturnType<typeof loadCoreAgentDeps>>;
  try {
    deps = await loadCoreAgentDeps();
  } catch (err) {
    return {
      text: null,
      error: err instanceof Error ? err.message : "Unable to load core agent dependencies",
    };
  }
  const cfg = coreConfig;

  // Build voice-specific session key based on phone number
  const normalizedPhone = from.replace(/\D/g, "");
  const agentId = "main";

  // Resolve paths
  const storePath = deps.resolveStorePath(cfg.session?.store, { agentId });
  const agentDir = deps.resolveAgentDir(cfg, agentId);
  const workspaceDir = deps.resolveAgentWorkspaceDir(cfg, agentId);

  // Ensure workspace exists
  await deps.ensureAgentWorkspace({ dir: workspaceDir });

  let sessionKey: string;
  let sessionId: string;
  let sessionFile: string;

  if (ephemeralSession) {
    // Ephemeral: fresh session with no history — for fast model with trimmed context
    sessionKey = `voice:ephemeral:${crypto.randomUUID()}`;
    sessionId = crypto.randomUUID();
    sessionFile = deps.resolveSessionFilePath(
      sessionId,
      { sessionId, updatedAt: Date.now() },
      { agentId },
    );
  } else {
    sessionKey = `voice:${normalizedPhone}`;

    // Load or create session entry
    const sessionStore = deps.loadSessionStore(storePath);
    const now = Date.now();
    let sessionEntry = sessionStore[sessionKey] as SessionEntry | undefined;

    if (!sessionEntry) {
      sessionEntry = {
        sessionId: crypto.randomUUID(),
        updatedAt: now,
      };
      sessionStore[sessionKey] = sessionEntry;
      await deps.saveSessionStore(storePath, sessionStore);
    }

    sessionId = sessionEntry.sessionId;
    sessionFile = deps.resolveSessionFilePath(sessionId, sessionEntry, { agentId });
  }

  // Resolve model from config (modelOverride takes priority)
  const modelRef =
    modelOverride || voiceConfig.responseModel || `${deps.DEFAULT_PROVIDER}/${deps.DEFAULT_MODEL}`;
  const slashIndex = modelRef.indexOf("/");
  const provider = slashIndex === -1 ? deps.DEFAULT_PROVIDER : modelRef.slice(0, slashIndex);
  const model = slashIndex === -1 ? modelRef : modelRef.slice(slashIndex + 1);

  // Resolve thinking level
  const thinkLevel = deps.resolveThinkingDefault({ cfg, provider, model });

  // Resolve agent identity for personalized prompt
  const identity = deps.resolveAgentIdentity(cfg, agentId);
  const agentName = identity?.name?.trim() || "assistant";

  // Build system prompt with conversation history
  const basePrompt =
    voiceConfig.responseSystemPrompt ??
    `Ты ${agentName}, голосовой AI-компаньон в телефонном разговоре. Отвечай кратко и естественно (1-3 предложения). Говори по-русски. Номер звонящего: ${from}. У тебя есть инструменты — используй когда нужно.`;

  let extraSystemPrompt = systemPromptHint ? `${basePrompt}\n\n${systemPromptHint}` : basePrompt;
  if (transcript.length > 0) {
    const history = transcript
      .map((entry) => `${entry.speaker === "bot" ? "You" : "Caller"}: ${entry.text}`)
      .join("\n");
    extraSystemPrompt = `${basePrompt}\n\nConversation so far:\n${history}`;
  }

  // Resolve timeout
  const timeoutMs = voiceConfig.responseTimeoutMs ?? deps.resolveAgentTimeoutMs({ cfg });
  const runId = `voice:${callId}:${Date.now()}`;

  // Check abort before expensive LLM call
  if (signal?.aborted) {
    return { text: null, error: "Aborted before LLM call" };
  }

  try {
    const result = await deps.runEmbeddedPiAgent({
      sessionId,
      sessionKey,
      messageProvider: "voice",
      sessionFile,
      workspaceDir: ephemeralSession ? "/tmp/openclaw-ephemeral" : workspaceDir,
      config: cfg,
      prompt: userMessage,
      provider,
      model,
      thinkLevel,
      verboseLevel: "off",
      timeoutMs,
      runId,
      lane: "voice",
      extraSystemPrompt,
      agentDir: ephemeralSession ? undefined : agentDir,
      onPartialReply,
      ...(maxTokens ? { maxTokens } : {}),
    });

    // Extract text from payloads
    const texts = (result.payloads ?? [])
      .filter((p) => p.text && !p.isError)
      .map((p) => p.text?.trim())
      .filter(Boolean);

    let text = texts.join(" ") || null;

    // Strip any leaked tool-call XML that the model may emit
    if (text) {
      text = text.replace(/<tool_calls>[\s\S]*/i, "").trim() || null;
    }

    if (!text && result.meta?.aborted) {
      return { text: null, error: "Response generation was aborted" };
    }

    return { text };
  } catch (err) {
    console.error(`[voice-call] Response generation failed:`, err);
    return { text: null, error: String(err) };
  }
}
