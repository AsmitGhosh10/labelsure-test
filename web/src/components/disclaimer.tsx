import { Scale } from "lucide-react"

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { cn } from "@/lib/utils"

export const SYSTEM_ROLE = "AI-assisted compliance screening"

export const SHORT_DISCLAIMER =
  "AI-assisted compliance screening — not a statutory inspection."

const FULL_DISCLAIMER =
  "This screening is a decision-support aid for a human inspector. It highlights " +
  "likely declaration issues under the Legal Metrology (Packaged Commodities) " +
  "Rules, 2011 from photographs of the package. It does not constitute automated " +
  "legal enforcement, does not replace statutory inspection, and carries no legal " +
  "finding of contravention. Every finding must be verified by an authorised " +
  "inspector before any action is taken."

/**
 * The statutory-posture banner.
 *
 * Every surface that shows a verdict has to carry this. It is intentionally not
 * dismissible: the point is that a reader never sees a verdict without it.
 */
export function Disclaimer({
  text,
  className,
}: {
  text?: string | null
  className?: string
}) {
  return (
    <Alert className={cn("border-amber-600/30 bg-amber-600/5", className)}>
      <Scale className="text-amber-700 dark:text-amber-500" />
      <AlertTitle className="text-amber-800 dark:text-amber-400">
        {SYSTEM_ROLE.toUpperCase()}
      </AlertTitle>
      <AlertDescription>{text || FULL_DISCLAIMER}</AlertDescription>
    </Alert>
  )
}
