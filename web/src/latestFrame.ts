/** One HTTP image in flight and one replaceable latest request, never a frame queue. */
export function latestFrameReader(
  read: (id: string, signal: AbortSignal) => Promise<{ blob: Blob; capturedAt: string | null }>,
  received: (frame: { id: string; blob: Blob; capturedAt: string | null }) => void,
  failed: (error: unknown) => void,
  timeoutMs: number,
) {
  let pending: string | null = null;
  let active: AbortController | null = null;
  let activeId = "";
  let delivered = "";
  let closed = false;
  async function pump() {
    if (closed || active || !pending) return;
    const id = pending;
    pending = null;
    const controller = new AbortController();
    active = controller;
    activeId = id;
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const frame = await read(id, controller.signal);
      if (!closed && !controller.signal.aborted) {
        delivered = id;
        received({ id, ...frame });
      }
    } catch (error) {
      if (!closed) failed(error);
    } finally {
      clearTimeout(timer);
      active = null;
      activeId = "";
      if (!closed) void pump();
    }
  }
  return {
    offer(id: string) {
      if (closed || id === activeId || id === delivered) return;
      pending = id;
      void pump();
    },
    close() {
      closed = true;
      pending = null;
      active?.abort();
    },
  };
}
