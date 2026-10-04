import { randomBytes, scrypt, timingSafeEqual } from "node:crypto";
import { promisify } from "node:util";

// Node's built-in scrypt — no native bcrypt/argon2 build step on Windows.
// Stored format: "scrypt$<salt hex>$<hash hex>".
const scryptAsync = promisify(scrypt) as (password: string, salt: Buffer, keylen: number) => Promise<Buffer>;
const KEY_LEN = 64;

export async function hashPassword(password: string): Promise<string> {
  const salt = randomBytes(16);
  const hash = await scryptAsync(password, salt, KEY_LEN);
  return `scrypt$${salt.toString("hex")}$${hash.toString("hex")}`;
}

export async function verifyPassword(password: string, stored: string): Promise<boolean> {
  const [scheme, saltHex, hashHex] = stored.split("$");
  if (scheme !== "scrypt" || !saltHex || !hashHex) return false;
  const expected = Buffer.from(hashHex, "hex");
  const actual = await scryptAsync(password, Buffer.from(saltHex, "hex"), expected.length);
  return timingSafeEqual(actual, expected);
}

// A fixed, valid hash of a random secret: comparing against it costs the same scrypt as a real account.
const DUMMY_HASH = `scrypt$${"0".repeat(32)}$${"0".repeat(KEY_LEN * 2)}`;

/** Constant-work stand-in for verifyPassword when the account doesn't exist (always false). */
export async function verifyDummyPassword(password: string): Promise<false> {
  await verifyPassword(password, DUMMY_HASH);
  return false;
}
