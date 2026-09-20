export const AUTH_COOKIE = "trader_session";
export const SESSION_DURATION_SECONDS = 60 * 60 * 24 * 7;

const REQUIRED_PIN = "9214";

function sessionSecret(): string {
  return process.env.AUTH_SECRET ?? process.env.DASHBOARD_API_KEY ?? "trader-local-session-secret";
}

function toBase64Url(bytes: Uint8Array): string {
  let binary = "";
  for (const byte of bytes) {
    binary += String.fromCharCode(byte);
  }
  return btoa(binary).replaceAll("+", "-").replaceAll("/", "_").replaceAll("=", "");
}

async function sign(value: string): Promise<string> {
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(sessionSecret()),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const signature = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(value));
  return toBase64Url(new Uint8Array(signature));
}

export function isValidPin(pin: unknown): pin is string {
  return typeof pin === "string" && pin === REQUIRED_PIN;
}

export async function createSessionToken(): Promise<string> {
  const expiresAt = Math.floor(Date.now() / 1000) + SESSION_DURATION_SECONDS;
  return `${expiresAt}.${await sign(String(expiresAt))}`;
}

export async function isAuthenticated(token: string | undefined): Promise<boolean> {
  if (!token) {
    return false;
  }

  const [expiresAt, signature, ...extraParts] = token.split(".");
  if (!expiresAt || !signature || extraParts.length > 0 || Number(expiresAt) <= Date.now() / 1000) {
    return false;
  }

  return signature === await sign(expiresAt);
}
