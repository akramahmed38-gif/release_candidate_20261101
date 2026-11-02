import os
from enum import Enum


class ProcessingEnum(Enum):
    PDF = ".pdf"
    DOCX = ".docx"


def main():
    """Entry Point for the Program."""
    print(
        f"Welcome from `{os.path.basename(__file__).split('.')[0]}` Module. (●'◡'●)"
    )


if __name__ == "__main__":
    main()