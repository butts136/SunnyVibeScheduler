type Entry = {
  count: number;
  resetAt: number;
};

type Options = {
  key: string;
  limit: number;
  windowMs: number;
};

const globalStore = globalThis as typeof globalThis & {
  __sunnyvibeRateLimitStore?: Map<string, Entry>;
};

function store() {
  if (!globalStore.__sunnyvibeRateLimitStore) {
    globalStore.__sunnyvibeRateLimitStore = new Map();
  }
  return globalStore.__sunnyvibeRateLimitStore;
}

export function assertRateLimit({ key, limit, windowMs }: Options) {
  const now = Date.now();
  const rateStore = store();
  const current = rateStore.get(key);

  if (!current || current.resetAt <= now) {
    rateStore.set(key, { count: 1, resetAt: now + windowMs });
    return;
  }

  if (current.count >= limit) {
    throw new Error('Trop de tentatives. Réessayez dans quelques minutes.');
  }

  current.count += 1;
  rateStore.set(key, current);
}
