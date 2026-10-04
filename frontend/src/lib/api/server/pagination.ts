import { NextResponse } from "next/server";

/** Header carrying the cursor for the next page; absent on the last page. List bodies stay plain arrays. */
export const NEXT_CURSOR_HEADER = "X-Next-Cursor";

const ID_RE = /^[A-Za-z0-9_-]{1,64}$/;

export type Page = { limit: number; cursor: string | undefined };

/**
 * `?limit=` (1..max, default `def`) and `?cursor=<id of the last row of the previous page>`.
 * Returns a 400 response for malformed values instead of letting them reach Prisma.
 */
export function readPage(url: URL, def: number, max: number): { page: Page; response?: never } | { page?: never; response: NextResponse } {
  const rawLimit = url.searchParams.get("limit");
  const cursor = url.searchParams.get("cursor") ?? undefined;
  const limit = rawLimit == null ? def : Number(rawLimit);
  if (!Number.isInteger(limit) || limit < 1 || limit > max) {
    return { response: NextResponse.json({ error: `limit must be a whole number from 1 to ${max}.` }, { status: 400 }) };
  }
  if (cursor !== undefined && !ID_RE.test(cursor)) {
    return { response: NextResponse.json({ error: "Invalid cursor." }, { status: 400 }) };
  }
  return { page: { limit, cursor } };
}

/** Prisma args for one page: fetch one extra row to learn whether another page exists. */
export function pageArgs({ limit, cursor }: Page) {
  return { take: limit + 1, ...(cursor ? { cursor: { id: cursor }, skip: 1 } : {}) };
}

/** Trim the look-ahead row and answer with the page plus the next cursor header. */
export function pageResponse<Row extends { id: string }, Out>(rows: Row[], { limit }: Page, map: (row: Row) => Out) {
  const more = rows.length > limit;
  const pageRows = more ? rows.slice(0, limit) : rows;
  const res = NextResponse.json(pageRows.map(map));
  if (more) res.headers.set(NEXT_CURSOR_HEADER, pageRows[pageRows.length - 1].id);
  return res;
}
