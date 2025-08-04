from api.inclass import router as inclass_router
from api.preclass import router as preclass_router
from fastapi import FastAPI

app = FastAPI()
app.include_router(inclass_router, prefix="/inclass")
app.include_router(preclass_router, prefix="/preclass")