import os
from enum import Enum

class ResponseSignalEnum(Enum):

    FILE_TYPE_NOT_SUPPORTED = "file_type_not_supported"
    FILE_SIZE_EXCEEDED = "file_size_exceeded"
    FILE_UPLOAD_SUCCESS = "file_upload_success"
    FILE_RESTORE_SUCCESS = "file_restore_success"
    FILE_UPLOAD_FAILED = "file_upload_failed"

    FILES_RETRIEVED_SUCCESSFULLY = "files_retrieved_successfully"
    FILE_DELETED_SUCCESSFULLY = "file_deleted_successfully"
    FILE_NOT_FOUND = "file_not_found"
    FILE_NOT_DELETED = "file_not_deleted"

    # ========= Exam Related Signals =========
    EXAM_CREATED_SUCCESS = "exam_created_success"
    EXAM_RETREIVED_SUCCESS = "exam_retrieved_success"
    EXAM_DELETED_SUCCESS = "exam_deleted_success"
    ALL_EXAMS_DELETED_SUCCESS = "all_exams_deleted_success"



