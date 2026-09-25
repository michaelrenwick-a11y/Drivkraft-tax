import type { NextConfig } from "next";

// The Python server (FastAPI + MCP) owns all data and logic; the web app is a
// client of it. /api is proxied so the browser talks to one origin.
const API_ORIGIN = process.env.DRIVKRAFT_API ?? "http://127.0.0.1:8787";

const nextConfig: NextConfig = {
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_ORIGIN}/api/:path*` }];
  },
};

export default nextConfig;
