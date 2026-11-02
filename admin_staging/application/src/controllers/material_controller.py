import base64
import os
import shutil
from datetime import datetime, timezone
from mimetypes import guess_type
from pathlib import Path, PurePosixPath

from controllers.base_controller import BaseController

SUPPORTED_MATERIAL_EXTENSIONS = {
    "video": {".mp4", ".mov", ".avi", ".mkv", ".webm"},
    "pdf": {".pdf"},
    "powerpoint": {".ppt", ".pptx"},
    "excel": {".xls", ".xlsx"},
}
VALID_MATERIAL_TYPES = frozenset(SUPPORTED_MATERIAL_EXTENSIONS.keys())

MIME_TYPE_OVERRIDES = {
    ".ppt": "application/vnd.ms-powerpoint",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}

WINDOWS_FORBIDDEN_NAME_CHARS = set('<>:"|?*')


class MaterialController(BaseController):
    def __init__(self, library_directory: str = "material", library_label: str = "Materials") -> None:
        super().__init__()
        self.material_library_dir = (Path(self.base_dir) / library_directory).resolve()
        self.material_library_label = library_label

    def get_group_path(self, group_name: str, training_type: str) -> str:
        group_dir_path = os.path.join(self.materials_dir, group_name, training_type)
        os.makedirs(group_dir_path, exist_ok=True)
        return group_dir_path

    def get_all_groups(self) -> list[str]:
        groups = []
        if os.path.exists(self.materials_dir):
            for material_group in os.listdir(self.materials_dir):
                group_path = os.path.join(self.materials_dir, material_group)
                if os.path.isdir(group_path):
                    groups.append(material_group)
        return groups

    def get_material_library_path(self) -> Path:
        return self.material_library_dir

    def normalize_relative_path(self, path_value: str | None, *, allow_root: bool = True) -> str:
        raw_value = (path_value or "").strip().replace("\\", "/")
        if raw_value in {"", "."}:
            if allow_root:
                return ""
            raise ValueError("Path is required.")

        if "\x00" in raw_value:
            raise ValueError("Invalid path.")

        candidate = PurePosixPath(raw_value)
        if candidate.is_absolute():
            raise ValueError("Absolute paths are not allowed.")

        normalized_parts: list[str] = []
        for part in candidate.parts:
            cleaned = str(part).strip()
            if cleaned in {"", "."}:
                continue
            if cleaned == "..":
                raise ValueError("Invalid path.")
            if ":" in cleaned:
                raise ValueError("Invalid path.")
            normalized_parts.append(cleaned)

        normalized = "/".join(normalized_parts)
        if not normalized and not allow_root:
            raise ValueError("Path is required.")
        return normalized

    def normalize_item_name(self, name: str, *, preserve_extension: str | None = None) -> str:
        candidate = (name or "").strip()
        if not candidate:
            raise ValueError("Name is required.")
        if candidate in {".", ".."}:
            raise ValueError("Invalid name.")
        if "/" in candidate or "\\" in candidate:
            raise ValueError("Invalid name.")
        if any(char in WINDOWS_FORBIDDEN_NAME_CHARS for char in candidate):
            raise ValueError("Invalid name.")
        if candidate.endswith("."):
            raise ValueError("Invalid name.")

        if preserve_extension:
            current_extension = preserve_extension.lower()
            provided_extension = Path(candidate).suffix.lower()
            if not provided_extension:
                candidate = f"{candidate}{current_extension}"
            elif provided_extension != current_extension:
                raise ValueError("File extension cannot be changed.")

        return candidate

    def resolve_library_path(
        self,
        relative_path: str | None = "",
        *,
        must_exist: bool = False,
        expect_directory: bool | None = None,
    ) -> tuple[Path, str]:
        library_root = self.get_material_library_path()
        normalized = self.normalize_relative_path(relative_path)
        target_path = library_root if not normalized else (library_root / Path(*normalized.split("/"))).resolve()

        if target_path != library_root and library_root not in target_path.parents:
            raise ValueError("Invalid path.")

        if must_exist and not target_path.exists():
            if expect_directory is False:
                raise FileNotFoundError("File not found.")
            raise FileNotFoundError("Folder not found.")

        if expect_directory is True and target_path.exists() and not target_path.is_dir():
            raise FileNotFoundError("Folder not found.")
        if expect_directory is False and target_path.exists() and not target_path.is_file():
            raise FileNotFoundError("File not found.")

        return target_path, normalized

    def build_relative_path(self, absolute_path: Path) -> str:
        return absolute_path.relative_to(self.get_material_library_path()).as_posix()

    def build_material_id(self, relative_path: str) -> str:
        encoded = base64.urlsafe_b64encode(relative_path.encode("utf-8")).decode("ascii")
        return encoded.rstrip("=")

    def decode_material_id(self, material_id: str) -> str:
        padded_material_id = material_id + "=" * (-len(material_id) % 4)
        try:
            return base64.urlsafe_b64decode(padded_material_id.encode("ascii")).decode("utf-8")
        except Exception as exc:
            raise ValueError("Invalid material identifier.") from exc

    def classify_material_type(self, file_path: Path) -> str | None:
        extension = file_path.suffix.lower()
        for material_type, extensions in SUPPORTED_MATERIAL_EXTENSIONS.items():
            if extension in extensions:
                return material_type
        return None

    def get_mime_type(self, file_path: Path) -> str:
        return MIME_TYPE_OVERRIDES.get(file_path.suffix.lower()) or guess_type(file_path.name)[0] or "application/octet-stream"

    def normalize_file_type_filter(self, file_type: str | None) -> str | None:
        normalized = str(file_type or "").strip().lower()
        if normalized in {"", "all"}:
            return None
        if normalized not in VALID_MATERIAL_TYPES:
            raise ValueError("Unsupported material type filter.")
        return normalized

    def format_timestamp(self, timestamp_value: float) -> str:
        return datetime.fromtimestamp(timestamp_value, tz=timezone.utc).isoformat()

    def build_file_descriptor(self, file_path: Path) -> dict:
        material_type = self.classify_material_type(file_path)
        if material_type is None:
            raise ValueError("Unsupported material type.")

        file_stat = file_path.stat()
        return {
            "material_id": self.build_material_id(self.build_relative_path(file_path)),
            "name": file_path.name,
            "path": self.build_relative_path(file_path),
            "file_type": material_type,
            "extension": file_path.suffix.lower(),
            "mime_type": self.get_mime_type(file_path),
            "size_bytes": int(file_stat.st_size),
            "last_modified": self.format_timestamp(file_stat.st_mtime),
        }

    def count_immediate_folder_items(self, folder_path: Path) -> tuple[int, int, int]:
        folder_count = 0
        file_count = 0
        skipped_files = 0

        for child_path in folder_path.iterdir():
            if child_path.is_dir():
                folder_count += 1
            elif child_path.is_file():
                if self.classify_material_type(child_path):
                    file_count += 1
                else:
                    skipped_files += 1

        return folder_count, file_count, skipped_files

    def build_folder_descriptor(self, folder_path: Path) -> dict:
        folder_count, file_count, skipped_files = self.count_immediate_folder_items(folder_path)
        folder_stat = folder_path.stat()
        return {
            "name": folder_path.name,
            "path": self.build_relative_path(folder_path),
            "item_count": folder_count + file_count,
            "folder_count": folder_count,
            "file_count": file_count,
            "skipped_files": skipped_files,
            "last_modified": self.format_timestamp(folder_stat.st_mtime),
        }

    def summarize_subtree(self, folder_path: Path) -> dict:
        counts = {
            "total_materials": 0,
            "folders": 0,
            "videos": 0,
            "pdfs": 0,
            "powerpoints": 0,
            "excels": 0,
            "skipped_files": 0,
        }

        for child_path in folder_path.rglob("*"):
            if child_path.is_dir():
                counts["folders"] += 1
                continue
            if not child_path.is_file():
                continue

            material_type = self.classify_material_type(child_path)
            if material_type is None:
                counts["skipped_files"] += 1
                continue

            counts["total_materials"] += 1
            if material_type == "video":
                counts["videos"] += 1
            elif material_type == "pdf":
                counts["pdfs"] += 1
            elif material_type == "powerpoint":
                counts["powerpoints"] += 1
            elif material_type == "excel":
                counts["excels"] += 1

        return counts

    def build_breadcrumb(self, relative_path: str) -> list[dict]:
        breadcrumb = [{"name": self.material_library_label, "path": ""}]
        if not relative_path:
            return breadcrumb

        parts = relative_path.split("/")
        for index in range(len(parts)):
            breadcrumb.append(
                {
                    "name": parts[index],
                    "path": "/".join(parts[: index + 1]),
                }
            )
        return breadcrumb

    def list_material_library(self, relative_path: str | None = "") -> dict:
        folder_path, normalized_path = self.resolve_library_path(
            relative_path,
            must_exist=True,
            expect_directory=True,
        )

        folders: list[dict] = []
        files: list[dict] = []
        skipped_in_current_folder = 0

        for child_path in sorted(
            folder_path.iterdir(),
            key=lambda path: (not path.is_dir(), path.name.lower()),
        ):
            if child_path.is_dir():
                folders.append(self.build_folder_descriptor(child_path))
                continue
            if not child_path.is_file():
                continue

            material_type = self.classify_material_type(child_path)
            if material_type is None:
                skipped_in_current_folder += 1
                continue
            files.append(self.build_file_descriptor(child_path))

        return {
            "currentPath": normalized_path,
            "breadcrumb": self.build_breadcrumb(normalized_path),
            "folders": folders,
            "files": files,
            "counts": self.summarize_subtree(folder_path),
            "skippedCount": skipped_in_current_folder,
        }

    def search_material_library_files(self, query: str | None = "", file_type: str | None = None) -> dict:
        normalized_query = str(query or "").strip().lower()
        normalized_file_type = self.normalize_file_type_filter(file_type)
        library_root = self.get_material_library_path()

        if not library_root.exists():
            return {
                "query": str(query or "").strip(),
                "file_type": normalized_file_type or "all",
                "total_matches": 0,
                "files": [],
            }

        matched_files: list[dict] = []
        for child_path in sorted(
            library_root.rglob("*"),
            key=lambda path: path.relative_to(library_root).as_posix().lower(),
        ):
            if not child_path.is_file():
                continue

            material_type = self.classify_material_type(child_path)
            if material_type is None:
                continue
            if normalized_file_type and material_type != normalized_file_type:
                continue

            relative_path = self.build_relative_path(child_path)
            search_haystack = f"{child_path.name} {relative_path}".lower()
            if normalized_query and normalized_query not in search_haystack:
                continue

            matched_files.append(self.build_file_descriptor(child_path))

        matched_files.sort(key=lambda file_descriptor: (file_descriptor["name"].lower(), file_descriptor["path"].lower()))
        return {
            "query": str(query or "").strip(),
            "file_type": normalized_file_type or "all",
            "total_matches": len(matched_files),
            "files": matched_files,
        }

    def ensure_unique_file_path(self, candidate_path: Path) -> Path:
        if not candidate_path.exists():
            return candidate_path

        base_name = candidate_path.stem
        extension = candidate_path.suffix
        counter = 1
        while True:
            next_candidate = candidate_path.with_name(f"{base_name} ({counter}){extension}")
            if not next_candidate.exists():
                return next_candidate
            counter += 1

    def prepare_upload_target(self, parent_relative_path: str | None, original_file_name: str) -> Path:
        parent_path, _ = self.resolve_library_path(
            parent_relative_path,
            must_exist=True,
            expect_directory=True,
        )
        sanitized_name = self.normalize_item_name(Path(original_file_name or "").name)
        if not sanitized_name:
            raise ValueError("File name is required.")

        material_type = self.classify_material_type(Path(sanitized_name))
        if material_type is None:
            raise ValueError("Unsupported file type.")

        return self.ensure_unique_file_path((parent_path / sanitized_name).resolve())

    def create_folder(self, parent_relative_path: str | None, folder_name: str) -> dict:
        parent_path, _ = self.resolve_library_path(
            parent_relative_path,
            must_exist=True,
            expect_directory=True,
        )
        sanitized_name = self.normalize_item_name(folder_name)
        target_path = (parent_path / sanitized_name).resolve()

        if target_path != self.get_material_library_path() and self.get_material_library_path() not in target_path.parents:
            raise ValueError("Invalid path.")
        if target_path.exists():
            raise FileExistsError("Folder already exists.")

        target_path.mkdir(parents=False, exist_ok=False)
        return self.build_folder_descriptor(target_path)

    def rename_folder(self, relative_path: str, new_name: str) -> dict:
        current_path, _ = self.resolve_library_path(
            relative_path,
            must_exist=True,
            expect_directory=True,
        )
        if current_path == self.get_material_library_path():
            raise ValueError("Root folder cannot be renamed.")

        sanitized_name = self.normalize_item_name(new_name)
        target_path = current_path.with_name(sanitized_name).resolve()
        if target_path == current_path:
            return self.build_folder_descriptor(current_path)

        if target_path != self.get_material_library_path() and self.get_material_library_path() not in target_path.parents:
            raise ValueError("Invalid path.")
        if target_path.exists():
            raise FileExistsError("Folder already exists.")

        current_path.rename(target_path)
        return self.build_folder_descriptor(target_path)

    def delete_folder(self, relative_path: str) -> None:
        target_path, _ = self.resolve_library_path(
            relative_path,
            must_exist=True,
            expect_directory=True,
        )
        if target_path == self.get_material_library_path():
            raise ValueError("Root folder cannot be deleted.")

        shutil.rmtree(target_path)

    def rename_file(self, relative_path: str, new_name: str) -> dict:
        current_path, _ = self.resolve_library_path(
            relative_path,
            must_exist=True,
            expect_directory=False,
        )
        sanitized_name = self.normalize_item_name(new_name, preserve_extension=current_path.suffix)
        target_path = current_path.with_name(sanitized_name).resolve()
        if target_path == current_path:
            return self.build_file_descriptor(current_path)

        if target_path != self.get_material_library_path() and self.get_material_library_path() not in target_path.parents:
            raise ValueError("Invalid path.")
        if target_path.exists():
            raise FileExistsError("File already exists.")

        current_path.rename(target_path)
        return self.build_file_descriptor(target_path)

    def delete_file(self, relative_path: str) -> None:
        target_path, _ = self.resolve_library_path(
            relative_path,
            must_exist=True,
            expect_directory=False,
        )
        if self.classify_material_type(target_path) is None:
            raise ValueError("Unsupported file type.")

        target_path.unlink()

    def resolve_material_library_item(self, relative_path: str) -> tuple[Path, dict]:
        target_path, _ = self.resolve_library_path(
            relative_path,
            must_exist=True,
            expect_directory=False,
        )

        material_type = self.classify_material_type(target_path)
        if material_type is None:
            raise ValueError("Unsupported material type.")

        return target_path, {
            "material_type": material_type,
            "mime_type": self.get_mime_type(target_path),
            "file_name": target_path.name,
        }
