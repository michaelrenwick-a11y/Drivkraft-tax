import type { NextConfig } from "next";

// The Python server (FastAPI + MCP) owns all data and logic; the web app is a
// client of it. /api is proxied so the browser talks to one origin.
const API_ORIGIN = process.env.DRIVKRAFT_API ?? "http://127.0.0.1:8787";

const nextConfig: NextConfig = {
  experimental: {
    // Source-document drops are base64 JSON: the bundled Copperleaf K-1 package is ~13 MB
    // encoded, over the 10 MB default, which cuts the proxied body off mid-stream.
    proxyClientMaxBodySize: "20mb",
  },
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_ORIGIN}/api/:path*` }];
  },
};

export default nextConfig;
