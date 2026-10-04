import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import type { AgentProfile } from "@/lib/types";

/** Gemini's read of the repository: what the agent is for and how MTA talks to it. */
export function AgentProfileCard({ profile }: { profile: AgentProfile }) {
  const iface = profile.interface ?? {};
  const endpoints = iface.endpoints ?? [];
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm font-medium text-muted-foreground">
          Agent profile{profile.agent_name ? ` · ${profile.agent_name}` : ""}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        {profile.purpose && <p>{profile.purpose}</p>}
        <div className="grid gap-4 sm:grid-cols-2">
          <List label="Capabilities" items={profile.capabilities} />
          <List label="Out of scope" items={profile.out_of_scope} />
          <List label="Tools & integrations" items={profile.tools_and_integrations} />
          <div className="space-y-1">
            <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">Interface</p>
            <p>
              {iface.type ?? "unknown"}
              {iface.framework && iface.framework !== "unknown" ? ` · ${iface.framework}` : ""}
            </p>
            {endpoints.slice(0, 4).map((e, i) => (
              <p key={i} className="font-mono text-xs text-muted-foreground">
                {e.method ?? "POST"} {e.path}
              </p>
            ))}
          </div>
        </div>
        {(profile.tech_stack?.length ?? 0) > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {profile.tech_stack!.map((t) => (
              <Badge key={t} variant="secondary" className="font-normal">{t}</Badge>
            ))}
          </div>
        )}
        {(profile.observed_risks?.length ?? 0) > 0 && (
          <List label="Risks spotted in the code" items={profile.observed_risks} tone="text-critical" />
        )}
      </CardContent>
    </Card>
  );
}

function List({ label, items, tone }: { label: string; items?: string[]; tone?: string }) {
  if (!items?.length) return null;
  return (
    <div className="space-y-1">
      <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">{label}</p>
      <ul className={`list-disc space-y-0.5 pl-5 ${tone ?? "text-muted-foreground"}`}>
        {items.slice(0, 8).map((item, i) => (
          <li key={i}>{item}</li>
        ))}
      </ul>
    </div>
  );
}
