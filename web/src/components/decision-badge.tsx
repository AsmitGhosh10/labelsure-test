import { AlertTriangle, CheckCircle2, CircleSlash, HelpCircle, XCircle } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"
import type { Decision, RuleStatus, Severity } from "@/lib/types"

/**
 * Verdict and rule-status chips.
 *
 * Colour is deliberately not the only signal: each state also carries its own
 * icon and its own words, so the verdict survives greyscale printing and
 * colour-vision deficiency. A compliance verdict read wrongly is worse than an
 * ugly one.
 */

const DECISION_STYLES: Record<Decision, { label: string; className: string; Icon: typeof CheckCircle2 }> = {
  COMPLIANT: {
    label: "Compliant",
    className: "border-emerald-600/30 bg-emerald-600/10 text-emerald-700 dark:text-emerald-400",
    Icon: CheckCircle2,
  },
  NON_COMPLIANT: {
    label: "Non-compliant",
    className: "border-red-600/30 bg-red-600/10 text-red-700 dark:text-red-400",
    Icon: XCircle,
  },
  MANUAL_REVIEW: {
    label: "Manual review",
    className: "border-amber-600/30 bg-amber-600/10 text-amber-700 dark:text-amber-400",
    Icon: AlertTriangle,
  },
}

export function DecisionBadge({
  decision,
  className,
}: {
  decision: Decision | null | undefined
  className?: string
}) {
  if (!decision || !(decision in DECISION_STYLES)) {
    return (
      <Badge variant="outline" className={cn("gap-1.5", className)}>
        <HelpCircle className="size-3.5" />
        Not assessed
      </Badge>
    )
  }
  const { label, className: tone, Icon } = DECISION_STYLES[decision]
  return (
    <Badge variant="outline" className={cn("gap-1.5 font-medium", tone, className)}>
      <Icon className="size-3.5" />
      {label}
    </Badge>
  )
}

const STATUS_STYLES: Record<RuleStatus, { label: string; className: string }> = {
  PASS: {
    label: "Pass",
    className: "border-emerald-600/30 bg-emerald-600/10 text-emerald-700 dark:text-emerald-400",
  },
  FAIL: {
    label: "Fail",
    className: "border-red-600/30 bg-red-600/10 text-red-700 dark:text-red-400",
  },
  MANUAL_REVIEW: {
    label: "Manual review",
    className: "border-amber-600/30 bg-amber-600/10 text-amber-700 dark:text-amber-400",
  },
  NOT_APPLICABLE: { label: "Not applicable", className: "text-muted-foreground" },
  UNVERIFIED: {
    label: "Unverified rule",
    className: "border-sky-600/30 bg-sky-600/10 text-sky-700 dark:text-sky-400",
  },
}

export function RuleStatusBadge({ status }: { status: RuleStatus }) {
  const style = STATUS_STYLES[status] ?? {
    label: status,
    className: "text-muted-foreground",
  }
  return (
    <Badge variant="outline" className={cn("font-medium", style.className)}>
      {status === "NOT_APPLICABLE" ? <CircleSlash className="size-3.5" /> : null}
      {style.label}
    </Badge>
  )
}

const SEVERITY_TONE: Record<string, string> = {
  CRITICAL: "border-red-600/40 bg-red-600/10 text-red-700 dark:text-red-400",
  HIGH: "border-orange-600/40 bg-orange-600/10 text-orange-700 dark:text-orange-400",
  MEDIUM: "border-amber-600/40 bg-amber-600/10 text-amber-700 dark:text-amber-400",
  LOW: "text-muted-foreground",
}

export function SeverityBadge({ severity }: { severity: Severity }) {
  return (
    <Badge
      variant="outline"
      className={cn("font-medium", SEVERITY_TONE[severity] ?? "text-muted-foreground")}
    >
      {severity}
    </Badge>
  )
}
