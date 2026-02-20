import type { VoiceCallConfig } from "../config.js";
import type { VoiceCallProvider } from "../providers/base.js";
import type { CallId, CallRecord, TranscriptEntry } from "../types.js";

export type TranscriptWaiter = {
  resolve: (text: string) => void;
  reject: (err: Error) => void;
  timeout: NodeJS.Timeout;
};

export type CallManagerRuntimeState = {
  activeCalls: Map<CallId, CallRecord>;
  providerCallIdMap: Map<string, CallId>;
  processedEventIds: Set<string>;
  /** Provider call IDs we already sent a reject hangup for; avoids duplicate hangup calls. */
  rejectedProviderCallIds: Set<string>;
};

export type CallManagerRuntimeDeps = {
  provider: VoiceCallProvider | null;
  config: VoiceCallConfig;
  storePath: string;
  webhookUrl: string | null;
};

export type CallManagerTransientState = {
  activeTurnCalls: Set<CallId>;
  transcriptWaiters: Map<CallId, TranscriptWaiter>;
  maxDurationTimers: Map<CallId, NodeJS.Timeout>;
};

export type CallManagerHooks = {
  /** Optional runtime hook invoked after an event transitions a call into answered state. */
  onCallAnswered?: (call: CallRecord) => void;
  /** Optional hook invoked when a call is answered (for transcript file creation). */
  onCallStartTranscript?: (call: CallRecord) => void;
  /** Optional hook invoked when a transcript entry is added to a call. */
  onTranscriptEntry?: (call: CallRecord, entry: TranscriptEntry) => void;
  /** Optional hook invoked when a call ends (for transcript finalization). */
  onCallEnded?: (call: CallRecord) => void;
};

export type CallManagerContext = CallManagerRuntimeState &
  CallManagerRuntimeDeps &
  CallManagerTransientState &
  CallManagerHooks;
