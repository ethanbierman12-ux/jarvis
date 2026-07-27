import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Keep tracing rooted on the dashboard package (avoid parent hub/ lockfile warning)
  outputFileTracingRoot: path.join(__dirname),
  // Allow opening via 127.0.0.1 while Next binds localhost
  allowedDevOrigins: ["127.0.0.1", "localhost", "10.0.0.130"],
};

export default nextConfig;
