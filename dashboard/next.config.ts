import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  outputFileTracingRoot: process.cwd(),
  // Disable the floating Next.js 15 Dev Tools panel. It is harmless but in `next dev`
  // it polls an internal `/messages` endpoint at ~1 Hz which spams the access log and
  // (more importantly) keeps the DevTools client React component rendering on every
  // navigation, slowing interactive development. Set to an object (e.g. `{ appIsrStatus: false, buildActivity: false }`)
  // if you want a partial re-enable; `false` disables the panel entirely.
  devIndicators: false,
};

export default nextConfig;
