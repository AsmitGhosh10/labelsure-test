import { useEffect, useState } from "react"
import { LogIn, LogOut } from "lucide-react"
import { toast } from "sonner"

import { api, ApiError, token } from "@/lib/api"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { Spinner } from "@/components/ui/spinner"

/**
 * Sign-in for deployments that enable authentication.
 *
 * When the backend reports auth disabled, this renders nothing: showing a
 * login box that gates nothing would be a lie about the deployment's posture.
 * Credentials are posted straight to the backend and only the returned token
 * is retained, in `sessionStorage`.
 */
export function SignInDialog() {
  const [authEnabled, setAuthEnabled] = useState<boolean | null>(null)
  const [open, setOpen] = useState(false)
  const [username, setUsername] = useState("")
  const [password, setPassword] = useState("")
  const [busy, setBusy] = useState(false)
  const [signedIn, setSignedIn] = useState(() => Boolean(token.get()))

  useEffect(() => {
    api
      .authStatus()
      .then((status) => setAuthEnabled(status.enabled))
      .catch(() => setAuthEnabled(false))
  }, [])

  if (!authEnabled) return null

  if (signedIn) {
    return (
      <Button
        variant="ghost"
        size="sm"
        onClick={() => {
          token.set(null)
          setSignedIn(false)
          toast.success("Signed out")
        }}
      >
        <LogOut />
        Sign out
      </Button>
    )
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    setBusy(true)
    try {
      const result = await api.login(username, password)
      token.set(result.access_token)
      setSignedIn(true)
      setOpen(false)
      setPassword("")
      toast.success(`Signed in as ${username} (${result.role})`)
    } catch (error) {
      toast.error(
        error instanceof ApiError ? error.message : "Could not reach the server",
      )
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="ghost" size="sm">
          <LogIn />
          Sign in
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-sm">
        <form onSubmit={submit}>
          <DialogHeader>
            <DialogTitle>Sign in</DialogTitle>
            <DialogDescription>
              Inspector, supervisor and administrator roles gate different parts of
              this tool.
            </DialogDescription>
          </DialogHeader>
          <FieldGroup className="py-4">
            <Field>
              <FieldLabel htmlFor="username">Username</FieldLabel>
              <Input
                id="username"
                autoComplete="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required
              />
            </Field>
            <Field>
              <FieldLabel htmlFor="password">Password</FieldLabel>
              <Input
                id="password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </Field>
          </FieldGroup>
          <DialogFooter>
            <Button type="submit" disabled={busy}>
              {busy ? <Spinner data-icon /> : <LogIn />}
              Sign in
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
