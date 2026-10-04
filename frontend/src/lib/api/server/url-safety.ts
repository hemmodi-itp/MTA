import { lookup } from "node:dns/promises";
import { isIP } from "node:net";
import { liveUrlSyntaxError } from "@/lib/validation/project";

/**
 * SSRF guard for the live-app URL MTA will drive a browser and HTTP client against. Only the public internet is a
 * valid target: no localhost / *.local / *.internal names, and no private, loopback, link-local (incl. the cloud
 * metadata address 169.254.169.254), CGNAT, multicast, unspecified or IPv6 ULA / link-local addresses — neither as
 * a literal nor as what the hostname resolves to. The evaluation service enforces the same policy independently.
 *
 * AQP_ALLOW_PRIVATE_TARGETS=1 lifts the address rules (local development against an app on your own machine).
 */

const BLOCKED_NAME = /(^|\.)(localhost|local|internal|localdomain|home\.arpa)$/i;

/** [network, prefix length] in IPv4 dotted form. */
const BLOCKED_V4: [string, number][] = [
  ["0.0.0.0", 8], // "this network" / unspecified
  ["10.0.0.0", 8],
  ["100.64.0.0", 10], // CGNAT
  ["127.0.0.0", 8],
  ["169.254.0.0", 16], // link-local, cloud metadata
  ["172.16.0.0", 12],
  ["192.0.0.0", 24],
  ["192.0.2.0", 24],
  ["192.168.0.0", 16],
  ["198.18.0.0", 15],
  ["198.51.100.0", 24],
  ["203.0.113.0", 24],
  ["224.0.0.0", 4], // multicast
  ["240.0.0.0", 4], // reserved + broadcast
];

function v4ToInt(ip: string): number {
  return ip.split(".").reduce((n, part) => (n << 8) + Number(part), 0) >>> 0;
}

function isBlockedV4(ip: string): boolean {
  const n = v4ToInt(ip);
  return BLOCKED_V4.some(([net, bits]) => {
    const mask = bits === 0 ? 0 : (~0 << (32 - bits)) >>> 0;
    return (n & mask) === (v4ToInt(net) & mask);
  });
}

/** Eight 16-bit groups of an IPv6 address (handles "::" and a trailing dotted IPv4). */
function v6Groups(ip: string): number[] | null {
  let addr = ip.toLowerCase().split("%")[0];
  const v4 = addr.match(/(\d+\.\d+\.\d+\.\d+)$/);
  if (v4) {
    const n = v4ToInt(v4[1]);
    addr = addr.slice(0, -v4[1].length) + `${(n >>> 16).toString(16)}:${(n & 0xffff).toString(16)}`;
  }
  const [head, tail] = addr.split("::");
  const h = head ? head.split(":") : [];
  const t = tail !== undefined && tail ? tail.split(":") : [];
  const fill = addr.includes("::") ? 8 - h.length - t.length : 0;
  const groups = [...h, ...Array(fill).fill("0"), ...t].map((g) => parseInt(g, 16));
  return groups.length === 8 && groups.every((g) => Number.isInteger(g) && g >= 0 && g <= 0xffff) ? groups : null;
}

function isBlockedV6(ip: string): boolean {
  const g = v6Groups(ip);
  if (!g) return true; // unparseable: refuse rather than guess
  const embedded = (hi: number, lo: number) => `${hi >> 8}.${hi & 0xff}.${lo >> 8}.${lo & 0xff}`;
  if (g.every((x) => x === 0)) return true; // ::
  if (g.slice(0, 7).every((x) => x === 0) && g[7] === 1) return true; // ::1
  if ((g[0] & 0xfe00) === 0xfc00) return true; // fc00::/7 unique local
  if ((g[0] & 0xffc0) === 0xfe80 || (g[0] & 0xffc0) === 0xfec0) return true; // link-local, old site-local
  if ((g[0] & 0xff00) === 0xff00) return true; // multicast
  if (g[0] === 0x100 && g[1] === 0 && g[2] === 0 && g[3] === 0) return true; // 100::/64 discard
  // IPv4-mapped / -compatible (::ffff:a.b.c.d, ::a.b.c.d) and NAT64 (64:ff9b::a.b.c.d): judge the IPv4 inside
  if (g.slice(0, 5).every((x) => x === 0) && (g[5] === 0xffff || g[5] === 0)) return isBlockedV4(embedded(g[6], g[7]));
  if (g[0] === 0x64 && g[1] === 0xff9b) return isBlockedV4(embedded(g[6], g[7]));
  if (g[0] === 0x2002) return isBlockedV4(embedded(g[1], g[2])); // 6to4
  return false;
}

export function isPrivateAddress(ip: string): boolean {
  const kind = isIP(ip);
  if (kind === 4) return isBlockedV4(ip);
  if (kind === 6) return isBlockedV6(ip);
  return true;
}

export const privateTargetsAllowed = () => process.env.AQP_ALLOW_PRIVATE_TARGETS === "1";

const PUBLIC_ONLY =
  "MTA only tests apps reachable on the public internet. Deploy the app (or expose it through a public tunnel) and use that URL.";

async function resolveAll(host: string): Promise<string[]> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  const timeout = new Promise<never>((_, reject) => {
    timer = setTimeout(() => reject(new Error("timeout")), 5000);
  });
  try {
    const found = await Promise.race([lookup(host, { all: true, verbatim: true }), timeout]);
    return found.map((a) => a.address);
  } finally {
    clearTimeout(timer);
  }
}

/** null when the URL is an allowed target, otherwise the message to show under the Live URL field. */
export async function checkLiveUrl(value: string): Promise<string | null> {
  const syntax = liveUrlSyntaxError(value);
  if (syntax) return syntax;
  if (privateTargetsAllowed()) return null;

  const host = new URL(value).hostname.replace(/^\[|\]$/g, "").replace(/\.$/, "");
  if (BLOCKED_NAME.test(host)) return `${host} is a local network name. ${PUBLIC_ONLY}`;
  if (isIP(host)) return isPrivateAddress(host) ? `${host} is a private or reserved address. ${PUBLIC_ONLY}` : null;

  let addresses: string[];
  try {
    addresses = await resolveAll(host);
  } catch {
    return `Couldn't resolve ${host}. Check the URL and that the app is deployed.`;
  }
  if (!addresses.length) return `Couldn't resolve ${host}. Check the URL and that the app is deployed.`;
  if (addresses.some(isPrivateAddress)) return `${host} points to a private or reserved address. ${PUBLIC_ONLY}`;
  return null;
}
