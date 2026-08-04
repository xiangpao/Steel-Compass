import type { NextConfig } from "next";

const apiTarget = process.env.API_INTERNAL_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  output: "standalone",
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
