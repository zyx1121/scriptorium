interface Bucket {
  tokens: number;
  last: number;
}

const buckets = new Map<string, Bucket>();

export function rateLimit(key: string, capacity: number, refillPerSec: number): boolean {
  const now = Date.now();
  let b = buckets.get(key);
  if (!b) {
    b = { tokens: capacity - 1, last: now };
    buckets.set(key, b);
    return true;
  }
  const elapsedSec = (now - b.last) / 1000;
  b.tokens = Math.min(capacity, b.tokens + elapsedSec * refillPerSec);
  b.last = now;
  if (b.tokens < 1) return false;
  b.tokens -= 1;
  return true;
}

const SWEEP_MS = 5 * 60_000;
const IDLE_MS = 10 * 60_000;
setInterval(() => {
  const now = Date.now();
  for (const [k, v] of buckets) {
    if (now - v.last > IDLE_MS) buckets.delete(k);
  }
}, SWEEP_MS).unref();
