// Single source of truth for the backend base URL.
//
// Set VITE_API_URL at build time (see .env.example). Vite inlines env vars at
// build time, so this must be configured on the host that runs `vite build`,
// not at runtime. Falls back to the local dev backend.
// Note: `??` is deliberately NOT used here. A build environment that defines
// VITE_API_URL but leaves it blank yields an empty string, not undefined,
// which would slip past a nullish check and bake in no host at all -- every
// request would then silently hit the static origin and 404. Treat blank as
// unset.
const configured = (import.meta.env.VITE_API_URL || "").trim();
const API_BASE_URL = (configured || "http://localhost:8000").replace(/\/+$/, "");

export function apiUrl(path) {
  return `${API_BASE_URL}${path.startsWith("/") ? path : `/${path}`}`;
}

export default API_BASE_URL;
