/** @type {import('next').NextConfig} */
const nextConfig = {
  // Internal TS packages are shipped as source; let Next transpile them.
  transpilePackages: ["@relay/ui", "@relay/core", "@relay/db", "@relay/flag-sdk"],
  // The native flag engine is a platform .node addon — must stay a runtime
  // require on the server, never enter a bundle.
  serverExternalPackages: ["@relay/flag-node"],
};

export default nextConfig;
