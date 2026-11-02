import os
import re
from fastapi import UploadFile
from models import ResponseSignalEnum
# from controllers import BaseController, MaterialController
from controllers.base_controller import BaseController
from controllers.material_controller import MaterialController

class DataController(BaseController):
    def __init__(self) -> None:
        super().__init__()
        self.size_scale = 1024 * 1024  # 1 MB in bytes

    def validate_uploaded_file(self, file: UploadFile) -> tuple[bool, ResponseSignalEnum]:
        # print(file.content_type)
        if file.content_type not in self.app_settings.FILE_ALLOWED_TYPES:
            return False, ResponseSignalEnum.FILE_TYPE_NOT_SUPPORTED.value

        if file.size > self.app_settings.FILE_MAX_SIZE * self.size_scale:
            return False, ResponseSignalEnum.FILE_SIZE_EXCEEDED.value

        return True, ResponseSignalEnum.FILE_UPLOAD_SUCCESS.value

    def clean_filename(self, file_name: str) -> str:
        # cleaned_file_name = re.sub(r"[^\w.]", "", file_name)
        # cleaned_file_name = cleaned_file_name.replace(" ", "_")
        # return cleaned_file_name
        return file_name

    def generate_unique_filepath(self, original_file_name: str, group_name: str, training_type: str) -> tuple[str, str]:
        group_dir_path = MaterialController().get_group_path(group_name=group_name, training_type=training_type)
        cleaned_file_name = self.clean_filename(original_file_name)

        new_file_path = ""
        while True:
            random_key = self.generate_random_string()
            print(f"Generated random key: {random_key}")
            new_filename = f"{cleaned_file_name}___{random_key}"
            new_file_path = os.path.join(group_dir_path, new_filename)
            if not os.path.exists(new_file_path):
                break

        return new_file_path, new_filename

def main():
    """Entry Point for the Program."""
    print(
        f"Welcome from `{os.path.basename(__file__).split('.')[0]}` Module (❁´◡`❁)"
    )
    controller = DataController()
    print(f"App Settings allowed file types: {controller.app_settings.FILE_ALLOWED_TYPES}")
    print(f"Unique File Path: {controller.generate_unique_filepath('test file @123!.txt', 101)}")

if __name__ == "__main__":
    main()
# python -m src.controllers.data_controller
