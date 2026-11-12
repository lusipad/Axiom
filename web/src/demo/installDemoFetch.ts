import type { demoFixtures } from "./fixtures";
import {
  compareCncExportsLocal,
  diagnoseSingleRunLocal,
  type ControllerProfileSpec,
} from "./localCncEngine";

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

export async function installDemoFetch(options?: {
  force?: boolean;
}): Promise<void> {
  if (!options?.force && import.meta.env.VITE_DEMO !== "1") return;
  const fixtures: typeof demoFixtures = (await import("./fixtures")).demoFixtures;
  const workbenchBundle = fixtures.get(
    "GET /api/v1/benchmarks/cnc/param-workbench",
  )?.[0]?.response as { controllerProfiles?: ControllerProfileSpec[] } | undefined;
  const controllerProfiles = workbenchBundle?.controllerProfiles ?? [];
  const nativeFetch = window.fetch.bind(window);
  window.fetch = (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const rawUrl = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    const method = (init?.method ?? (input instanceof Request ? input.method : "GET")).toUpperCase();
    const key = normalizeKey(method, rawUrl);
    if (key === null) return nativeFetch(input, init);
    const candidates = fixtures.get(key);
    const payload = parseBody(init);
    const matched = candidates?.find((entry) => deepEqual(entry.request, payload));
    if (matched) {
      return Promise.resolve(
        new Response(JSON.stringify(matched.response), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );
    }
    if (key === "POST /api/v1/benchmarks/cnc/compare") {
      try {
        const computed = compareCncExportsLocal(payload);
        return Promise.resolve(
          new Response(JSON.stringify(computed), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          }),
        );
      } catch (err) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              detail: err instanceof Error ? err.message : "A/B 对比参数校验未通过",
            }),
            {
              status: 422,
              headers: { "Content-Type": "application/json" },
            },
          ),
        );
      }
    }
    if (key === "POST /api/v1/benchmarks/cnc/param-diagnose") {
      try {
        const computed = diagnoseSingleRunLocal(payload, controllerProfiles);
        return Promise.resolve(
          new Response(JSON.stringify(computed), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          }),
        );
      } catch (err) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              detail: err instanceof Error ? err.message : "单刀快诊数据校验未通过",
            }),
            {
              status: 422,
              headers: { "Content-Type": "application/json" },
            },
          ),
        );
      }
    }
    return Promise.resolve(
      new Response(JSON.stringify({ detail: "演示模式未覆盖该请求" }), {
        status: 503,
        headers: { "Content-Type": "application/json" },
      }),
    );
  };
}
