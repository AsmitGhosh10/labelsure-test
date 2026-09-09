import { useState } from "react"
import { Check, Gavel } from "lucide-react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  Field,
  FieldDescription,
  FieldGroup,
  FieldLabel,
  FieldSet,
} from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Spinner } from "@/components/ui/spinner"
import { ToggleGroupField } from "@/components/toggle-group-field"
import { api, ApiError, token } from "@/lib/api"
import type { Inspection } from "@/lib/types"

/**
 * Human sign-off on an automated finding (accept or override).
 *
 * The reason is mandatory and an override must name the decision that replaces
 * the automated one, because the audit trail is the point: a verdict that
 * changed without a recorded reason is worse than no verdict.
 */
export function SignOffCard({ inspection }: { inspection: Inspection }) {
  const [action, setAction] = useState<"ACCEPT" | "OVERRIDE">("ACCEPT")
  const [reason, setReason] = useState("")
  const [finalDecision, setFinalDecision] = useState("")
  const [inspectorId, setInspectorId] = useState("")
  const [inspectorName, setInspectorName] = useState("")
  const [busy, setBusy] = useState(false)
  const [recorded, setRecorded] = useState<string | null>(null)

  const authed = Boolean(token.get())
  const reasonTooShort = reason.trim().length < 10
  const overrideMissing = action === "OVERRIDE" && !finalDecision
  const idMissing = !authed && !inspectorId.trim()

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    setBusy(true)
    try {
      await api.recordDecision(inspection.inspection_id, {
        action,
        reason: reason.trim(),
        final_decision: action === "OVERRIDE" ? finalDecision : undefined,
        inspector_id: authed ? undefined : inspectorId.trim(),
        inspector_name: inspectorName.trim() || undefined,
      })
      setRecorded(action)
      toast.success(
        action === "ACCEPT" ? "Finding accepted" : "Finding overridden and recorded",
      )
    } catch (error) {
      toast.error(
        error instanceof ApiError ? error.message : "Could not record the decision",
      )
    } finally {
      setBusy(false)
    }
  }

  if (recorded) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Check className="text-emerald-600" />
            Decision recorded
          </CardTitle>
          <CardDescription>
            This inspection has been {recorded === "ACCEPT" ? "accepted" : "overridden"}{" "}
            and written to the audit log.
          </CardDescription>
        </CardHeader>
      </Card>
    )
  }

  return (
    <Card>
      <form onSubmit={submit}>
        <CardHeader>
          <CardTitle>Inspector sign-off</CardTitle>
          <CardDescription>
            The automated verdict is a recommendation. Nothing is final until an
            authorised inspector accepts or overrides it here.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <FieldGroup>
            <FieldSet>
              <ToggleGroupField
                label="Action"
                value={action}
                onValueChange={(value) => setAction(value as "ACCEPT" | "OVERRIDE")}
                options={[
                  { value: "ACCEPT", label: "Accept the finding" },
                  { value: "OVERRIDE", label: "Override it" },
                ]}
              />
            </FieldSet>

            {action === "OVERRIDE" && (
              <Field data-invalid={overrideMissing || undefined}>
                <FieldLabel htmlFor="final-decision">Corrected decision</FieldLabel>
                <Select value={finalDecision} onValueChange={setFinalDecision}>
                  <SelectTrigger
                    id="final-decision"
                    aria-invalid={overrideMissing || undefined}
                  >
                    <SelectValue placeholder="Choose the decision that replaces it" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectGroup>
                      <SelectItem value="COMPLIANT">Compliant</SelectItem>
                      <SelectItem value="NON_COMPLIANT">Non-compliant</SelectItem>
                      <SelectItem value="MANUAL_REVIEW">Manual review</SelectItem>
                    </SelectGroup>
                  </SelectContent>
                </Select>
                <FieldDescription>
                  Required for an override. The automated verdict was{" "}
                  {inspection.decision ?? "not assessed"}.
                </FieldDescription>
              </Field>
            )}

            <Field data-invalid={reasonTooShort || undefined}>
              <FieldLabel htmlFor="reason">Reason</FieldLabel>
              <Textarea
                id="reason"
                rows={3}
                aria-invalid={reasonTooShort || undefined}
                placeholder="What did you verify against the physical package?"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
              />
              <FieldDescription>
                Recorded in the audit log against your identity. At least 10 characters.
              </FieldDescription>
            </Field>

            {!authed && (
              <Field data-invalid={idMissing || undefined}>
                <FieldLabel htmlFor="inspector-id">Inspector identifier</FieldLabel>
                <Input
                  id="inspector-id"
                  aria-invalid={idMissing || undefined}
                  value={inspectorId}
                  onChange={(e) => setInspectorId(e.target.value)}
                />
                <FieldDescription>
                  Required because this deployment has authentication switched off.
                  With authentication on, the signed-in identity is used instead and
                  cannot be overridden here.
                </FieldDescription>
              </Field>
            )}

            <Field>
              <FieldLabel htmlFor="inspector-name">Inspector name (optional)</FieldLabel>
              <Input
                id="inspector-name"
                value={inspectorName}
                onChange={(e) => setInspectorName(e.target.value)}
              />
            </Field>
          </FieldGroup>
        </CardContent>
        <CardFooter>
          <Button
            type="submit"
            disabled={busy || reasonTooShort || overrideMissing || idMissing}
          >
            {busy ? <Spinner data-icon /> : <Gavel />}
            Record decision
          </Button>
        </CardFooter>
      </form>
    </Card>
  )
}
