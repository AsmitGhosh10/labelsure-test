import { SHORT_DISCLAIMER } from "@/components/disclaimer"

export function SiteFooter() {
  return (
    <footer className="border-t">
      <div className="text-muted-foreground mx-auto flex w-full max-w-6xl flex-col gap-2 px-4 py-6 text-sm sm:flex-row sm:items-center sm:justify-between">
        <p>LabelSure — Legal Metrology (Packaged Commodities) Rules, 2011 screening.</p>
        <p>{SHORT_DISCLAIMER}</p>
      </div>
    </footer>
  )
}
