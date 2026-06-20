/**
 * Base path para todas las llamadas HTTP. El nginx del container UI proxiea
 * /api/* a examen-api inyectando el header X-API-Key server-side.
 *
 * Para dev local con tunnel SSH: `npm run start` corre con proxy.conf.json.
 */
export const API_BASE = '/api';
