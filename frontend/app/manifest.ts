import type { MetadataRoute } from "next";

// Installable from the browser ("Add to Home Screen"). No offline cache on purpose: schedules
// change during an event and stale data is worse than a clear "you're offline".
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "conCompass: your AI event companion",
    short_name: "conCompass",
    description: "Find the right sessions and people, plan a conflict-free agenda, and know where to be next.",
    start_url: "/agent",
    display: "standalone",
    background_color: "#f6f5f1",
    theme_color: "#f6f5f1",
    icons: [{ src: "/icon.svg", sizes: "any", type: "image/svg+xml", purpose: "any" }],
  };
}
