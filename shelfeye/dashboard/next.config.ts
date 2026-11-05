import type { NextConfig } from "next";

// The browser calls /api/* on the dashboard, and Next.js forwards it to the
// ShelfEye server, so the server needs no CORS setup.
const apiUrl = process.env.SHELFEYE_API_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  devIndicators: false, // the Next.js badge would cover the user card in the sidebar
  async rewrites() {
    // "fallback" so our own route handlers win, including dynamic ones like
    // the live view stream; a plain array would be checked before those.
    return {
      beforeFiles: [],
      afterFiles: [],
      fallback: [{ source: "/api/:path*", destination: `${apiUrl}/api/:path*` }],
    };
  },
};

export default nextConfig;
