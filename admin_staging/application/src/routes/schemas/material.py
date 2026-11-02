from pydantic import BaseModel, Field
from typing import Optional

class MaterialRequest(BaseModel):
    material_id: str = Field(..., description="Unique identifier for the material")
    material_name: str = Field(..., description="Name of the material")
    material_group: str = Field(..., description="Group to which the material belongs")
    material_training_type: str = Field(..., description="Type of training for the material")
    exam_id: Optional[str] = Field(None, description="Associated exam ID, if any")
