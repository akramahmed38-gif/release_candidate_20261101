import os
from typing import Callable
# from sqlalchemy.ext.asyncio import AsyncSession
from utils import get_settings

# SessionMaker = Callable[[], AsyncSession]


class BaseModel:
    def __init__(self):
        self.app_settings = get_settings()

def main():
    """Entry point for testing the BaseDataModel class."""
    print(
        f"Welcome from `{os.path.basename(__file__).split('.')[0]}` module. Nothing to do ^_^!"
    )

if __name__ == "__main__":
    main()

# python -m src.models.base_data_model
