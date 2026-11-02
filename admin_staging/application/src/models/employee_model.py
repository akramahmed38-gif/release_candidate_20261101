import os
from typing import Callable, Sequence, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, and_
from sqlalchemy.orm import selectinload
from collections import defaultdict
from models.db_schemas import Employee, Branch

SessionMaker = Callable[[], AsyncSession]
EMPLOYMENT_STATUS_ACTIVE = "active"

class EmployeeModel:

    def __init__(self, db_client: SessionMaker) -> None:
        self.db_client = db_client

    @classmethod
    async def create_instance(cls, db_client: SessionMaker):
        instance = cls(db_client)
        return instance

    #! =============== Create Operations =============== !#
    async def create_user(self, employee: Employee) -> Employee:
        async with self.db_client() as session:
            async with session.begin():
                session.add(employee)
            await session.commit()
            await session.refresh(employee)

            return employee

    async def create_branch(self, branch: Branch) -> Branch:
        async with self.db_client() as session:
            async with session.begin():
                session.add(branch)
            await session.commit()
            await session.refresh(branch)

            return branch

    async def is_user_exists_by_hrid(self, hr_id: str) -> Tuple[bool, Employee | None]: 
        async with self.db_client() as session:
            async with session.begin():
                query = select(Employee).where(Employee.hr_id == hr_id)
                result = await session.execute(query)
                employee = result.scalar_one_or_none()
                
                return employee is not None, employee

    async def is_user_exists_by_email(self, email: str) -> Tuple[bool, Employee | None]: 
        async with self.db_client() as session:
            async with session.begin():
                query = select(Employee).where(Employee.email == email)
                result = await session.execute(query)
                employee = result.scalar_one_or_none()

                return employee is not None, employee

    async def is_user_exists_by_email_and_hrid(self, email: str, hr_id: str) -> Tuple[bool, Employee | None]: 
        async with self.db_client() as session:
            async with session.begin():
                query = select(Employee).where((Employee.email == email) & (Employee.hr_id == hr_id))
                result = await session.execute(query)
                employee = result.scalar_one_or_none()

                return employee is not None, employee

    async def bulk_upsert_branches(self, branches: Sequence[dict]) -> tuple[int, int, list[dict]]:
        """
        Insert or update branches in bulk.
        Returns (created_count, updated_count, errors).
        """
        created = 0
        updated = 0
        errors: list[dict] = []

        async with self.db_client() as session:
            async with session.begin():
                existing = {
                    branch.branch_code: branch
                    for branch in (await session.execute(select(Branch))).scalars()
                }

                for payload in branches:
                    code = payload["branch_code"]
                    try:
                        if code in existing:
                            branch = existing[code]
                            for key, value in payload.items():
                                setattr(branch, key, value)
                            updated += 1
                        else:
                            branch = Branch(**payload)
                            session.add(branch)
                            existing[code] = branch
                            created += 1
                    except Exception as exc:
                        errors.append({"branch_code": code, "reason": str(exc)})

        return created, updated, errors

    #! =============== Read Operations =============== !#
    async def get_all_users(self, *, active_only: bool = False) -> Sequence[Employee]:
        async with self.db_client() as session:
            query = select(Employee).options(selectinload(Employee.branch))
            if active_only:
                query = query.where(Employee.employment_status == EMPLOYMENT_STATUS_ACTIVE)
            result = await session.execute(query)
            employees = result.scalars().all()

            return employees

    async def get_user_by_hrid(self, hr_id: str) -> Employee | None:
            async with self.db_client() as session:
                # query = select(Employee).where(Employee.hr_id == hr_id)
                query = select(Employee).options(selectinload(Employee.branch)).where(Employee.hr_id == hr_id)
                result = await session.execute(query)
                employee = result.scalar_one_or_none()

                return employee

    async def get_branch_by_code(self, branch_code: str) -> Branch | None:
        async with self.db_client() as session:
            query = select(Branch).where(Branch.branch_code == branch_code)
            result = await session.execute(query)
            return result.scalar_one_or_none()

    async def get_branch_by_name(self, branch_name: str) -> Branch | None:
        normalized_name = (branch_name or "").strip().lower()
        async with self.db_client() as session:
            query = select(Branch).where(func.lower(Branch.branch_name) == normalized_name)
            result = await session.execute(query)
            return result.scalar_one_or_none()

    async def is_branch_exists(self, branch_code: str) -> bool:
        async with self.db_client() as session:
            async with session.begin():
                query = select(Branch).where(Branch.branch_code == branch_code)
                result = await session.execute(query)
                branch = result.scalar_one_or_none()

                return branch is not None


    async def get_audience_hierarchy(
        self,
        regions: list[str] | None = None,
        areas: list[str] | None = None,
        *,
        active_only: bool = False,
    ):
        async with self.db_client() as session:
            branch_stmt = (
                select(
                    Branch.branch_region,
                    Branch.branch_area,
                    Branch.branch_code,
                    Branch.branch_name,
                    Branch.branch_division,
                    Branch.branch_sub_department,
                ).order_by(Branch.branch_region, Branch.branch_area, Branch.branch_name)
            )
            if regions:
                branch_stmt = branch_stmt.where(Branch.branch_region.in_(regions))
            if areas:
                branch_stmt = branch_stmt.where(Branch.branch_area.in_(areas))

            employee_stmt = select(
                Employee.branch_code,
                Employee.hr_id,
                Employee.name,
                Employee.title,
                Employee.department,
            )
            if active_only:
                employee_stmt = employee_stmt.where(Employee.employment_status == EMPLOYMENT_STATUS_ACTIVE)

            branches = await session.execute(branch_stmt)
            employees = await session.execute(employee_stmt)

        employees_by_branch = defaultdict(list)
        for branch_code, hr_id, name, title, dept in employees:
            employees_by_branch[branch_code].append(
                {
                    "hr_id": hr_id, 
                    "name": name, 
                    "title": title, 
                    "department": dept
                }
            )

        # regions_tree = {}
        regions_tree: dict[str, dict] = {}
        for region, area, code, name, division, subdept in branches:
            region_node = regions_tree.setdefault(region, {"region": region, "areas": {}})
            area_node = region_node["areas"].setdefault(area, {"area": area, "branches": []})
            area_node["branches"].append(
                {
                    "branch_code": code,
                    "branch_name": name,
                    "division": division,
                    "sub_department": subdept,
                    "employees": employees_by_branch.get(code, []),
                }
            )

        return [
            {
                "region": region_name,
                "areas": list(region_data["areas"].values()),
            }
            for region_name, region_data in regions_tree.items()
        ]

    async def get_existing_hr_ids(self, hr_ids: Sequence[str], *, active_only: bool = False) -> list[str]:
        if not hr_ids:
            return []
        async with self.db_client() as session:
            query = select(Employee.hr_id).where(Employee.hr_id.in_(hr_ids))
            if active_only:
                query = query.where(Employee.employment_status == EMPLOYMENT_STATUS_ACTIVE)
            result = await session.execute(query)
            return [row[0] for row in result.all()]

    async def get_hr_ids_by_branch_codes(
        self,
        branch_codes: Sequence[str],
        *,
        active_only: bool = False,
    ) -> tuple[list[str], list[str], list[str]]:
        """
        Returns (hr_ids, missing_branch_codes, branches_without_employees)
        """
        if not branch_codes:
            return [], [], []
        async with self.db_client() as session:
            branch_stmt = select(Branch.branch_code).where(Branch.branch_code.in_(branch_codes))
            branch_result = await session.execute(branch_stmt)
            valid_codes = [row[0] for row in branch_result.all()]

            missing_codes = [code for code in branch_codes if code not in set(valid_codes)]
            if not valid_codes:
                return [], missing_codes, []

            query = (
                select(Employee.hr_id, Employee.branch_code)
                .where(Employee.branch_code.in_(valid_codes))
            )
            if active_only:
                query = query.where(Employee.employment_status == EMPLOYMENT_STATUS_ACTIVE)
            result = await session.execute(query)
            hr_ids = []
            used_branch_codes = set()
            for hr_id, branch_code in result.all():
                hr_ids.append(hr_id)
                used_branch_codes.add(branch_code)

            branches_without_employees = [code for code in valid_codes if code not in used_branch_codes]

            return hr_ids, missing_codes, branches_without_employees

    #! =============== Delete Operations =============== !#
    async def delete_user_by_hr_id(self, hr_id: str) -> bool:
        async with self.db_client() as session:
            async with session.begin():
                query = select(Employee).where(Employee.hr_id == hr_id)
                result = await session.execute(query)
                employee = result.scalar_one_or_none()
                if employee:
                    await session.delete(employee)
                    await session.commit()
                    return True
                return False

    async def delete_all_users(self) -> int:
        async with self.db_client() as session:
            async with session.begin():
                # get all employees
                query = select(Employee)
                result = await session.execute(query)                
                # Loop through and delete each employee
                employees = result.scalars().all()
                count = 0
                for employee in employees:
                    await session.delete(employee)
                    count += 1
            await session.commit()
            return count

    #! =============== Update Operations =============== !#

    async def update_user(self, hr_id: str, new_data: dict) -> bool:
        async with self.db_client() as session:
            async with session.begin():
                query = select(Employee).where(Employee.hr_id == hr_id)
                result = await session.execute(query)
                employee = result.scalar_one_or_none()
                if employee:
                    for key, value in new_data.items():
                        setattr(employee, key, value)
                    session.add(employee)
                    await session.commit()
                    return True
                return False

    async def get_hr_ids_matching_filters(self, filters: dict | None, *, active_only: bool = False) -> list[str]:
        async with self.db_client() as session:
            # query = select(Employee.hr_id) # return only the hr_id column.
            query = select(Employee.hr_id).join(Branch, Employee.branch_code == Branch.branch_code)

            conditions = []

            def normalized(values):
                return [value for value in (values or []) if value]


            mapping = {
                Branch.branch_code: normalized(filters.get("branch_codes")),
                Branch.branch_name: normalized(filters.get("branches")),
                Branch.branch_area: normalized(filters.get("areas")),
                Branch.branch_region: normalized(filters.get("regions")),
                Branch.branch_division: normalized(filters.get("divisions")),
                Branch.branch_sub_department: normalized(filters.get("sub_departments")),
                Employee.title: normalized(filters.get("titles")),
                Employee.department: normalized(filters.get("departments")),
                Employee.hr_id: normalized(filters.get("hr_ids")),
            }
            # Key is the column, value is the list of values to filter by.

            # mapping = {
            #     Employee.hr_id: normalized(filters.get("hr_ids")),
            #     Employee.title: normalized(filters.get("titles")),
            #     Employee.branch: normalized(filters.get("branches")),
            #     Employee.area: normalized(filters.get("areas")),
            #     Employee.region: normalized(filters.get("regions")),
            #     Employee.division: normalized(filters.get("divisions")),
            #     Employee.department: normalized(filters.get("departments")),
            #     Employee.sub_department: normalized(filters.get("sub_departments")),
            # }
            # Key is the column, value is the list of values to filter by.

            for column, values in mapping.items():
                if values: # If a column has a non‑empty list of values
                    conditions.append(column.in_(values))

            if active_only:
                conditions.append(Employee.employment_status == EMPLOYMENT_STATUS_ACTIVE)

            if conditions:
                query = query.where(and_(*conditions))

            result = await session.execute(query.order_by(Employee.hr_id))
            return [row[0] for row in result.all()]
