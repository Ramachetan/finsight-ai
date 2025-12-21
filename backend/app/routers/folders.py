from typing import List

from dotenv import load_dotenv
from fastapi import APIRouter, File, HTTPException, UploadFile, status

from app.models.schemas import FolderCreate, FolderDetails, FolderResponse
from app.services.storage import StorageService

load_dotenv()

router = APIRouter(prefix="/folders", tags=["folders"])

storage_service = StorageService()


@router.post("/", response_model=FolderResponse)
def create_folder(folder: FolderCreate):
    """
    Creates a logical folder to group bank statements.
    """
    try:
        result = storage_service.create_folder(folder.name)
        if not result:
             raise HTTPException(status_code=500, detail="Failed to create folder")
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/", response_model=List[FolderResponse])
def get_folders():
    """
    List all folders.
    """
    return storage_service.list_folders()


@router.get("/{folder_id}", response_model=FolderDetails)
def get_folder(folder_id: str):
    """
    Get folder details and list of files.
    """
    folder = storage_service.get_folder(folder_id)
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    
    files = storage_service.list_files(folder_id)
    # Ensure fileCount is set in the response
    return {**folder, "files": files, "fileCount": len(files)}


@router.delete("/{folder_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_folder(folder_id: str):
    """
    Deletes a folder and its contents.
    """
    if not storage_service.folder_exists(folder_id):
        raise HTTPException(status_code=404, detail="Folder not found")

    # Delete from GCS
    storage_service.delete_folder(folder_id)
    return None


@router.post("/{folder_id}/upload")
def upload_statements(folder_id: str, files: List[UploadFile] = File(...)):
    """
    Uploads one or multiple PDF bank statements to a specific folder.
    """
    if not storage_service.folder_exists(folder_id):
        raise HTTPException(status_code=404, detail="Folder not found")

    saved_files = []
    for file in files:
        try:
            # Upload to GCS
            storage_service.upload_file(folder_id, file.filename, file.file)
            saved_files.append(file.filename)
        except Exception as e:
            print(f"Failed to upload {file.filename}: {e}")

    return {
        "message": f"Successfully uploaded {len(saved_files)} files",
        "files": saved_files,
    }


@router.get("/{folder_id}/files/{filename}")
def get_file(folder_id: str, filename: str):
    """
    Retrieve an original uploaded file from a folder.
    Returns the file as a streaming response with appropriate content type.
    """
    import io

    from fastapi.responses import StreamingResponse
    
    # Verify folder exists
    if not storage_service.folder_exists(folder_id):
        raise HTTPException(status_code=404, detail="Folder not found")
    
    # Get file content from storage
    try:
        file_content = storage_service.read_file_content(folder_id, filename)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve file: {str(e)}")
    
    # Determine content type based on file extension
    content_type = "application/pdf" if filename.lower().endswith('.pdf') else "application/octet-stream"
    
    # Return file as streaming response
    return StreamingResponse(
        io.BytesIO(file_content),
        media_type=content_type,
        headers={
            "Content-Disposition": f'inline; filename="{filename}"'
        }
    )


@router.delete("/{folder_id}/files/{filename}", status_code=status.HTTP_204_NO_CONTENT)
def delete_file(folder_id: str, filename: str):
    """
    Delete a specific file from a folder.
    Also deletes the associated processed CSV if it exists.
    """
    # Verify folder exists
    if not storage_service.folder_exists(folder_id):
        raise HTTPException(status_code=404, detail="Folder not found")
    
    # Check if file exists
    files = storage_service.list_files(folder_id)
    if filename not in files:
        raise HTTPException(status_code=404, detail="File not found")
    
    # Delete the file
    success = storage_service.delete_file(folder_id, filename)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete file")
    
    return None
