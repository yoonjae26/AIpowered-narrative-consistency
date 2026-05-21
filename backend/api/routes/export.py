from fastapi import APIRouter, Response
from pydantic import BaseModel, Field


router = APIRouter(prefix="/export", tags=["export"])


class ExportRequest(BaseModel):
	title: str = Field(min_length=1)
	content: str = Field(min_length=1)


@router.post("/markdown")
def export_markdown(request: ExportRequest) -> Response:
	body = f"# {request.title}\n\n{request.content}\n"
	return Response(content=body, media_type="text/markdown; charset=utf-8")


@router.post("/text")
def export_text(request: ExportRequest) -> Response:
	return Response(content=request.content, media_type="text/plain; charset=utf-8")
