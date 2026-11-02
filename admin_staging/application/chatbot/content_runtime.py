"""Preload published learning generations without restarting the web portal."""
from __future__ import annotations
import asyncio
import time
from pathlib import Path

from .content_state import StaleSourceFilter


async def watch_content_generations(app, root, logger, interval=5):
    from fastapi.concurrency import run_in_threadpool
    from .config import load_config
    from .service import TrainingChatbot
    from .content_sync import refresh_stale_catalog
    root=Path(root)
    next_scan=0
    while True:
        try:
            config=await run_in_threadpool(load_config,root)
            if config.content_sync_enabled and time.monotonic()>=next_scan:
                await run_in_threadpool(refresh_stale_catalog,root)
                next_scan=time.monotonic()+30
            current=getattr(app.state,'chatbot_service',None)
            active=getattr(getattr(current,'config',None),'content_generation',None)
            desired=getattr(config,'content_generation',None)
            mode_changed=config.content_sync_enabled!=getattr(getattr(current,'config',None),'content_sync_enabled',False)
            if getattr(config,'content_sync_enabled',False) and ((desired and desired!=active) or mode_changed):
                def preload():
                    candidate=TrainingChatbot(root)
                    if getattr(candidate.config,'content_generation',None)!=desired:raise ValueError('Content generation changed during preload')
                    if not desired and candidate.vector_store.count()==0:raise ValueError('The existing index is not initialized')
                    candidate.retriever.refresh()
                    candidate.retriever.source_filter=StaleSourceFilter(root,desired)
                    return candidate
                candidate=await run_in_threadpool(preload)
                # Existing requests keep their own service reference. New ones
                # receive a fully loaded index, never a half-built collection.
                app.state.chatbot_service=candidate
                app.state.index_initialized=True
                app.state.content_sync_error=None
                logger.info('Published learning content loaded into the chatbot.')
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            # Do not log exception text, paths, prompts or credentials.
            app.state.content_sync_error=type(exc).__name__
            logger.warning('Learning content reload deferred; error_type=%s',type(exc).__name__)
        await asyncio.sleep(interval)
