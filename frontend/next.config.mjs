const apiOrigin = process.env.API_SERVER_ORIGIN ?? process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${apiOrigin}/api/:path*`
      },
      {
        source: "/health",
        destination: `${apiOrigin}/health`
      },
      {
        source: "/ready",
        destination: `${apiOrigin}/ready`
      }
    ];
  }
};

export default nextConfig;
