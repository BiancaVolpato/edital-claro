// Same-origin proxy to the backend API. The browser calls /api/..., and this
// handler forwards to API_URL, read at request time, so the same build works
// locally, in docker-compose and in production, without CORS.

import type { NextRequest } from "next/server";

const API_URL = process.env.API_URL ?? "http://localhost:8000";
// Request and response headers worth forwarding; everything else stays behind.
// X-Forwarded-For carries the client address set by the hosting platform's proxy,
// so the backend's rate limit counts each visitor, not this server.
const REQUEST_HEADERS = ["content-type", "accept", "x-forwarded-for"];
const RESPONSE_HEADERS = ["content-type", "content-disposition", "content-length", "retry-after"];
// On a platform whose servers have no fixed address (Vercel), the backend cannot
// list this server as a trusted proxy. Instead this server proves itself with a
// shared secret and names the visitor, read from a header the platform sets and
// overwrites (Vercel: x-real-ip), so a visitor cannot choose it. See ADR-040.
const PROXY_TOKEN = process.env.PROXY_TOKEN;
const CLIENT_IP_HEADER = process.env.CLIENT_IP_HEADER;

async function forward(
  request: NextRequest,
  ctx: RouteContext<"/api/[...path]">,
): Promise<Response> {
  const { path } = await ctx.params;
  const target = new URL(
    `${API_URL}/${path.map(encodeURIComponent).join("/")}`,
  );
  target.search = request.nextUrl.search;

  const headers = new Headers();
  for (const name of REQUEST_HEADERS) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  const visitor = CLIENT_IP_HEADER ? request.headers.get(CLIENT_IP_HEADER) : null;
  if (PROXY_TOKEN && visitor) {
    headers.set("x-edital-proxy-token", PROXY_TOKEN);
    headers.set("x-edital-client-ip", visitor.split(",")[0].trim());
  }
  const hasBody = request.method !== "GET" && request.method !== "HEAD";

  let upstream: Response;
  try {
    upstream = await fetch(target, {
      method: request.method,
      headers,
      body: hasBody ? request.body : undefined,
      // Required by Node's fetch to stream a request body (PDF uploads).
      ...(hasBody ? { duplex: "half" } : {}),
      cache: "no-store",
    } as RequestInit);
  } catch {
    return Response.json(
      { detail: "Não foi possível falar com o backend. Confira se ele está rodando." },
      { status: 502 },
    );
  }

  const responseHeaders = new Headers();
  for (const name of RESPONSE_HEADERS) {
    const value = upstream.headers.get(name);
    if (value) responseHeaders.set(name, value);
  }
  return new Response(upstream.body, {
    status: upstream.status,
    headers: responseHeaders,
  });
}

export const GET = forward;
export const POST = forward;
export const PUT = forward;
export const DELETE = forward;
