"use client";

import * as Tooltip from "@radix-ui/react-tooltip";
import { FileCode2 } from "lucide-react";
import type { ReactNode } from "react";
import type { Evidence } from "@/lib/api";
import { cn } from "@/lib/cn";

export type PageSize = [number, number];

export function pageUrl(docId: string, page: number) {
  return `/api/docs/${docId}/pages/${page}.png`;
}

/**
 * The PDF region a value was read from, cropped out of the rendered page with
 * CSS (no second image request). Coordinates are PDF points, top-left origin.
 */
export function EvidenceCrop({
  docId,
  evidence,
  pageSize,
  width = 280,
  className,
}: {
  docId: string;
  evidence: Evidence;
  pageSize: PageSize;
  width?: number;
  className?: string;
}) {
  if (!evidence.bbox) return null;
  const [x0, y0, x1, y1] = evidence.bbox;
  const pad = 6;
  const bw = x1 - x0 + pad * 2;
  const bh = y1 - y0 + pad * 2;
  const scale = width / bw;
  const height = Math.min(bh * scale, 140);
  return (
    <div
      role="img"
      aria-label={`PDF page ${evidence.page}, where the value was read${evidence.text ? `: ${evidence.text.replace(/\n/g, ", ")}` : ""}`}
      className={cn("overflow-hidden rounded-md border border-border bg-white", className)}
      style={{
        width,
        height,
        backgroundImage: `url(${pageUrl(docId, evidence.page)})`,
        backgroundRepeat: "no-repeat",
        backgroundSize: `${pageSize[0] * scale}px ${pageSize[1] * scale}px`,
        backgroundPosition: `${-(x0 - pad) * scale}px ${-(y0 - pad) * scale}px`,
      }}
    />
  );
}

/**
 * Source peek (05-ux signature interaction): hover or focus a figure to see
 * where it came from. Click behavior belongs to the caller (it selects the row
 * and pans the PDF).
 */
export function SourcePeek({
  docId,
  evidence,
  pageSize,
  label,
  hasPdf,
  children,
}: {
  docId: string;
  evidence: Evidence | null;
  pageSize: PageSize | null;
  label: string;
  hasPdf: boolean;
  children: ReactNode;
}) {
  return (
    <Tooltip.Root delayDuration={250}>
      <Tooltip.Trigger asChild>{children}</Tooltip.Trigger>
      <Tooltip.Portal>
        <Tooltip.Content
          side="left"
          align="center"
          sideOffset={10}
          collisionPadding={12}
          className="z-50 w-[304px] animate-fade-in rounded-lg border border-border bg-surface p-3 shadow-overlay"
        >
          <p className="text-xs font-medium text-fg">{label}</p>
          {evidence?.bbox && pageSize && hasPdf ? (
            <>
              <EvidenceCrop docId={docId} evidence={evidence} pageSize={pageSize} className="mt-2" />
              <p className="mt-2 flex items-center justify-between gap-2 text-[11px] text-fg-muted">
                <span>
                  Page {evidence.page}
                  {evidence.status && evidence.status !== "present" && <> · {evidence.status.replace(/_/g, " ")}</>}
                </span>
                <span>{evidence.match === "box" ? "Code is on a statement" : "Click to show on the PDF"}</span>
              </p>
            </>
          ) : (
            <p className="mt-1.5 flex items-start gap-2 text-xs leading-5 text-fg-muted">
              <FileCode2 className="mt-0.5 size-3.5 shrink-0" aria-hidden />
              {hasPdf
                ? "The extractor recorded no PDF location for this value (statement detail or absent from the face)."
                : "This K-1 came in as an OTD document, so there's no PDF to point at. The OTD path is its source."}
            </p>
          )}
        </Tooltip.Content>
      </Tooltip.Portal>
    </Tooltip.Root>
  );
}
