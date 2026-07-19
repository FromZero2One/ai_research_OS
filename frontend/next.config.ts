import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  rewrites: async () => [
    {
      source: "/api/:path*",
      destination: "http://localhost:8000/api/v1/:path*",
    },
    {
      source: "/health",
      destination: "http://localhost:8000/health",
    },
  ],
};

export default nextConfig;
