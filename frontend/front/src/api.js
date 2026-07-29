
const configured = (import.meta.env.VITE_API_URL || "").trim();
const API_BASE_URL = (configured || "http://localhost:8000").replace(/\/+$/, "");

export function apiUrl(path) {
  return `${API_BASE_URL}${path.startsWith("/") ? path : `/${path}`}`;
}

export default API_BASE_URL;
