import os
from sqlalchemy.ext.declarative import declarative_base

SQLAlchemyBase = declarative_base()  

def main():
    """Create all tables in the database."""
    print(
        f"Welcome from `{os.path.basename(__file__)}`: Nothing to do ___^__^__ ...\n\n"
    )

if __name__ == "__main__":
    
    main()
# python -m src.models.db_schemas.hr.schemas.hr_base
