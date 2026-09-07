interface UploadProgressProps {
      progress: number;
}

export default function UploadProgress({progress,}: UploadProgressProps) {
      return (
            <div className="space-y-2">
                  <div className="flex items-center justify-between text-sm text-muted">
                        <span>Uploading...</span>
                        <span>{progress}%</span>
                  </div>

                  <div className="h-2 overflow-hidden rounded-full bg-card">
                        <div className="h-full rounded-full bg-primary transition-all duration-300" style={{width: `${progress}%`,}}>

                        </div>
                  </div>
            </div>
      )
}