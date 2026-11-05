// Relays a camera's live view from the ShelfEye server. This route replaces
// the generic /api rewrite for streams, which would cut them off after 30 s.

const apiUrl = process.env.SHELFEYE_API_URL ?? "http://localhost:8000";

export const dynamic = "force-dynamic";

export async function GET(request: Request, { params }: { params: Promise<{ nodeId: string }> }) {
  const { nodeId } = await params;
  let upstream: Response;
  try {
    upstream = await fetch(`${apiUrl}/api/nodes/${encodeURIComponent(nodeId)}/stream`, {
      cache: "no-store",
      headers: { cookie: request.headers.get("cookie") ?? "" }, // the server checks the login session
      signal: request.signal, // closing the live view tells the server, which tells the Pi to stop
    });
  } catch {
    return new Response("ShelfEye server unreachable", { status: 502 });
  }
  if (!upstream.ok || !upstream.body) {
    return new Response(await upstream.text(), { status: upstream.status });
  }
  return new Response(upstream.body, {
    headers: {
      "Content-Type": upstream.headers.get("Content-Type") ?? "multipart/x-mixed-replace; boundary=FRAME",
      "Cache-Control": "no-cache, no-store",
    },
  });
}
