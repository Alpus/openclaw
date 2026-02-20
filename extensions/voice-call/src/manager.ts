import fs from "node:fs";
import fsp from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import type { VoiceCallConfig } from "./config.js";
import type { CallManagerContext } from "./manager/context.js";
import { processEvent as processManagerEvent } from "./manager/events.js";
import { getCallByProviderCallId as getCallByProviderCallIdFromMaps } from "./manager/lookup.js";
import {
  continueCall as continueCallWithContext,
  endCall as endCallWithContext,
  initiateCall as initiateCallWithContext,
  speak as speakWithContext,
  speakInitialMessage as speakInitialMessageWithContext,
} from "./manager/outbound.js";
import { getCallHistoryFromStore, loadActiveCallsFromStore } from "./manager/store.js";
import type { VoiceCallProvider } from "./providers/base.js";
import type { VoiceCallProvider } from "./providers/base.js";
import type {
  CallId,
  CallRecord,
  NormalizedEvent,
  OutboundCallOptions,
  TranscriptEntry,
} from "./types.js";
import type { CallId, CallRecord, NormalizedEvent, OutboundCallOptions } from "./types.js";
import { resolveUserPath } from "./utils.js";

function resolveDefaultStoreBase(config: VoiceCallConfig, storePath?: string): string {
  const rawOverride = storePath?.trim() || config.store?.trim();
  if (rawOverride) {
    return resolveUserPath(rawOverride);
  }
  const preferred = path.join(os.homedir(), ".openclaw", "voice-calls");
  const candidates = [preferred].map((dir) => resolveUserPath(dir));
  const existing =
    candidates.find((dir) => {
      try {
        return fs.existsSync(path.join(dir, "calls.jsonl")) || fs.existsSync(dir);
      } catch {
        return false;
      }
    }) ?? resolveUserPath(preferred);
  return existing;
}

/**
 * Manages voice calls: state ownership and delegation to manager helper modules.
 */
export class CallManager {
  private activeCalls = new Map<CallId, CallRecord>();
  private providerCallIdMap = new Map<string, CallId>();
  private processedEventIds = new Set<string>();
  private rejectedProviderCallIds = new Set<string>();
  private provider: VoiceCallProvider | null = null;
  private config: VoiceCallConfig;
  private storePath: string;
  private webhookUrl: string | null = null;
  private activeTurnCalls = new Set<CallId>();
  private transcriptWaiters = new Map<
    CallId,
    {
      resolve: (text: string) => void;
      reject: (err: Error) => void;
      timeout: NodeJS.Timeout;
    }
  >();
  private maxDurationTimers = new Map<CallId, NodeJS.Timeout>();

  /** Map callId → file path for the live transcript markdown */
  private liveTranscriptPaths = new Map<string, string>();

  constructor(config: VoiceCallConfig, storePath?: string) {
    this.config = config;
    this.storePath = resolveDefaultStoreBase(config, storePath);
  }

  /**
   * Initialize the call manager with a provider.
   */
  initialize(provider: VoiceCallProvider, webhookUrl: string): void {
    this.provider = provider;
    this.webhookUrl = webhookUrl;

    fs.mkdirSync(this.storePath, { recursive: true });

    const persisted = loadActiveCallsFromStore(this.storePath);
    this.activeCalls = persisted.activeCalls;
    this.providerCallIdMap = persisted.providerCallIdMap;
    this.processedEventIds = persisted.processedEventIds;
    this.rejectedProviderCallIds = persisted.rejectedProviderCallIds;
  }

  /**
   * Get the current provider.
   */
  getProvider(): VoiceCallProvider | null {
    return this.provider;
  }

  /**
   * Initiate an outbound call.
   */
  async initiateCall(
    to: string,
    sessionKey?: string,
    options?: OutboundCallOptions | string,
  ): Promise<{ callId: CallId; success: boolean; error?: string }> {
    return initiateCallWithContext(this.getContext(), to, sessionKey, options);
  }

  /**
   * Speak to user in an active call.
   */
  async speak(callId: CallId, text: string): Promise<{ success: boolean; error?: string }> {
    return speakWithContext(this.getContext(), callId, text);
  }

  /**
   * Speak the initial message for a call (called when media stream connects).
   */
  async speakInitialMessage(providerCallId: string): Promise<void> {
    return speakInitialMessageWithContext(this.getContext(), providerCallId);
  }

  /**
   * Continue call: speak prompt, then wait for user's final transcript.
   */
  async continueCall(
    callId: CallId,
    prompt: string,
  ): Promise<{ success: boolean; transcript?: string; error?: string }> {
    return continueCallWithContext(this.getContext(), callId, prompt);
  }

  /**
   * End an active call.
   */
  async endCall(callId: CallId): Promise<{ success: boolean; error?: string }> {
    return endCallWithContext(this.getContext(), callId);
  }

  private getContext(): CallManagerContext {
    return {
      activeCalls: this.activeCalls,
      providerCallIdMap: this.providerCallIdMap,
      processedEventIds: this.processedEventIds,
      rejectedProviderCallIds: this.rejectedProviderCallIds,
      provider: this.provider,
      config: this.config,
      storePath: this.storePath,
      webhookUrl: this.webhookUrl,
      activeTurnCalls: this.activeTurnCalls,
      transcriptWaiters: this.transcriptWaiters,
      maxDurationTimers: this.maxDurationTimers,
      onCallAnswered: (call) => {
        this.maybeSpeakInitialMessageOnAnswered(call);
      },
      onCallStartTranscript: (call) => {
        this.startTranscriptFile(call);
      },
      onTranscriptEntry: (call, entry) => {
        this.appendTranscriptLine(call, entry);
      },
      onCallEnded: (call) => {
        this.finalizeTranscriptFile(call);
      },
    };
  }

  /**
   * Process a webhook event.
   */
  processEvent(event: NormalizedEvent): void {
    processManagerEvent(this.getContext(), event);
  }

  private maybeSpeakInitialMessageOnAnswered(call: CallRecord): void {
    const initialMessage =
      typeof call.metadata?.initialMessage === "string" ? call.metadata.initialMessage.trim() : "";

    if (!initialMessage) {
      return;
    }

    if (!this.provider || !call.providerCallId) {
      return;
    }

    // Twilio has provider-specific state for speaking (<Say> fallback) and can
    // fail for inbound calls; keep existing Twilio behavior unchanged.
    if (this.provider.name === "twilio") {
      return;
    }

    void this.speakInitialMessage(call.providerCallId);
  }

  /**
   * Get an active call by ID.
   */
  getCall(callId: CallId): CallRecord | undefined {
    return this.activeCalls.get(callId);
  }

  /**
   * Get an active call by provider call ID (e.g., Twilio CallSid).
   */
  getCallByProviderCallId(providerCallId: string): CallRecord | undefined {
    return getCallByProviderCallIdFromMaps({
      activeCalls: this.activeCalls,
      providerCallIdMap: this.providerCallIdMap,
      providerCallId,
    });
  }

  /**
   * Get all active calls.
   */
  getActiveCalls(): CallRecord[] {
    return Array.from(this.activeCalls.values());
  }

  /**
   * Get call history (from persisted logs).
   */
  async getCallHistory(limit = 50): Promise<CallRecord[]> {
    return getCallHistoryFromStore(this.storePath, limit);
  }

  // --- Real-time transcript file ---

  private static pad2(n: number): string {
    return String(n).padStart(2, "0");
  }

  /**
   * Create the transcript markdown file when a call starts.
   */
  private startTranscriptFile(call: CallRecord): void {
    const workspaceDir = path.join(os.homedir(), ".openclaw", "workspace");
    const callsDir = path.join(workspaceDir, "memory", "calls");

    const d = new Date(call.startedAt);
    const p = CallManager.pad2;
    const dateStr = `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
    const timeStr = `${p(d.getHours())}-${p(d.getMinutes())}`;
    const filePath = path.join(callsDir, `${dateStr}-${timeStr}.md`);
    this.liveTranscriptPaths.set(call.callId, filePath);

    const header = [
      `# Voice Call — ${dateStr} ${timeStr.replace("-", ":")}`,
      "",
      `- **Direction:** ${call.direction}`,
      `- **From:** ${call.from}`,
      `- **To:** ${call.to}`,
      `- **Status:** 🔴 In progress`,
      "",
      "## Transcript",
      "",
    ].join("\n");

    fsp
      .mkdir(callsDir, { recursive: true })
      .then(() => fsp.writeFile(filePath, header, "utf-8"))
      .then(() =>
        console.log(`[voice-call] Live transcript started: memory/calls/${dateStr}-${timeStr}.md`),
      )
      .catch((err) => console.error("[voice-call] Failed to start transcript file:", err));
  }

  /**
   * Append a single transcript entry to the live file.
   */
  private appendTranscriptLine(call: CallRecord, entry: TranscriptEntry): void {
    const filePath = this.liveTranscriptPaths.get(call.callId);
    if (!filePath) return;

    const ts = new Date(entry.timestamp);
    const p = CallManager.pad2;
    const time = `${p(ts.getHours())}:${p(ts.getMinutes())}:${p(ts.getSeconds())}`;
    const speaker = entry.speaker === "bot" ? "🤖 Bot" : "👤 User";
    const line = `**${time}** ${speaker}: ${entry.text}\n\n`;

    fsp.appendFile(filePath, line).catch((err) => {
      console.error("[voice-call] Failed to append transcript line:", err);
    });
  }

  /**
   * Finalize the transcript file when a call ends — update status & add duration.
   */
  private finalizeTranscriptFile(call: CallRecord): void {
    const filePath = this.liveTranscriptPaths.get(call.callId);
    if (!filePath) return;

    const durationMs = (call.endedAt || Date.now()) - call.startedAt;
    const durationMin = Math.round(durationMs / 60000);

    const footer = [
      "---",
      "",
      `- **Duration:** ~${durationMin} min`,
      `- **End reason:** ${call.endReason || "unknown"}`,
      "",
    ].join("\n");

    fsp
      .appendFile(filePath, footer)
      .then(() => fsp.readFile(filePath, "utf-8"))
      .then((content) => {
        const updated = content.replace("🔴 In progress", "✅ Completed");
        return fsp.writeFile(filePath, updated, "utf-8");
      })
      .then(() => console.log(`[voice-call] Transcript finalized: ${filePath}`))
      .catch((err) => console.error("[voice-call] Failed to finalize transcript:", err))
      .finally(() => this.liveTranscriptPaths.delete(call.callId));
  }
}
