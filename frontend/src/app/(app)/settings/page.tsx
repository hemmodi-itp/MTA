"use client";

import { Bell, Gauge, KeyRound } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { EmptyState } from "@/components/shared/empty-state";
import { PageHeader } from "@/components/shared/page-header";
import { SectionCard } from "@/components/shared/section-card";
import { useCurrentUser } from "@/components/shell/current-user";

/** Shown next to controls that have no backend yet, so nothing on this page pretends to work. */
function NotYet() {
  return <Badge variant="outline" className="font-normal text-muted-foreground">Not available yet</Badge>;
}

export default function SettingsPage() {
  const user = useCurrentUser();

  return (
    <>
      <PageHeader title="Settings" description="Your account. Workspace settings, API access and plans are on the way." />

      <Tabs defaultValue="profile" className="max-w-3xl">
        <div className="no-scrollbar overflow-x-auto">
          <TabsList className="w-max">
            <TabsTrigger value="profile">Profile</TabsTrigger>
            <TabsTrigger value="api-keys">API keys</TabsTrigger>
            <TabsTrigger value="notifications">Notifications</TabsTrigger>
            <TabsTrigger value="usage">Usage &amp; plan</TabsTrigger>
          </TabsList>
        </div>

        <TabsContent value="profile" className="mt-4">
          <SectionCard title="Profile" action={<NotYet />}>
            <div className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="name">Full name</Label>
                <Input id="name" defaultValue={user?.name ?? ""} placeholder="Your name" readOnly aria-describedby="profile-note" />
              </div>
              <div className="space-y-2">
                <Label htmlFor="email">Email</Label>
                <Input id="email" defaultValue={user?.email ?? ""} disabled />
              </div>
              <div className="flex flex-wrap items-center gap-3 pt-1">
                <Button disabled>Save changes</Button>
                <p id="profile-note" className="text-xs text-muted-foreground">Editing your profile isn&apos;t available yet.</p>
              </div>
            </div>
          </SectionCard>
        </TabsContent>

        <TabsContent value="api-keys" className="mt-4">
          <SectionCard title="API keys" action={<NotYet />}>
            <EmptyState size="inline" icon={KeyRound} title="No API keys"
              description="Keys for triggering evaluations from CI will be created here once API access is available." />
          </SectionCard>
        </TabsContent>

        <TabsContent value="notifications" className="mt-4">
          <SectionCard title="Notifications" action={<NotYet />}>
            <EmptyState size="inline" icon={Bell} title="In-app only for now"
              description="Run updates appear under the bell in the top bar. Email alerts on failures and completed runs are planned." />
          </SectionCard>
        </TabsContent>

        <TabsContent value="usage" className="mt-4">
          <SectionCard title="Usage & plan" action={<NotYet />}>
            <EmptyState size="inline" icon={Gauge} title="No usage limits"
              description="Plans and evaluation-minute tracking aren't set up yet, so there is nothing to show here." />
          </SectionCard>
        </TabsContent>
      </Tabs>
    </>
  );
}
