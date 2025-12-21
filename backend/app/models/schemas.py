from pydantic import BaseModel


class FolderCreate(BaseModel):
    name: str


class FolderResponse(BaseModel):
    id: str
    name: str
    status: str
    fileCount: int = 0


class FolderDetails(FolderResponse):
    files: list[str] = []
