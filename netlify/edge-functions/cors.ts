/**
 * Edge Function: inyecta cabeceras CORS en todas las respuestas (incl. 502)
 * y responde OPTIONS (preflight) sin invocar la función Lambda.
 */
import type { Config, Context } from "@netlify/edge-functions";

const CORS_ORIGIN = "https://salesianosfrontend.netlify.app";

const corsHeaders: Record<string, string> = {
  "Access-Control-Allow-Origin": CORS_ORIGIN,
  "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, PATCH, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type, Authorization",
  "Access-Control-Allow-Credentials": "true",
};

export const config: Config = {
  path: "/*",
};

export default async (request: Request, context: Context) => {
  if (request.method === "OPTIONS") {
    return new Response(null, {
      status: 204,
      headers: corsHeaders,
    });
  }

  const response = await context.next();
  const newHeaders = new Headers(response.headers);
  Object.entries(corsHeaders).forEach(([k, v]) => newHeaders.set(k, v));
  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers: newHeaders,
  });
};
