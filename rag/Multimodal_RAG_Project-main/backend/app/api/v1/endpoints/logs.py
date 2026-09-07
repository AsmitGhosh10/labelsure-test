from fastapi import HTTPException, Query, APIRouter
from pathlib import Path
import json

router = APIRouter(tags=["logs"])

LOG_FILE_PATH = Path("logs/app.log")

@router.get("/logs")
async def get_logs(limit: int = Query(50, ge = 1, le = 100)):
      """
      Fetch last N log lines (Default = 50, Limit = 100)
      """

      if not LOG_FILE_PATH: 
            raise HTTPException(status_code=404, detail="Log file not found")
      
      try:
            with LOG_FILE_PATH.open("r", encoding = "utf-8", errors="replace") as f:
                  lines = f.readlines()
            #=====================
            #Make structured logs
            #=====================
            parsed_logs = []
            for line in lines[-limit:]:
                  try:
                        parsed_logs.append(json.loads(line))
                  except:
                        parsed_logs.append({"raw": line.strip()})

            return {
                  "total_lines": len(lines),
                  "returned_lines": min(limit, len(lines)),
                  "logs": parsed_logs
            }
      except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))