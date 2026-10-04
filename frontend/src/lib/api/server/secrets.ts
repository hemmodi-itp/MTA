import { createCipheriv, createHash, randomBytes } from "node:crypto";

/**
 * AES-256-GCM for live-app test credentials. Format and key derivation match
 * tools/agent_eval/secrets_box.py: base64url(iv[12] ‖ ciphertext ‖ tag[16]), key = SHA-256(AQP_SECRET_KEY).
 * The web app only ever encrypts; the evaluation service decrypts at run time.
 */
export function encryptJson(value: unknown): string {
  const secret = process.env.AQP_SECRET_KEY;
  if (!secret) throw new Error("AQP_SECRET_KEY is not set");
  const key = createHash("sha256").update(secret, "utf8").digest();
  const iv = randomBytes(12);
  const cipher = createCipheriv("aes-256-gcm", key, iv);
  const ct = Buffer.concat([cipher.update(JSON.stringify(value), "utf8"), cipher.final()]);
  return Buffer.concat([iv, ct, cipher.getAuthTag()]).toString("base64url");
}
