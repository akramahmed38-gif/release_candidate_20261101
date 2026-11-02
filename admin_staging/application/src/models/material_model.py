import os
from typing import Callable, Sequence, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func
from models.base_model import BaseModel
from models.db_schemas import Material

SessionMaker = Callable[[], AsyncSession]

class MaterialModel(BaseModel):
    def __init__(self, db_client: SessionMaker) -> None:
        super().__init__()
        self.db_client = db_client

    @classmethod
    async def create_instance(cls, db_client: SessionMaker):
        instance = cls(db_client)
        return instance

    #! =============== Create Operations =============== !#

    async def create_material(self, material: Material) -> Material:
        async with self.db_client() as session:
            async with session.begin():
                session.add(material)
            await session.commit()
            await session.refresh(material)

            return material
    
    async def create_materials_bulk(self, materials: Sequence[Material]) -> Sequence[Material]:
        async with self.db_client() as session:
            async with session.begin():
                session.add_all(materials)
            await session.commit()
            for material in materials:
                await session.refresh(material)

            return materials

    async def is_material_exists(self, material_id: str) -> Tuple[bool, Material | None]:
        async with self.db_client() as session:
            async with session.begin():
                query = select(Material).where(Material.material_id == material_id)
                result = await session.execute(query)
                material = result.scalar_one_or_none()
                
                return material is not None, material

    #! =============== Read Operations =============== !#

    async def get_all_materials(self) -> Sequence[Material]:
        async with self.db_client() as session:
            async with session.begin():
                query = select(Material)
                materials = await session.execute(query)
                materials = materials.scalars().all()
                return materials

    async def get_material_by_id(self, material_id: str) -> Material | None:
        async with self.db_client() as session:
            async with session.begin():
                query = select(Material).where(Material.material_id == material_id)
                result = await session.execute(query)
                material = result.scalar_one_or_none()
                return material

    async def get_materials_by_group(self, material_group: str) -> Sequence[Material]:
        async with self.db_client() as session:
            async with session.begin():
                query = select(Material).where(Material.material_group == material_group)
                result = await session.execute(query)
                materials = result.scalars().all()
                return materials        

    async def get_materials_by_training_type(self, training_type: str) -> Sequence[Material]:
        async with self.db_client() as session:
            async with session.begin():
                query = select(Material).where(Material.material_training_type == training_type)
                result = await session.execute(query)
                materials = result.scalars().all()
                return materials

    async def get_materials_by_group_and_training_type(self, material_group: str, training_type: str) -> Sequence[Material]:
        async with self.db_client() as session:
            async with session.begin():
                query = select(Material).where(
                    Material.material_group == material_group,
                    Material.material_training_type == training_type
                )
                result = await session.execute(query)
                materials = result.scalars().all()
                return materials
    
    async def get_exams_for_material(self, material_id: str):
        async with self.db_client() as session:
            async with session.begin():
                material = await session.get(Material, material_id)
                if material is None:
                    return None
                await session.refresh(material)
                return material.exams  # returns list of Exam objects
    
    #! =============== Delete Operations =============== !#

    #! =============== Soft Delete
    async def remove_material_by_id(self, material_id: str) -> bool:
        # is_deleted
        async with self.db_client() as session:
            async with session.begin():
                query = select(Material).where(Material.material_id == material_id)
                result = await session.execute(query)
                material = result.scalar_one_or_none()
                if material is None:
                    return False
                material.is_deleted = True
                await session.commit()
                return True

    #! =============== Hard Delete
    async def remove_material_by_id_permanently(self, material_id: str) -> bool:
        # hard delete
        async with self.db_client() as session:
            async with session.begin():
                query = select(Material).where(Material.material_id == material_id)
                result = await session.execute(query)
                material = result.scalar_one_or_none()

                if material is None:
                    return False

                await session.delete(material)
                await session.commit()
                return True

    #! =============== Restore
    async def restore_material_by_id(self, material_id: str) -> bool:
        async with self.db_client() as session:
            async with session.begin():
                query = select(Material).where(Material.material_id == material_id)
                result = await session.execute(query)
                material = result.scalar_one_or_none()
                if material is None:
                    return False
                material.is_deleted = False
                await session.commit()
                return True

    #! =============== Update Operations =============== !#

