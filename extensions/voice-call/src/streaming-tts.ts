/**
 * Streaming TTS Pipeline — Phase 3: ElevenLabs WebSocket API
 *
 * Streams LLM tokens directly into ElevenLabs WebSocket → receives ulaw_8000 audio → Twilio.
 * No sentence splitting, no HTTP-per-sentence overhead.
 * ElevenLabs handles buffering and generation timing (auto_mode=true).
 */

import WebSocket from "ws";
import type { MediaStreamHandler } from "./media-stream.js";

/** Chunk size for sending audio to Twilio (640 bytes = 80ms at 8kHz ulaw) */
const CHUNK_SIZE = 640;

export interface StreamingTtsPipelineOptions {
  voiceId: string;
  modelId: string;
  apiKey: string;
  streamSid: string;
  mediaStreamHandler: MediaStreamHandler;
}

/**
 * Streaming TTS pipeline using ElevenLabs WebSocket API.
 * Accepts LLM tokens, sends them directly to ElevenLabs WS,
 * receives audio chunks and forwards to Twilio.
 */
export class StreamingTtsPipeline {
  private voiceId: string;
  private modelId: string;
  private apiKey: string;
  private streamSid: string;
  private mediaStreamHandler: MediaStreamHandler;

  private ws: WebSocket | null = null;
  private aborted = false;
  private flushed = false;
  private wsReady = false;
  private pendingChunks: string[] = [];

  /** Resolves when all audio has been received and sent */
  private completionResolve: (() => void) | null = null;
  private completionPromise: Promise<void>;

  /** Track leftover bytes for chunking */
  private audioLeftover = Buffer.alloc(0);

  constructor(opts: StreamingTtsPipelineOptions) {
    this.voiceId = opts.voiceId;
    this.modelId = opts.modelId;
    this.apiKey = opts.apiKey;
    this.streamSid = opts.streamSid;
    this.mediaStreamHandler = opts.mediaStreamHandler;
    this.completionPromise = new Promise((resolve) => {
      this.completionResolve = resolve;
    });

    this.connect();
  }

  /**
   * Open WebSocket connection to ElevenLabs and send BOS message.
   */
  private connect(): void {
    const url = `wss://api.elevenlabs.io/v1/text-to-speech/${this.voiceId}/stream-input?model_id=${this.modelId}&output_format=ulaw_8000&inactivity_timeout=30`;

    this.ws = new WebSocket(url, {
      headers: {
        "xi-api-key": this.apiKey,
      },
    });

    this.ws.on("open", () => {
      if (this.aborted) {
        this.ws?.close();
        return;
      }

      console.log("[streaming-tts] WebSocket connected to ElevenLabs");

      // Send BOS (Begin of Stream) message with voice settings
      this.ws!.send(
        JSON.stringify({
          text: " ",
          voice_settings: {
            stability: 0.5,
            similarity_boost: 0.75,
          },
        }),
      );

      this.wsReady = true;

      // Flush any buffered chunks that arrived before WS was ready
      for (const chunk of this.pendingChunks) {
        this.sendText(chunk);
      }
      this.pendingChunks = [];
    });

    this.ws.on("message", (data: WebSocket.Data) => {
      if (this.aborted) return;

      try {
        const msg = JSON.parse(data.toString());

        if (msg.audio) {
          // Decode base64 audio and send to Twilio in chunks
          const audioBuf = Buffer.from(msg.audio, "base64");
          this.sendAudioChunks(audioBuf);
        }

        if (msg.isFinal) {
          // ElevenLabs signals end of generation
          console.log("[streaming-tts] ElevenLabs generation complete");
          this.sendRemainingAudio();
          this.mediaStreamHandler.sendMark(this.streamSid, `streaming-tts-done-${Date.now()}`);
          this.completionResolve?.();
        }
      } catch (err) {
        if (!this.aborted) {
          console.error("[streaming-tts] Error parsing ElevenLabs message:", err);
        }
      }
    });

    this.ws.on("error", (err) => {
      if (!this.aborted) {
        console.error("[streaming-tts] WebSocket error:", err);
      }
      this.completionResolve?.();
    });

    this.ws.on("close", (code, reason) => {
      console.log(`[streaming-tts] WebSocket closed: ${code} ${reason}`);
      this.sendRemainingAudio();
      this.completionResolve?.();
    });
  }

  /**
   * Feed tokens from LLM stream. Sends directly to ElevenLabs WebSocket.
   * ElevenLabs handles internal buffering (auto_mode=false by default).
   */
  feedTokens(tokens: string): void {
    if (this.aborted) return;

    if (!this.wsReady) {
      this.pendingChunks.push(tokens);
      return;
    }

    this.sendText(tokens);
  }

  /**
   * Signal end of LLM stream. Sends EOS to ElevenLabs.
   */
  flush(): void {
    if (this.aborted || this.flushed) return;
    this.flushed = true;

    if (!this.wsReady) {
      // WS not ready yet — wait for it, then send EOS
      if (this.ws) {
        this.ws.on("open", () => {
          this.sendEos();
        });
      }
      return;
    }

    this.sendEos();
  }

  /**
   * Cancel all in-flight TTS and close WebSocket.
   */
  abort(): void {
    if (this.aborted) return;
    this.aborted = true;
    this.pendingChunks = [];

    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.close();
    }
    this.ws = null;

    this.mediaStreamHandler.clearAudio(this.streamSid);
    this.completionResolve?.();
  }

  /**
   * Wait for all audio to be received and sent.
   */
  async waitForCompletion(): Promise<void> {
    return this.completionPromise;
  }

  /**
   * Send text chunk to ElevenLabs WebSocket.
   */
  private sendText(text: string): void {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return;

    this.ws.send(
      JSON.stringify({
        text,
        try_trigger_generation: true,
      }),
    );
  }

  /**
   * Send EOS (End of Stream) to trigger final generation.
   */
  private sendEos(): void {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return;

    console.log("[streaming-tts] Sending EOS to ElevenLabs");
    this.ws.send(
      JSON.stringify({
        text: "",
      }),
    );
  }

  /**
   * Buffer audio and send in CHUNK_SIZE pieces to Twilio.
   */
  private sendAudioChunks(audio: Buffer): void {
    let buf = Buffer.concat([this.audioLeftover, audio]);

    while (buf.length >= CHUNK_SIZE) {
      this.mediaStreamHandler.sendAudio(this.streamSid, buf.subarray(0, CHUNK_SIZE));
      buf = buf.subarray(CHUNK_SIZE);
    }

    this.audioLeftover = buf;
  }

  /**
   * Send any remaining buffered audio.
   */
  private sendRemainingAudio(): void {
    if (this.audioLeftover.length > 0) {
      this.mediaStreamHandler.sendAudio(this.streamSid, this.audioLeftover);
      this.audioLeftover = Buffer.alloc(0);
    }
  }
}
