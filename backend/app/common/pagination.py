from pydantic import BaseModel, Field


class PageParams(BaseModel):
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)


class PageResult(BaseModel):
    items: list
    total: int
    page: int
    page_size: int
