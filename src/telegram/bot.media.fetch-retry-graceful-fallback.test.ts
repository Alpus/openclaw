import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { resetInboundDedupe } from "../auto-reply/reply/inbound-dedupe.js";
import * as ssrf from "../infra/net/ssrf.js";

const useSpy = vi.fn();
const middlewareUseSpy = vi.fn();
const onSpy = vi.fn();
const stopSpy = vi.fn();
const sendChatActionSpy = vi.fn();
const sendMessageSpy = vi.fn();
const cacheStickerSpy = vi.fn();
const getCachedStickerSpy = vi.fn();
const describeStickerImageSpy = vi.fn();
const resolvePinnedHostname = ssrf.resolvePinnedHostname;
const lookupMock = vi.fn();
let resolvePinnedHostnameSpy: ReturnType<typeof vi.spyOn>;

type ApiStub = {
  config: { use: (arg: unknown) => void };
  sendChatAction: typeof sendChatActionSpy;
  sendMessage: typeof sendMessageSpy;
  setMyCommands: (commands: Array<{ command: string; description: string }>) => Promise<void>;
};

const apiStub: ApiStub = {
  config: { use: useSpy },
  sendChatAction: sendChatActionSpy,
  sendMessage: sendMessageSpy,
  setMyCommands: vi.fn(async () => undefined),
};

beforeEach(() => {
  vi.useRealTimers();
  resetInboundDedupe();
  lookupMock.mockResolvedValue([{ address: "93.184.216.34", family: 4 }]);
  resolvePinnedHostnameSpy = vi
    .spyOn(ssrf, "resolvePinnedHostname")
    .mockImplementation((hostname) => resolvePinnedHostname(hostname, lookupMock));
});

afterEach(() => {
  lookupMock.mockReset();
  resolvePinnedHostnameSpy?.mockRestore();
  resolvePinnedHostnameSpy = null;
});

vi.mock("grammy", () => ({
  Bot: class {
    api = apiStub;
    use = middlewareUseSpy;
    on = onSpy;
    command = vi.fn();
    stop = stopSpy;
    catch = vi.fn();
    constructor(public token: string) {}
  },
  InputFile: class {},
  webhookCallback: vi.fn(),
}));

vi.mock("@grammyjs/runner", () => ({
  sequentialize: () => vi.fn(),
}));

vi.mock("@grammyjs/transformer-throttler", () => ({
  apiThrottler: () => vi.fn(() => "throttler"),
}));

vi.mock("../media/store.js", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../media/store.js")>();
  return {
    ...actual,
    saveMediaBuffer: vi.fn(async (buffer: Buffer, contentType?: string) => ({
      id: "media",
      path: "/tmp/telegram-media",
      size: buffer.byteLength,
      contentType: contentType ?? "application/octet-stream",
    })),
  };
});

vi.mock("../config/config.js", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../config/config.js")>();
  return {
    ...actual,
    loadConfig: () => ({
      channels: { telegram: { dmPolicy: "open", allowFrom: ["*"] } },
    }),
  };
});

vi.mock("../config/sessions.js", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../config/sessions.js")>();
  return {
    ...actual,
    updateLastRoute: vi.fn(async () => undefined),
  };
});

vi.mock("./sticker-cache.js", () => ({
  cacheSticker: (...args: unknown[]) => cacheStickerSpy(...args),
  getCachedSticker: (...args: unknown[]) => getCachedStickerSpy(...args),
  describeStickerImage: (...args: unknown[]) => describeStickerImageSpy(...args),
}));

vi.mock("../pairing/pairing-store.js", () => ({
  readChannelAllowFromStore: vi.fn(async () => [] as string[]),
  upsertChannelPairingRequest: vi.fn(async () => ({
    code: "PAIRCODE",
    created: true,
  })),
}));

vi.mock("../auto-reply/reply.js", () => {
  const replySpy = vi.fn(async (_ctx: unknown, opts?: { onReplyStart?: () => Promise<void> }) => {
    await opts?.onReplyStart?.();
    return undefined;
  });
  return { getReplyFromConfig: replySpy, __replySpy: replySpy };
});

const TEST_TIMEOUT_MS = process.platform === "win32" ? 120_000 : 90_000;

describe("telegram media fetch resilience", () => {
  it(
    "retries transient fetch failures and succeeds on second attempt",
    async () => {
      const { createTelegramBot } = await import("./bot.js");
      const replyModule = await import("../auto-reply/reply.js");
      const replySpy = replyModule.__replySpy as unknown as ReturnType<typeof vi.fn>;

      onSpy.mockReset();
      replySpy.mockReset();

      const runtimeError = vi.fn();
      createTelegramBot({
        token: "tok",
        runtime: {
          log: vi.fn(),
          error: runtimeError,
          exit: () => {
            throw new Error("exit");
          },
        },
      });
      const handler = onSpy.mock.calls.find((call: unknown[]) => call[0] === "message")?.[1] as (
        ctx: Record<string, unknown>,
      ) => Promise<void>;
      expect(handler).toBeDefined();

      // First fetch fails, second succeeds
      const fetchSpy = vi
        .spyOn(globalThis, "fetch" as never)
        .mockRejectedValueOnce(new TypeError("fetch failed"))
        .mockResolvedValueOnce({
          ok: true,
          status: 200,
          statusText: "OK",
          headers: { get: () => "audio/ogg" },
          arrayBuffer: async () => new Uint8Array([0x4f, 0x67, 0x67, 0x53]).buffer,
        } as Response);

      await handler({
        message: {
          message_id: 1,
          chat: { id: 1234, type: "private" },
          voice: { file_id: "voice_id", duration: 5 },
          date: 1736380800,
        },
        me: { username: "openclaw_bot" },
        getFile: async () => ({ file_path: "voice/file_123.oga" }),
      });

      // Should retry and succeed — message should be processed
      expect(runtimeError).not.toHaveBeenCalled();
      expect(replySpy).toHaveBeenCalledTimes(1);
      expect(fetchSpy).toHaveBeenCalledTimes(2);

      fetchSpy.mockRestore();
    },
    TEST_TIMEOUT_MS,
  );

  it(
    "continues processing without media when all fetch retries fail (voice message)",
    async () => {
      const { createTelegramBot } = await import("./bot.js");
      const replyModule = await import("../auto-reply/reply.js");
      const replySpy = replyModule.__replySpy as unknown as ReturnType<typeof vi.fn>;

      onSpy.mockReset();
      replySpy.mockReset();

      const runtimeError = vi.fn();
      createTelegramBot({
        token: "tok",
        runtime: {
          log: vi.fn(),
          error: runtimeError,
          exit: () => {
            throw new Error("exit");
          },
        },
      });
      const handler = onSpy.mock.calls.find((call: unknown[]) => call[0] === "message")?.[1] as (
        ctx: Record<string, unknown>,
      ) => Promise<void>;
      expect(handler).toBeDefined();

      // All fetch attempts fail
      const fetchSpy = vi
        .spyOn(globalThis, "fetch" as never)
        .mockRejectedValue(new TypeError("fetch failed"));

      await handler({
        message: {
          message_id: 2,
          chat: { id: 1234, type: "private" },
          voice: { file_id: "voice_id_2", duration: 3 },
          date: 1736380800,
        },
        me: { username: "openclaw_bot" },
        getFile: async () => ({ file_path: "voice/file_456.oga" }),
      });

      // Message should NOT be silently dropped — it should still be processed
      // Agent will see <media:audio> placeholder even without the actual file
      expect(runtimeError).not.toHaveBeenCalled();
      expect(replySpy).toHaveBeenCalledTimes(1);

      // The body should contain audio placeholder
      const payload = replySpy.mock.calls[0][0];
      expect(payload.Body).toContain("<media:audio>");

      fetchSpy.mockRestore();
    },
    TEST_TIMEOUT_MS,
  );

  it(
    "continues processing without media when all fetch retries fail (image)",
    async () => {
      const { createTelegramBot } = await import("./bot.js");
      const replyModule = await import("../auto-reply/reply.js");
      const replySpy = replyModule.__replySpy as unknown as ReturnType<typeof vi.fn>;

      onSpy.mockReset();
      replySpy.mockReset();

      const runtimeError = vi.fn();
      createTelegramBot({
        token: "tok",
        runtime: {
          log: vi.fn(),
          error: runtimeError,
          exit: () => {
            throw new Error("exit");
          },
        },
      });
      const handler = onSpy.mock.calls.find((call: unknown[]) => call[0] === "message")?.[1] as (
        ctx: Record<string, unknown>,
      ) => Promise<void>;
      expect(handler).toBeDefined();

      const fetchSpy = vi
        .spyOn(globalThis, "fetch" as never)
        .mockRejectedValue(new TypeError("fetch failed"));

      await handler({
        message: {
          message_id: 3,
          chat: { id: 1234, type: "private" },
          photo: [{ file_id: "photo_id" }],
          caption: "Check this out",
          date: 1736380800,
        },
        me: { username: "openclaw_bot" },
        getFile: async () => ({ file_path: "photos/photo.jpg" }),
      });

      // Message with caption should still be processed even without media
      expect(runtimeError).not.toHaveBeenCalled();
      expect(replySpy).toHaveBeenCalledTimes(1);
      const payload = replySpy.mock.calls[0][0];
      expect(payload.Body).toContain("Check this out");

      fetchSpy.mockRestore();
    },
    TEST_TIMEOUT_MS,
  );
});
