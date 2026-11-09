import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  reactStrictMode: true,
  poweredByHeader: false,
  devIndicators: false,
  // Single-container deployments: the browser calls /api on the same origin and Next.js proxies
  // to the backend inside the container (set BACKEND_INTERNAL_URL at build time).
  async rewrites() {
    const backend = process.env.BACKEND_INTERNAL_URL;
    return backend ? [{ source: "/api/:path*", destination: `${backend}/api/:path*` }] : [];
  },
  images: {
    // Speaker photos come from the Sessionize CDN referenced in the source data.
    remotePatterns: [{ protocol: "https", hostname: "cdn.sessionize.com" }],
  },
};

export default nextConfig;
