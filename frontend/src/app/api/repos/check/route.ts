import { NextResponse } from "next/server";
import { checkPublicRepo } from "@/lib/api/server/github";
import { requireUser } from "@/lib/api/server/access";

/** Instant "is this repo public?" check for the New Project form. Signed-in users only (it spends GitHub quota). */
export async function GET(request: Request) {
  const { response } = await requireUser();
  if (response) return response;
  const url = new URL(request.url).searchParams.get("url") ?? "";
  return NextResponse.json(await checkPublicRepo(url));
}
