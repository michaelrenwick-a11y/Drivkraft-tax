import { Inbox } from "lucide-react";
import type { Metadata } from "next";
import { Kbd } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { StatusPill } from "@/components/ui/status-pill";

export const metadata: Metadata = { title: "Inbox" };

export default function InboxPage() {
  return (
    <EmptyState
      icon={Inbox}
      title="Nothing waiting for review"
      action={<StatusPill kind="proposal" label="AI proposals land here" />}
      footer={
        <p className="flex items-center justify-center gap-2 text-xs text-fg-muted">
          <Kbd>⏎</Kbd> accept <span aria-hidden>·</span> <Kbd>⌫</Kbd> reject <span aria-hidden>·</span> undo is always
          available
        </p>
      }
    >
      Suggestions from chat, meeting notes and workpaper imports show up here as proposals. Nothing touches your data
      until you accept it.
    </EmptyState>
  );
}
