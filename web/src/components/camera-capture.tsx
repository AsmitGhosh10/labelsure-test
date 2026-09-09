import { useCallback, useEffect, useRef, useState } from "react"
import { Camera, CameraOff, RefreshCw, SwitchCamera } from "lucide-react"

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
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
import { Spinner } from "@/components/ui/spinner"

/**
 * Photograph a package surface with the device camera.
 *
 * Uses `getUserMedia` and a canvas rather than a capture library: the browser
 * already does all of this, and a dependency here would buy nothing.
 *
 * Two things matter more than they look. The stream is stopped on every exit
 * path, because a camera left running keeps the hardware indicator lit and
 * reads as spyware. And capture requests the highest resolution the device
 * will give, because the declarations being read are small print — a 640×480
 * frame produces OCR failures that look like compliance findings.
 */

type Facing = "environment" | "user"

function describeError(error: unknown): string {
  if (!(error instanceof Error)) return "The camera could not be started."
  switch (error.name) {
    case "NotAllowedError":
    case "SecurityError":
      return "Camera access was refused. Allow it for this site in your browser, then try again."
    case "NotFoundError":
    case "OverconstrainedError":
      return "No camera was found on this device."
    case "NotReadableError":
      return "The camera is already in use by another application."
    default:
      return `The camera could not be started (${error.name}).`
  }
}

export function CameraCapture({
  onCapture,
  disabled,
}: {
  onCapture: (file: File) => void
  disabled?: boolean
}) {
  const [open, setOpen] = useState(false)
  const [facing, setFacing] = useState<Facing>("environment")
  const [error, setError] = useState<string | null>(null)
  const [ready, setReady] = useState(false)
  const videoRef = useRef<HTMLVideoElement>(null)
  const streamRef = useRef<MediaStream | null>(null)

  const stop = useCallback(() => {
    streamRef.current?.getTracks().forEach((track) => track.stop())
    streamRef.current = null
    setReady(false)
  }, [])

  const start = useCallback(
    async (mode: Facing) => {
      stop()
      setError(null)
      // getUserMedia only exists in a secure context. Over plain HTTP on a
      // hostname other than localhost the API is simply absent, which would
      // otherwise surface as an unhelpful TypeError.
      if (!navigator.mediaDevices?.getUserMedia) {
        setError(
          "This browser will not open a camera on an insecure connection. Use HTTPS, or localhost.",
        )
        return
      }
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          video: {
            facingMode: mode,
            width: { ideal: 1920 },
            height: { ideal: 1920 },
          },
          audio: false,
        })
        streamRef.current = stream
        if (videoRef.current) {
          videoRef.current.srcObject = stream
          await videoRef.current.play().catch(() => {
            /* autoplay refusal is not fatal; the frame still renders */
          })
        }
        setReady(true)
      } catch (err) {
        setError(describeError(err))
      }
    },
    [stop],
  )

  useEffect(() => {
    if (open) void start(facing)
    else stop()
    return stop
  }, [open, facing, start, stop])

  function capture() {
    const video = videoRef.current
    if (!video || !video.videoWidth) return

    const canvas = document.createElement("canvas")
    canvas.width = video.videoWidth
    canvas.height = video.videoHeight
    const context = canvas.getContext("2d")
    if (!context) return
    context.drawImage(video, 0, 0, canvas.width, canvas.height)

    canvas.toBlob(
      (blob) => {
        if (!blob) return
        const stamp = new Date().toISOString().replace(/[:.]/g, "-")
        onCapture(new File([blob], `capture-${stamp}.jpg`, { type: "image/jpeg" }))
        setOpen(false)
      },
      "image/jpeg",
      // Below about 0.9 the compression starts eating the thin strokes in
      // small declaration text, which costs OCR accuracy.
      0.92,
    )
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button type="button" variant="outline" size="sm" disabled={disabled}>
          <Camera />
          Use camera
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Photograph a surface</DialogTitle>
          <DialogDescription>
            Fill the frame with the label, hold steady, and avoid glare across the
            printed declarations.
          </DialogDescription>
        </DialogHeader>

        {error ? (
          <Alert variant="destructive">
            <CameraOff />
            <AlertTitle>Camera unavailable</AlertTitle>
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        ) : (
          <div className="bg-muted relative overflow-hidden rounded-md">
            <video
              ref={videoRef}
              playsInline
              muted
              autoPlay
              className="aspect-video w-full object-contain"
            />
            {!ready && (
              <div className="text-muted-foreground absolute inset-0 flex items-center justify-center gap-2 text-sm">
                <Spinner />
                Starting the camera…
              </div>
            )}
          </div>
        )}

        <DialogFooter className="sm:justify-between">
          <div className="flex gap-2">
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() =>
                setFacing(facing === "environment" ? "user" : "environment")
              }
              disabled={!!error}
            >
              <SwitchCamera />
              Switch camera
            </Button>
            {error && (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => void start(facing)}
              >
                <RefreshCw />
                Retry
              </Button>
            )}
          </div>
          <Button type="button" onClick={capture} disabled={!ready}>
            <Camera />
            Take photo
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
