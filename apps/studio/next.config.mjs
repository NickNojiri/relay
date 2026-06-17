/** @type {import('next').NextConfig} */
const nextConfig = {
  // Internal TS packages are shipped as source; let Next transpile them.
  transpilePackages: ["@relay/ui", "@relay/core", "@relay/db", "@relay/flag-sdk"],
};

export default nextConfig;
