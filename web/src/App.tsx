import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom"

import { SiteHeader } from "@/components/site-header"
import { SiteFooter } from "@/components/site-footer"
import { Toaster } from "@/components/ui/sonner"
import { TooltipProvider } from "@/components/ui/tooltip"
import { AskPage } from "@/pages/ask"
import { DashboardPage } from "@/pages/dashboard"
import { InspectPage } from "@/pages/inspect"
import { InspectionDetailPage } from "@/pages/inspection-detail"
import { LandingPage } from "@/pages/landing"
import { RegulationsPage } from "@/pages/regulations"
import { ReviewQueuePage } from "@/pages/review-queue"

export default function App() {
  return (
    <BrowserRouter>
      <TooltipProvider>
        <div className="bg-background flex min-h-svh flex-col">
          <SiteHeader />
          <main className="flex-1">
            <Routes>
              <Route path="/" element={<LandingPage />} />
              <Route path="/inspect" element={<InspectPage />} />
              <Route path="/ask" element={<AskPage />} />
              <Route path="/regulations" element={<RegulationsPage />} />
              <Route path="/queue" element={<ReviewQueuePage />} />
              <Route path="/inspections/:id" element={<InspectionDetailPage />} />
              <Route path="/dashboard" element={<DashboardPage />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </main>
          <SiteFooter />
        </div>
        <Toaster />
      </TooltipProvider>
    </BrowserRouter>
  )
}
