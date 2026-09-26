import type { NextConfig } from "next";

const apiTarget = process.env.API_INTERNAL_URL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  output: "standalone",
  // Full structural analysis evaluates every load combination synchronously.
  // Keep a bounded budget; Next's 30 s proxy default can cut off valid analyses.
  experimental: { proxyTimeout: 180_000 },
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${apiTarget}/api/:path*`,
      },
      {
        source: "/backend-health",
        destination: `${apiTarget}/health`,
      },
    ];
  },
};

export default nextConfig;
