import type { demoFixtures } from "./fixtures";

function deepEqual(left: unknown, right: unknown): boolean {
  if (left === right) return true;
  if (typeof left !== typeof right) return false;
  if (Array.isArray(left) || Array.isArray(right)) {
    return (
      Array.isArray(left) &&
      Array.isArray(right) &&
      left.length === right.length &&
      left.every((item, index) => deepEqual(item, right[index]))
    );
  }
  if (left !== null && right !== null && typeof left === "object") {
    const leftKeys = Object.keys(left as Record<string, unknown>);
    const rightKeys = Object.keys(right as Record<string, unknown>);
    return (
      leftKeys.length === rightKeys.length &&
      leftKeys.every(
        (key) =>
          key in (right as Record<string, unknown>) &&
          deepEqual(
            (left as Record<string, unknown>)[key],
            (right as Record<string, unknown>)[key],
          ),
      )
    );
  }
  return false;
}

function normalizeKey(method: string, rawUrl: string): string | null {
  let parsed: URL;
  try {
    parsed = new URL(rawUrl, window.location.origin);
  } catch {
    return null;
  }
  if (!parsed.pathname.startsWith("/api/v1/")) return null;
  const pairs = [...parsed.searchParams.entries()].sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0));
  const query = new URLSearchParams(pairs).toString();
  return `${method.toUpperCase()} ${parsed.pathname}${query ? `?${query}` : ""}`;
}

function parseBody(init: RequestInit | undefined): unknown {
  const body = init?.body;
  if (typeof body !== "string" || body.length === 0) return null;
  try {
    return JSON.parse(body);
  } catch {
    return null;
  }
}

export async function installDemoFetch(): Promise<void> {
  if (import.meta.env.VITE_DEMO !== "1") return;
  const fixtures: typeof demoFixtures = (await import("./fixtures")).demoFixtures;
  const nativeFetch = window.fetch.bind(window);
  window.fetch = (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const rawUrl = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    const method = (init?.method ?? (input instanceof Request ? input.method : "GET")).toUpperCase();
    const key = normalizeKey(method, rawUrl);
    if (key === null) return nativeFetch(input, init);
    const candidates = fixtures.get(key);
    const payload = parseBody(init);
    const matched = candidates?.find((entry) => deepEqual(entry.request, payload));
    if (!candidates || !matched) {
      return Promise.resolve(
        new Response(JSON.stringify({ detail: "演示模式未覆盖该请求" }), {
          status: 503,
          headers: { "Content-Type": "application/json" },
        }),
      );
    }
    return Promise.resolve(
      new Response(JSON.stringify(matched.response), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
  };
}
