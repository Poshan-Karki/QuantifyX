const configured = (import.meta.env.VITE_API_URL || "").trim();
const API_BASE_URL = (configured || "http://localhost:8000").replace(/\/+$/, "");

export function apiUrl(path) {
  return `${API_BASE_URL}${path.startsWith("/") ? path : `/${path}`}`;
}

/**
 * Turn a FastAPI error body into one readable sentence.
 *
 * Two shapes arrive: a plain string `detail` from HTTPException, and a list of
 * {loc, msg} objects from 422 request validation.
 */
function describeError(body, status) {
  const detail = body?.detail;

  if (Array.isArray(detail)) {
    return detail
      .map((d) => `${d.loc?.[d.loc.length - 1] ?? "input"}: ${d.msg}`)
      .join("; ");
  }
  if (typeof detail === "string" && detail.trim()) return detail;
  if (typeof body?.message === "string" && body.message.trim()) return body.message;

  return `Request failed (HTTP ${status}).`;
}

async function request(path, options) {
  let res;
  try {
    res = await fetch(apiUrl(path), options);
  } catch {
    throw new Error(
      "Could not reach the API. Check that the backend is running and that " +
        "VITE_API_URL points at it.",
    );
  }

  const body = await res.json().catch(() => null);

  if (!res.ok) throw new Error(describeError(body, res.status));
  return body;
}

export function getJson(path) {
  return request(path, { method: "GET" });
}

export function postJson(path, payload) {
  return request(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

/** GET returning a list, with a non-array response treated as empty. */
export async function getList(path) {
  const body = await getJson(path);
  return Array.isArray(body) ? body : [];
}

export default API_BASE_URL;
