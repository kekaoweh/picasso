import type { NextConfig } from "next";

const backend = process.env.PICASSO_BACKEND_URL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  // Proxy the API so the session cookie is first-party and SSE/uploads share an origin.
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${backend}/api/:path*` }];
  },
};

export default nextConfig;
