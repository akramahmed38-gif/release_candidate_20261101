from models.db_schemas.learning.schemas.learning_base import SQLAlchemyBase
from models.db_schemas.learning.schemas.material import Material
from models.db_schemas.learning.schemas.exam import Exam
from models.db_schemas.learning.schemas.question import (
    Question,
    QuestionChoice,
    QuestionBankItem,
    QuestionBankChoice,
)
from models.db_schemas.learning.schemas.question_group import QuestionBankGroup, QuestionBankGroupMember
from models.db_schemas.learning.schemas.emplyee import Employee
from models.db_schemas.learning.schemas.employment_status_history import EmploymentStatusHistory
from models.db_schemas.learning.schemas.maintenance_job_lock import MaintenanceJobLock
from models.db_schemas.learning.schemas.otp_request import OTPRequest
from models.db_schemas.learning.schemas.branch import Branch
from models.db_schemas.learning.schemas.association_table import exam_materials, exam_employees
from models.db_schemas.learning.schemas.correction import ExamAttempt, ExamAnswer
from models.db_schemas.learning.schemas.daily_brief import (
    DailyBrief,
    DailyBriefAction,
    DailyBriefAudience,
    DailyBriefBlock,
    DailyBriefEmailBatch,
    DailyBriefEmailRecipient,
    DailyBriefFeedback,
    DailyBriefRead,
    DailyBriefView,
)
from models.db_schemas.learning.schemas.business_vocabulary import VocabularyCategory, VocabularyItem
