// Execution is started once; all recovery traffic is read-only.
const BASE = 'http://localhost:8000/api/review-board';
const terminal = (session: any) => ['completed', 'partial_failure', 'budget_stopped', 'failed'].includes(session.status);
export const activeRunKey = 'review-board-active-run';
export function rememberRun(id: string | null) {
  try {
    if (id) globalThis.localStorage?.setItem(activeRunKey, id);
    else globalThis.localStorage?.removeItem(activeRunKey);
  } catch { /* Storage may be disabled; the session ID still works for manual recovery. */ }
}
export function rememberedRun(): string | null {
  try { return globalThis.localStorage?.getItem(activeRunKey) || null; } catch { return null; }
}

async function readSession(id: string, fetcher: typeof fetch) {
  const response = await fetcher(`${BASE}/sessions/${encodeURIComponent(id)}`);
  if (!response.ok) throw new Error(`Unable to recover review ${id} (${response.status}). No replacement run was started.`);
  return response.json();
}

export async function observeReview(id: string, initial: any, onEvent: (event: any) => void,
                                    fetcher: typeof fetch = fetch, pause = () => new Promise(resolve => setTimeout(resolve, 500))) {
  let session = initial;
  let sequence = -1;
  const accept = (next: any, nextSequence: number) => {
    if (!next || next.session_id !== id || !Number.isInteger(nextSequence) || nextSequence < 0) throw new Error('Unexpected review snapshot');
    if (nextSequence <= sequence) return;
    sequence = nextSequence;
    session = next;
    onEvent({ type: terminal(next) ? 'session_final' : 'session_snapshot', session: next, sequence });
  };
  if (!session) session = await readSession(id, fetcher);
  accept(session, session.run_metadata?.sequence || 0);
  if (!terminal(session)) {
    let reader: ReadableStreamDefaultReader<Uint8Array> | undefined;
    try {
      const res = await fetcher(`${BASE}/sessions/${encodeURIComponent(id)}/events?after=${sequence}`);
      if (!res.ok || !res.body) throw new Error('Progress stream unavailable');
      reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      while (!terminal(session)) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, '\n');
        let boundary;
        while ((boundary = buffer.indexOf('\n\n')) >= 0) {
          const block = buffer.slice(0, boundary);
          buffer = buffer.slice(boundary + 2);
          const data = block.split('\n').filter(line => line.startsWith('data:')).map(line => line.slice(5).trimStart()).join('\n');
          if (!data) continue;
          const event = JSON.parse(data);
          accept(event.session, event.sequence);
        }
      }
    } catch {
      // A disconnect or premature EOF recovers the existing run, never POSTs /run.
    } finally {
      await reader?.cancel().catch(() => {});
    }
  }
  while (!terminal(session)) {
    await pause();
    const next = await readSession(id, fetcher);
    // Interrupted projection can have the same stored cursor but a different terminal status.
    accept(next, Math.max(next.run_metadata?.sequence || 0, terminal(next) ? sequence + 1 : sequence));
  }
  rememberRun(null);
  return session;
}

export async function startReview(payload: any, onEvent: (event: any) => void, fetcher: typeof fetch = fetch) {
  const id = payload.session_id;
  rememberRun(id);
  let response;
  try {
    response = await fetcher(`${BASE}/runs`, {
      method: 'POST', headers: { 'Content-Type': 'application/json', 'Idempotency-Key': id },
      body: JSON.stringify(payload),
    });
  } catch {
    // The start may already have reached the server. Read by the same ID only.
    return observeReview(id, null, onEvent, fetcher);
  }
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Unable to start review');
  }
  let initial;
  try { initial = await response.json(); }
  catch { return observeReview(id, null, onEvent, fetcher); }
  return observeReview(id, initial, onEvent, fetcher);
}
