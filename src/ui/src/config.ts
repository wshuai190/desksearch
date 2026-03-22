// When served from FastAPI, use relative URLs (same origin).
// Only fall back to localhost:3777 during Vite dev with no env override.
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '';
