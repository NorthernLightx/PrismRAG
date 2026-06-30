/* Frontend → API base URL.

   Empty string means "same origin" — the default for local dev and the combined
   (single-service) deploy, so api.js falls back to window.location.origin.

   When the frontend is served from its own host (decoupled deploy), the build
   overwrites this file with the API service URL — see Dockerfile.web's
   `--build-arg API_BASE=...`. The URL itself is supplied at build time and is
   not committed. */
window.SPECTRARAG_API_BASE = "";
