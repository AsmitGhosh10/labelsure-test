from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ....core.dependencies import get_db
from ....ml.ranking.explainability import ExplainabilityModule
from ....schemas.explain import ExplainResponse
from ....schemas.query import QueryRequest

router = APIRouter(tags=["explain"])

explain_module = ExplainabilityModule()

@router.post("/explain", response_model=ExplainResponse)
async def explain_ranking(
    request: QueryRequest,           
    db: AsyncSession = Depends(get_db)
):
    """Get detailed explanation of ranking decisions."""
    explanation = await explain_module.explain_ranking(request.query,db, request.k)
    return ExplainResponse(**explanation)

