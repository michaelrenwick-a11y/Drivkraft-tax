import {
  Activity,
  BookOpen,
  FolderOpen,
  HeartHandshake,
  Inbox,
  NotebookPen,
  Send,
  type LucideIcon,
} from "lucide-react";

export type NavItem = {
  href: string;
  label: string;
  icon: LucideIcon;
  /** Palette search terms beyond the label. */
  keywords?: string[];
};

// Sidebar order from planning/05-ux.md (information architecture).
export const NAV: NavItem[] = [
  { href: "/cases", label: "Cases", icon: FolderOpen, keywords: ["clients", "returns", "k-1"] },
  { href: "/inbox", label: "Inbox", icon: Inbox, keywords: ["proposals", "review", "accept"] },
  { href: "/research", label: "Research", icon: BookOpen, keywords: ["bizora", "citations"] },
  { href: "/notes", label: "Notes", icon: NotebookPen, keywords: ["meetings", "transcripts"] },
  { href: "/efile", label: "E-file", icon: Send, keywords: ["batch", "submit", "transmit", "irs", "mef"] },
  { href: "/operator", label: "Operator", icon: Activity, keywords: ["metrics", "usage", "status"] },
  { href: "/credits", label: "Credits", icon: HeartHandshake, keywords: ["license", "open source", "about"] },
];

export function navItemFor(pathname: string): NavItem | undefined {
  return NAV.find((item) => pathname === item.href || pathname.startsWith(`${item.href}/`));
}
