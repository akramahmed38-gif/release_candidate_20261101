"""Simulation-only admin API, using the actual Training authentication."""
from fastapi import APIRouter,Depends,HTTPException,UploadFile,File
from pydantic import BaseModel,Field
from fastapi.concurrency import run_in_threadpool
from admin_knowledge import admin
import synthetic_store as store
router=APIRouter(prefix='/api/v1/admin/synthetic-documents',dependencies=[Depends(admin)])
def identity(user):return str(user.get('sub') or user.get('email'))
class Action(BaseModel):
    action:str=Field(max_length=50)
    note:str=Field(default='',max_length=240)
class Preview(BaseModel):
    field:str=Field(min_length=1,max_length=40)
    language:str=Field(default='en',max_length=2)
def invoke(function,*args):
    try:return function(*args)
    except store.WorkflowError as exc:raise HTTPException(409,str(exc)) from None
@router.get('')
def listing():return {'documents':store.list_documents(),'real_policy_approvals':0,'mode':'synthetic_workflow_test'}
@router.post('')
async def ingest(file:UploadFile=File(...),user=Depends(admin)):
    raw=await file.read(65537)
    return await run_in_threadpool(invoke,store.new_revision,raw,identity(user))
@router.post('/{namespace}/replace')
async def replace(namespace:str,file:UploadFile=File(...),user=Depends(admin)):
    raw=await file.read(65537)
    return await run_in_threadpool(invoke,store.new_revision,raw,identity(user),namespace)
@router.post('/{namespace}/action')
def action(namespace:str,payload:Action,user=Depends(admin)):
    return invoke(store.transition,namespace,payload.action,identity(user),payload.note)
@router.post('/{namespace}/preview')
def preview(namespace:str,payload:Preview,user=Depends(admin)):
    return invoke(store.preview,namespace,payload.field,payload.language,identity(user))
@router.get('/{namespace}/history')
def history(namespace:str):return {'revisions':invoke(store.history,namespace),'real_policy_approvals':0}

@router.post("/{namespace}/restore-drill")
def restore_drill(namespace:str,payload:Preview,user=Depends(admin)):
    from synthetic_restore import drill
    return invoke(drill,namespace,payload.field,payload.language,identity(user))
