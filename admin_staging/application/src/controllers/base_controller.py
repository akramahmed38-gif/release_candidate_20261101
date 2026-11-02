"""Initialize the controller with settings and computed paths."""

import os
import random
import string
from utils.config_utils import get_settings
from models.exam_model import ExamModel
from models.material_model import MaterialModel

class BaseController:

    def __init__(self):
        """Initialize the BaseController with application settings and paths."""

        self.app_settings = get_settings()
        self.base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__))) # D:\Fawry\HRTrainingSystem
        self.materials_dir = os.path.join(self.base_dir, "assets", "materials") # D:\Fawry\HRTrainingSystem\assets\materials
        self.db_dir = os.path.join(self.base_dir, "assets", "db") # D:\Fawry\HRTrainingSystem\assets\database

    def generate_random_string(self, length: int = 8) -> str:

        if length <= 0:
            raise ValueError("Length must be a positive integer.")

        # print(f"Generating random string of length {"".join(random.choices(string.ascii_lowercase + string.digits, k=length))}")
        return "".join(random.choices(string.ascii_lowercase + string.digits, k=length))




    async def generate_random_id(self) -> str:
        return str(random.randint(1, 1000))


    # def get_database_path(self, db_name):

    #     database_path = os.path.join(self.db_dir, db_name)
    #     os.makedirs(self.db_dir, exist_ok=True)

    #     return database_path


if __name__ == "__main__":
    print(
        f"Welcome from `{os.path.basename(__file__).split('.')[0]}` Module. Nothing to do ^_____^!"
    )

    base = BaseController()
    print(f"Base Directory: {base.base_dir}")
    print(f"Materials Directory: {base.materials_dir}")
    print(f"Database Directory: {base.db_dir}")
    print(f"Database Path: {base.get_database_path('hr_learning_system.db')}")



# python -m src.controllers.base_controller