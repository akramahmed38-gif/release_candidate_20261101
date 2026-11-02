"""Data Routes Module."""

import os
from mimetypes import guess_type
from pathlib import Path
from typing import Iterable, List, Optional
import logging
import aiofiles
from pydantic import BaseModel, Field
# from httpcore import request
from fastapi import APIRouter, UploadFile, status, Depends, Request, HTTPException, File, Query
from fastapi.responses import JSONResponse, FileResponse, Response, StreamingResponse
from controllers import DataController, MaterialController

from routes.schemas import MaterialRequest
from models.material_model import MaterialModel

from models import ResponseSignalEnum
from models.db_schemas import Material
from routes.users.auth_utils import get_current_user

logger = logging.getLogger("uvicorn")
material_router = APIRouter(prefix="/api/v1", tags=["api_v1", "material"])

MATERIAL_VIEWER_ROLES = {"admin", "auditor", "hr", "manager", "retail", "employee"}
MATERIAL_ADMIN_ROLES = {"admin", "auditor"}
LEGACY_MATERIAL_MANAGER_ROLES = {"admin", "auditor", "hr"}
VIDEO_STREAM_CHUNK_SIZE = 1024 * 1024


class MaterialFolderCreateRequest(BaseModel):
    path: str = Field(default="", description="Parent folder path relative to the material root.")
    name: str = Field(min_length=1, description="Folder name to create.")


class MaterialFolderRenameRequest(BaseModel):
    path: str = Field(..., description="Folder path relative to the material root.")
    new_name: str = Field(min_length=1, description="New folder name.")


class MaterialFolderDeleteRequest(BaseModel):
    path: str = Field(..., description="Folder path relative to the material root.")


class MaterialFileRenameRequest(BaseModel):
    path: str = Field(..., description="File path relative to the material root.")
    new_name: str = Field(min_length=1, description="New file name.")


class MaterialFileDeleteRequest(BaseModel):
    path: str = Field(..., description="File path relative to the material root.")


def _normalized_role(current_user: dict) -> str:
    return str(current_user.get("role") or current_user.get("department") or "").strip().lower()


def _require_material_view_access(current_user: dict) -> None:
    if _normalized_role(current_user) not in MATERIAL_VIEWER_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not allowed to access training materials.",
        )


def _require_material_admin_access(current_user: dict) -> None:
    if _normalized_role(current_user) not in MATERIAL_ADMIN_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can manage training materials.",
        )


def _require_legacy_material_manager(current_user: dict) -> None:
    if _normalized_role(current_user) not in LEGACY_MATERIAL_MANAGER_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not allowed to manage legacy training materials.",
        )


def _library_controller(request: Request) -> MaterialController:
    request_path = request.scope.get("path") or request.url.path
    if "/daily-brief" in request_path:
        return MaterialController(library_directory="daily_brief", library_label="Daily Brief")
    return MaterialController()


def _material_error_response(detail: str, status_code_value: int) -> HTTPException:
    return HTTPException(status_code=status_code_value, detail=detail)


def _iter_file_chunk(file_path: Path, start: int, end: int, chunk_size: int = VIDEO_STREAM_CHUNK_SIZE) -> Iterable[bytes]:
    with file_path.open("rb") as opened_file:
        opened_file.seek(start)
        remaining = end - start + 1

        while remaining > 0:
            chunk = opened_file.read(min(chunk_size, remaining))
            if not chunk:
                break
            yield chunk
            remaining -= len(chunk)


def _parse_range_header(range_header: str, file_size: int) -> tuple[int, int]:
    if not range_header.lower().startswith("bytes="):
        raise ValueError("Invalid Range header.")

    first_range = range_header.split("=", 1)[1].split(",", 1)[0].strip()
    if "-" not in first_range:
        raise ValueError("Invalid Range header.")

    start_text, end_text = first_range.split("-", 1)
    if not start_text and not end_text:
        raise ValueError("Invalid Range header.")

    if not start_text:
        suffix_length = int(end_text)
        if suffix_length <= 0:
            raise ValueError("Invalid Range header.")
        start = max(file_size - suffix_length, 0)
        end = file_size - 1
    else:
        start = int(start_text)
        if start < 0:
            raise ValueError("Invalid Range header.")
        end = file_size - 1 if not end_text else int(end_text)
        if end < start:
            raise ValueError("Invalid Range header.")

    if start >= file_size:
        raise ValueError("Range start is outside the file size.")

    return start, min(end, file_size - 1)


def _build_video_stream_headers(
    *,
    mime_type: str,
    content_length: int,
    content_range: str | None = None,
) -> dict[str, str]:
    headers = {
        "Accept-Ranges": "bytes",
        "Content-Type": mime_type,
        "Content-Length": str(content_length),
        "Cache-Control": "no-transform",
    }
    if content_range:
        headers["Content-Range"] = content_range
    return headers


@material_router.get("/daily-brief")
@material_router.get("/materials")
async def list_material_library(
    path: str = Query(default="", description="Folder path relative to the material root."),
    request: Request = None,
    current_user: dict = Depends(get_current_user),
):
    _require_material_view_access(current_user)
    material_controller = _library_controller(request)

    try:
        library_payload = material_controller.list_material_library(path)
    except FileNotFoundError as exc:
        raise _material_error_response(str(exc), status.HTTP_404_NOT_FOUND) from exc
    except ValueError as exc:
        raise _material_error_response(str(exc), status.HTTP_400_BAD_REQUEST) from exc
    except OSError as exc:
        logger.exception("Unable to access training material folder.")
        raise _material_error_response(
            "Unable to access the training material folder.",
            status.HTTP_500_INTERNAL_SERVER_ERROR,
        ) from exc

    message = ""
    if not library_payload["folders"] and not library_payload["files"]:
        message = "This folder does not contain supported training items yet."
    elif library_payload["skippedCount"]:
        message = f"{library_payload['skippedCount']} unsupported files were skipped in this folder."

    return {
        "signal": ResponseSignalEnum.FILES_RETRIEVED_SUCCESSFULLY.value,
        **library_payload,
        "message": message,
    }


@material_router.get("/daily-brief/search")
@material_router.get("/materials/search")
async def search_material_library_files(
    query: str = Query(default="", description="Search term matched against material file names and paths."),
    file_type: str = Query(default="all", description="Optional material type filter."),
    request: Request = None,
    current_user: dict = Depends(get_current_user),
):
    _require_material_view_access(current_user)
    material_controller = _library_controller(request)

    try:
        search_payload = material_controller.search_material_library_files(query, file_type)
    except ValueError as exc:
        raise _material_error_response(str(exc), status.HTTP_400_BAD_REQUEST) from exc
    except OSError as exc:
        logger.exception("Unable to search training material files.")
        raise _material_error_response(
            "Unable to search the training materials library.",
            status.HTTP_500_INTERNAL_SERVER_ERROR,
        ) from exc

    message = ""
    if not search_payload["files"]:
        message = "No matching training material files were found."

    return {
        "signal": ResponseSignalEnum.FILES_RETRIEVED_SUCCESSFULLY.value,
        **search_payload,
        "message": message,
    }


@material_router.get("/daily-brief/open")
@material_router.get("/materials/open")
async def open_material_library_file(
    path: str = Query(..., description="File path relative to the material root."),
    request: Request = None,
    current_user: dict = Depends(get_current_user),
):
    _require_material_view_access(current_user)
    material_controller = _library_controller(request)

    try:
        file_path, metadata = material_controller.resolve_material_library_item(path)
    except FileNotFoundError as exc:
        raise _material_error_response(str(exc), status.HTTP_404_NOT_FOUND) from exc
    except ValueError as exc:
        raise _material_error_response(str(exc), status.HTTP_400_BAD_REQUEST) from exc
    except OSError as exc:
        logger.exception("Unable to open training material file.")
        raise _material_error_response(
            "The requested file could not be opened.",
            status.HTTP_500_INTERNAL_SERVER_ERROR,
        ) from exc

    disposition = "attachment" if metadata["material_type"] == "powerpoint" else "inline"
    return FileResponse(
        path=file_path,
        filename=metadata["file_name"],
        media_type=metadata["mime_type"],
        content_disposition_type=disposition,
    )


@material_router.get("/daily-brief/stream")
@material_router.get("/materials/stream")
async def stream_material_library_video(
    request: Request,
    path: str = Query(..., description="Video path relative to the material root."),
    current_user: dict = Depends(get_current_user),
):
    _require_material_view_access(current_user)
    material_controller = _library_controller(request)

    try:
        file_path, metadata = material_controller.resolve_material_library_item(path)
    except FileNotFoundError as exc:
        raise _material_error_response(str(exc), status.HTTP_404_NOT_FOUND) from exc
    except ValueError as exc:
        raise _material_error_response(str(exc), status.HTTP_400_BAD_REQUEST) from exc
    except OSError as exc:
        logger.exception("Unable to stream training material file.")
        raise _material_error_response(
            "The requested video could not be streamed.",
            status.HTTP_500_INTERNAL_SERVER_ERROR,
        ) from exc

    if metadata["material_type"] != "video":
        raise _material_error_response(
            "Streaming is only available for video files.",
            status.HTTP_400_BAD_REQUEST,
        )

    try:
        file_size = file_path.stat().st_size
    except OSError as exc:
        logger.exception("Unable to access training material file size.")
        raise _material_error_response(
            "The requested video could not be streamed.",
            status.HTTP_500_INTERNAL_SERVER_ERROR,
        ) from exc

    range_header = request.headers.get("range")
    if range_header:
        try:
            start, end = _parse_range_header(range_header, file_size)
        except ValueError:
            return Response(
                status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE,
                headers={
                    "Accept-Ranges": "bytes",
                    "Content-Range": f"bytes */{file_size}",
                    "Cache-Control": "no-transform",
                },
            )

        content_length = end - start + 1
        headers = _build_video_stream_headers(
            mime_type=metadata["mime_type"],
            content_length=content_length,
            content_range=f"bytes {start}-{end}/{file_size}",
        )
        return StreamingResponse(
            _iter_file_chunk(file_path, start, end),
            status_code=status.HTTP_206_PARTIAL_CONTENT,
            headers=headers,
            media_type=metadata["mime_type"],
        )

    headers = _build_video_stream_headers(
        mime_type=metadata["mime_type"],
        content_length=file_size,
    )
    return StreamingResponse(
        _iter_file_chunk(file_path, 0, file_size - 1),
        status_code=status.HTTP_200_OK,
        headers=headers,
        media_type=metadata["mime_type"],
    )


@material_router.get("/materials/file/{material_id}")
async def open_material_library_file_by_id(
    material_id: str,
    current_user: dict = Depends(get_current_user),
):
    _require_material_view_access(current_user)
    material_controller = MaterialController()

    try:
        relative_path = material_controller.decode_material_id(material_id)
        file_path, metadata = material_controller.resolve_material_library_item(relative_path)
    except FileNotFoundError as exc:
        raise _material_error_response(str(exc), status.HTTP_404_NOT_FOUND) from exc
    except ValueError as exc:
        raise _material_error_response(str(exc), status.HTTP_400_BAD_REQUEST) from exc
    except OSError as exc:
        logger.exception("Unable to open training material file.")
        raise _material_error_response(
            "The requested file could not be opened.",
            status.HTTP_500_INTERNAL_SERVER_ERROR,
        ) from exc

    disposition = "attachment" if metadata["material_type"] == "powerpoint" else "inline"
    return FileResponse(
        path=file_path,
        filename=metadata["file_name"],
        media_type=metadata["mime_type"],
        content_disposition_type=disposition,
    )


@material_router.post("/daily-brief/folder")
@material_router.post("/materials/folder")
async def create_material_folder(
    payload: MaterialFolderCreateRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    _require_material_admin_access(current_user)
    material_controller = _library_controller(request)

    try:
        folder = material_controller.create_folder(payload.path, payload.name)
    except FileNotFoundError as exc:
        raise _material_error_response(str(exc), status.HTTP_404_NOT_FOUND) from exc
    except FileExistsError as exc:
        raise _material_error_response(str(exc), status.HTTP_409_CONFLICT) from exc
    except ValueError as exc:
        raise _material_error_response(str(exc), status.HTTP_400_BAD_REQUEST) from exc
    except OSError as exc:
        logger.exception("Unable to create material folder.")
        raise _material_error_response(
            "The folder could not be created.",
            status.HTTP_500_INTERNAL_SERVER_ERROR,
        ) from exc

    return {
        "signal": "folder_created_successfully",
        "folder": folder,
    }


@material_router.put("/daily-brief/folder")
@material_router.put("/materials/folder")
async def rename_material_folder(
    payload: MaterialFolderRenameRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    _require_material_admin_access(current_user)
    material_controller = _library_controller(request)

    try:
        folder = material_controller.rename_folder(payload.path, payload.new_name)
    except FileNotFoundError as exc:
        raise _material_error_response(str(exc), status.HTTP_404_NOT_FOUND) from exc
    except FileExistsError as exc:
        raise _material_error_response(str(exc), status.HTTP_409_CONFLICT) from exc
    except ValueError as exc:
        raise _material_error_response(str(exc), status.HTTP_400_BAD_REQUEST) from exc
    except OSError as exc:
        logger.exception("Unable to rename material folder.")
        raise _material_error_response(
            "The folder could not be renamed.",
            status.HTTP_500_INTERNAL_SERVER_ERROR,
        ) from exc

    return {
        "signal": "folder_renamed_successfully",
        "folder": folder,
    }


@material_router.delete("/daily-brief/folder")
@material_router.delete("/materials/folder")
async def delete_material_folder(
    payload: MaterialFolderDeleteRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    _require_material_admin_access(current_user)
    material_controller = _library_controller(request)

    try:
        material_controller.delete_folder(payload.path)
    except FileNotFoundError as exc:
        raise _material_error_response(str(exc), status.HTTP_404_NOT_FOUND) from exc
    except ValueError as exc:
        raise _material_error_response(str(exc), status.HTTP_400_BAD_REQUEST) from exc
    except OSError as exc:
        logger.exception("Unable to delete material folder.")
        raise _material_error_response(
            "The folder could not be deleted.",
            status.HTTP_500_INTERNAL_SERVER_ERROR,
        ) from exc

    return {
        "signal": "folder_deleted_successfully",
        "path": payload.path,
    }


@material_router.put("/daily-brief/file")
@material_router.put("/materials/file")
async def rename_material_file(
    payload: MaterialFileRenameRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    _require_material_admin_access(current_user)
    material_controller = _library_controller(request)

    try:
        file_payload = material_controller.rename_file(payload.path, payload.new_name)
    except FileNotFoundError as exc:
        raise _material_error_response(str(exc), status.HTTP_404_NOT_FOUND) from exc
    except FileExistsError as exc:
        raise _material_error_response(str(exc), status.HTTP_409_CONFLICT) from exc
    except ValueError as exc:
        raise _material_error_response(str(exc), status.HTTP_400_BAD_REQUEST) from exc
    except OSError as exc:
        logger.exception("Unable to rename material file.")
        raise _material_error_response(
            "The file could not be renamed.",
            status.HTTP_500_INTERNAL_SERVER_ERROR,
        ) from exc

    return {
        "signal": "file_renamed_successfully",
        "file": file_payload,
    }


@material_router.delete("/daily-brief/file")
@material_router.delete("/materials/file")
async def delete_material_file(
    payload: MaterialFileDeleteRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    _require_material_admin_access(current_user)
    material_controller = _library_controller(request)

    try:
        material_controller.delete_file(payload.path)
    except FileNotFoundError as exc:
        raise _material_error_response(str(exc), status.HTTP_404_NOT_FOUND) from exc
    except ValueError as exc:
        raise _material_error_response(str(exc), status.HTTP_400_BAD_REQUEST) from exc
    except OSError as exc:
        logger.exception("Unable to delete material file.")
        raise _material_error_response(
            "The file could not be deleted.",
            status.HTTP_500_INTERNAL_SERVER_ERROR,
        ) from exc

    return {
        "signal": "file_deleted_successfully",
        "path": payload.path,
    }

#! Upload Material File
@material_router.post("/daily-brief/upload")
@material_router.post("/materials/upload")
async def upload_material(
    request: Request,
    files: List[UploadFile] = File(...),
    path: str = Query(default="", description="Target folder path relative to the material root."),
    group_name: Optional[str] = Query(default=None),
    training_type: Optional[str] = Query(default=None),  # Legacy mode: New Hire || Existing Employee
    current_user: dict = Depends(get_current_user),
):
    app_state = request.app.state
    app_settings = app_state.settings

    if group_name is not None or training_type is not None:
        _require_legacy_material_manager(current_user)
        if not group_name or not training_type:
            raise _material_error_response(
                "group_name and training_type are required for the legacy upload flow.",
                status.HTTP_400_BAD_REQUEST,
            )

        data_controller = DataController()
        material_model = await MaterialModel.create_instance(
            db_client=app_state.db_client,
        )

        file_names_list = []

        for file in files:
            is_valid, result_signal = data_controller.validate_uploaded_file(file)
            if not is_valid:
                return JSONResponse(
                    content={"signal": result_signal},
                    status_code=status.HTTP_400_BAD_REQUEST,
                )
            file_path, file_name = data_controller.generate_unique_filepath(
                original_file_name=file.filename,
                group_name=group_name,
                training_type=training_type,
            )
            file_names_list.append(file_name)

            try:
                async with aiofiles.open(file_path, "wb") as opened_file:
                    while chunk := await file.read(app_settings.FILE_DEFAULT_CHUNK_SIZE):
                        await opened_file.write(chunk)
            except OSError as exc:
                logger.error("Error while uploading file: %s", exc)
                return JSONResponse(
                    content={"signal": ResponseSignalEnum.FILE_UPLOAD_FAILED.value},
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

            material_record = Material(
                material_name=file_name,
                material_group=group_name,
                material_training_type=training_type,
            )
            await material_model.create_material(material_record)

        return JSONResponse(
            content={
                "signal": ResponseSignalEnum.FILE_UPLOAD_SUCCESS.value,
                "file_names": file_names_list,
            },
            status_code=status.HTTP_201_CREATED,
        )

    _require_material_admin_access(current_user)
    material_controller = _library_controller(request)
    uploaded_files: list[dict] = []
    skipped_files: list[dict] = []

    for file in files:
        incoming_name = (file.filename or "").strip()
        display_name = os.path.basename(incoming_name) if incoming_name else "unnamed"

        try:
            target_path = material_controller.prepare_upload_target(path, incoming_name)
        except FileNotFoundError as exc:
            raise _material_error_response(str(exc), status.HTTP_404_NOT_FOUND) from exc
        except ValueError as exc:
            skipped_files.append({"name": display_name, "reason": str(exc)})
            continue

        try:
            async with aiofiles.open(target_path, "wb") as opened_file:
                while chunk := await file.read(app_settings.FILE_DEFAULT_CHUNK_SIZE):
                    await opened_file.write(chunk)
            uploaded_files.append(material_controller.build_file_descriptor(target_path))
        except OSError as exc:
            logger.exception("Unable to upload file into the material library.")
            raise _material_error_response(
                "One or more files could not be uploaded.",
                status.HTTP_500_INTERNAL_SERVER_ERROR,
            ) from exc

    if not uploaded_files:
        return JSONResponse(
            content={
                "signal": ResponseSignalEnum.FILE_TYPE_NOT_SUPPORTED.value,
                "message": "No supported files were uploaded.",
                "skipped_files": skipped_files,
                "uploaded_count": 0,
                "skipped_count": len(skipped_files),
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    return JSONResponse(
        content={
            "signal": ResponseSignalEnum.FILE_UPLOAD_SUCCESS.value,
            "uploaded_files": uploaded_files,
            "skipped_files": skipped_files,
            "uploaded_count": len(uploaded_files),
            "skipped_count": len(skipped_files),
        },
        status_code=status.HTTP_201_CREATED,
    )

#! Get ALL Materials
@material_router.get("/materials/all")
async def get_all_materials(
    request: Request,
):
    app_state = request.app.state

    material_model = await MaterialModel.create_instance(
        db_client=app_state.db_client,
    )


    materials = await material_model.get_all_materials()

    materials_data = [
        {
            "material_id": material.material_id,
            "material_name": material.material_name.split("___")[0],
            "material_group": material.material_group,
            "material_training_type": material.material_training_type,
            "is_deleted": material.is_deleted,
        }
        for material in materials
    ]

    return JSONResponse(
        content={
            "signal": ResponseSignalEnum.FILES_RETRIEVED_SUCCESSFULLY.value,
            "materials": materials_data,
        },
        status_code=status.HTTP_200_OK,
    )

#! Get ALL Materials by Group
@material_router.get("/materials/by-group/{group_name}")
async def get_materials_by_group(
    request: Request,
    group_name: str,
):
    app_state = request.app.state

    material_model = await MaterialModel.create_instance(
        db_client=app_state.db_client,
    )

    materials = await material_model.get_materials_by_group(group_name)

    materials_data = [
        {
            "material_id": material.material_id,
            "material_name": material.material_name,
            "material_group": material.material_group,
            "material_training_type": material.material_training_type,
            "is_deleted": material.is_deleted,
        }
        for material in materials
    ]

    return JSONResponse(
        content={
            "signal": ResponseSignalEnum.FILES_RETRIEVED_SUCCESSFULLY.value,
            "materials": materials_data,
        },
        status_code=status.HTTP_200_OK,
    )

#! Get ALL Materials by Training Type
@material_router.get("/materials/by-training-type/{training_type}")
async def get_materials_by_training_type(
    request: Request,
    training_type: str,
):
    app_state = request.app.state

    material_model = await MaterialModel.create_instance(
        db_client=app_state.db_client,
    )


    materials = await material_model.get_materials_by_training_type(training_type)

    materials_data = [
        {
            "material_id": material.material_id,
            "material_name": material.material_name,
            "material_group": material.material_group,
            "material_training_type": material.material_training_type,
            "is_deleted": material.is_deleted,
        }
        for material in materials
    ]

    return JSONResponse(
        content={
            "signal": ResponseSignalEnum.FILES_RETRIEVED_SUCCESSFULLY.value,
            "materials": materials_data,
        },
        status_code=status.HTTP_200_OK,
    )

#! Get ALL Materials by Group and Training Type
@material_router.get("/materials/by-group-and-training-type/")
async def get_materials_by_group_and_training_type(
    request: Request,
    group_name: str,
    training_type: str,
):
    app_state = request.app.state

    material_model = await MaterialModel.create_instance(
        db_client=app_state.db_client,
    )


    materials = await material_model.get_materials_by_group_and_training_type(
        group_name, training_type
    )

    materials_data = [
        {
            "material_id": material.material_id,
            "material_name": material.material_name,
            "material_group": material.material_group,
            "material_training_type": material.material_training_type,
            "is_deleted": material.is_deleted,
        }
        for material in materials
    ]

    return JSONResponse(
        content={
            "signal": ResponseSignalEnum.FILES_RETRIEVED_SUCCESSFULLY.value,
            "materials": materials_data,
        },
        status_code=status.HTTP_200_OK,
    )

#! Get Material by ID
@material_router.get("/materials/by_id/{material_id}")
async def get_material_by_id(
    request: Request,
    material_id: str,
):
    app_state = request.app.state

    material_model = await MaterialModel.create_instance(
        db_client=app_state.db_client,
    )


    material = await material_model.get_material_by_id(material_id)

    if not material:
        return JSONResponse(
            content={
                "signal": ResponseSignalEnum.FILE_NOT_FOUND.value,
            },
            status_code=status.HTTP_404_NOT_FOUND,
        )

    material_data = {
        "material_id": material.material_id,
        "material_name": material.material_name,
        "material_group": material.material_group,
        "material_training_type": material.material_training_type,
        "is_deleted": material.is_deleted,
    }

    return JSONResponse(
        content={
            "signal": ResponseSignalEnum.FILES_RETRIEVED_SUCCESSFULLY.value,
            "material": material_data,
        },
        status_code=status.HTTP_200_OK,
    )

#! Delete Material by ID
@material_router.delete("/materials/softdelete/{material_id}")
async def delete_material_by_id_softdelete(
    request: Request,
    material_id: str,
):
    app_state = request.app.state

    material_model = await MaterialModel.create_instance(
        db_client=app_state.db_client,
    )


    is_deleted = await material_model.remove_material_by_id(material_id)

    if not is_deleted:
        return JSONResponse(
            content={
                "signal": ResponseSignalEnum.FILE_NOT_FOUND.value,
            },
            status_code=status.HTTP_404_NOT_FOUND,
        )

    return JSONResponse(
        content={
            "signal": ResponseSignalEnum.FILE_DELETED_SUCCESSFULLY.value,
        },
        status_code=status.HTTP_200_OK,
    )

#! Delete Material by ID permanently
@material_router.delete("/materials/harddelete/{material_id}")
async def delete_material_by_id_harddelete(
    request: Request,
    material_id: str,
):
    app_state = request.app.state

    material_model = await MaterialModel.create_instance(
        db_client=app_state.db_client,
    )


    is_deleted = await material_model.remove_material_by_id_permanently(material_id)

    if not is_deleted:
        return JSONResponse(
            content={
                "signal": ResponseSignalEnum.FILE_NOT_FOUND.value,
            },
            status_code=status.HTTP_404_NOT_FOUND,
        )

    return JSONResponse(
        content={
            "signal": ResponseSignalEnum.FILE_DELETED_SUCCESSFULLY.value,
        },
        status_code=status.HTTP_200_OK,
    )

#! Delete Material by Group
@material_router.delete("/materials/by-group/{group_name}")
async def delete_materials_by_group(
    request: Request,
    group_name: str,
):
    app_state = request.app.state

    material_model = await MaterialModel.create_instance(
        db_client=app_state.db_client,
    )

    materials = await material_model.get_materials_by_group(group_name)

    if not materials:
        return JSONResponse(
            content={
                "signal": ResponseSignalEnum.FILE_NOT_FOUND.value,
            },
            status_code=status.HTTP_404_NOT_FOUND,
        )

    for material in materials:
        await material_model.remove_material_by_id(material.material_id)

    return JSONResponse(
        content={
            "signal": ResponseSignalEnum.FILE_DELETED_SUCCESSFULLY.value,
            "number_of_deleted_files": len(materials),
        },
        status_code=status.HTTP_200_OK,
    )

#! Delete Material by Training Type
@material_router.delete("/materials/by-training-type/{training_type}")
async def delete_materials_by_training_type(
    request: Request,
    training_type: str,
):
    app_state = request.app.state

    material_model = await MaterialModel.create_instance(
        db_client=app_state.db_client,
    )

    materials = await material_model.get_materials_by_training_type(training_type)

    if not materials:
        return JSONResponse(
            content={
                "signal": ResponseSignalEnum.FILE_NOT_FOUND.value,
            },
            status_code=status.HTTP_404_NOT_FOUND,
        )

    for material in materials:
        await material_model.remove_material_by_id(material.material_id)

    return JSONResponse(
        content={
            "signal": ResponseSignalEnum.FILE_DELETED_SUCCESSFULLY.value,
            "number_of_deleted_files": len(materials),
        },
        status_code=status.HTTP_200_OK,
    )

#! delete ALL Materials
@material_router.delete("/materials/all")
async def delete_all_materials(
    request: Request,
):
    app_state = request.app.state

    material_model = await MaterialModel.create_instance(
        db_client=app_state.db_client,
    )

    materials = await material_model.get_all_materials()

    if not materials:
        return JSONResponse(
            content={
                "signal": ResponseSignalEnum.FILE_NOT_FOUND.value,
            },
            status_code=status.HTTP_404_NOT_FOUND,
        )

    for material in materials:
        await material_model.remove_material_by_id_permanently(material.material_id)

    return JSONResponse(
        content={
            "signal": ResponseSignalEnum.FILE_DELETED_SUCCESSFULLY.value,
            "number_of_deleted_files": len(materials),
        },
        status_code=status.HTTP_200_OK,
    )

#! Restore Material by ID
@material_router.post("/materials/restore/{material_id}")
async def restore_material_by_id(
    request: Request,
    material_id: str,
):
    app_state = request.app.state

    material_model = await MaterialModel.create_instance(
        db_client=app_state.db_client,
    )

    material = await material_model.get_material_by_id(material_id)
    if not material:
        return JSONResponse(
            content={
                "signal": ResponseSignalEnum.FILE_NOT_FOUND.value,
            },
            status_code=status.HTTP_404_NOT_FOUND,
        )
    
    if not material.is_deleted:
        return JSONResponse(
            content={
                "signal": ResponseSignalEnum.FILE_NOT_DELETED.value,
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )


    is_restored = await material_model.restore_material_by_id(material_id)

    if not is_restored:
        return JSONResponse(
            content={
                "signal": ResponseSignalEnum.FILE_NOT_FOUND.value,
            },
            status_code=status.HTTP_404_NOT_FOUND,
        )

    return JSONResponse(
        content={
            "signal": ResponseSignalEnum.FILE_RESTORE_SUCCESS.value,
        },
        status_code=status.HTTP_200_OK,
    )

@material_router.get("/materials/download/{material_id}")
async def download_material(
    request: Request,
    material_id: str,
):
    
    app_state = request.app.state

    material_model = await MaterialModel.create_instance(
        db_client=app_state.db_client,
    )

    material = await material_model.get_material_by_id(material_id)
    if not material:
        return JSONResponse(
            content={
                "signal": ResponseSignalEnum.FILE_NOT_FOUND.value,
            },
            status_code=status.HTTP_404_NOT_FOUND,
        )
    
    if material.is_deleted:
        return JSONResponse(
            content={
                "signal": "FILE IS DELETED",
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    
    file_path = os.path.join(DataController().materials_dir, material.material_group, material.material_training_type , material.material_name)
        
    if not os.path.exists(file_path):
        return JSONResponse(
            content={
                "signal": ResponseSignalEnum.FILE_NOT_FOUND.value,
            },
            status_code=status.HTTP_404_NOT_FOUND,
        )
    
    return FileResponse(
        path=file_path,
        filename=material.material_name,
        media_type='application/octet-stream'
    )

@material_router.get("/materials/view/{material_id}")
async def view_material(
    request: Request,
    material_id: str,
):
    app_state = request.app.state
    material_model = await MaterialModel.create_instance(
        db_client=app_state.db_client,
    )

    material = await material_model.get_material_by_id(material_id)
    if not material:
        return JSONResponse(
            content={"signal": ResponseSignalEnum.FILE_NOT_FOUND.value},
            status_code=status.HTTP_404_NOT_FOUND,
        )

    if material.is_deleted:
        return JSONResponse(
            content={"signal": "FILE IS DELETED"},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    file_path = os.path.join(
        DataController().materials_dir,
        material.material_group,
        material.material_training_type,
        material.material_name,
    )
    if not os.path.exists(file_path):
        return JSONResponse(
            content={"signal": ResponseSignalEnum.FILE_NOT_FOUND.value},
            status_code=status.HTTP_404_NOT_FOUND,
        )
    
    display_name = material.material_name.split("___")[0]
    mime_type, _ = guess_type(display_name)
    if mime_type is None:
        mime_type = "application/octet-stream"
    mime_type, _ = guess_type(display_name)

    print(f"[INFO] Viewing file at path: {file_path}, {material.material_name.split('___')[0]}, application/octet-stream")
    return FileResponse(
        path=file_path,
        filename=display_name,
        media_type=mime_type
    )



@material_router.get("/materials/analyze")
async def analyze_materials(request: Request):

    app_state = request.app.state
    material_model = await MaterialModel.create_instance(
        db_client=app_state.db_client,
    )
    materials = await material_model.get_all_materials()

    if not materials:
        return JSONResponse(
            content={
                "signal": "no materials found for analysis.",
            },
            status_code=status.HTTP_404_NOT_FOUND,
        )
    total_materials = len(materials)
    group_counts = {}
    training_type_counts = {}
    for material in materials:
        group = material.material_group
        training_type = material.material_training_type

        group_counts[group] = group_counts.get(group, 0) + 1
        training_type_counts[training_type] = training_type_counts.get(training_type, 0) + 1

    analysis_result = {
        "total_materials": total_materials,
        "group_counts": group_counts,
        "training_type_counts": training_type_counts,
    }

    return JSONResponse(
        content={
            "signal": "materials analysis completed successfully.",
            "analysis": analysis_result,
        },
        status_code=status.HTTP_200_OK,
    )




def main():
    """Entry Point for the Program."""
    print(
        f"Welcome from `{os.path.basename(__file__).split('.')[0]}` Module. Nothing to do ^_____^!"
    )

if __name__ == "__main__":
    main()
