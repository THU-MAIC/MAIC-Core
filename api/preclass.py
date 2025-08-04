from fastapi import APIRouter
from service.preclass.main import PRECLASS_MAIN
from pydantic import BaseModel

router = APIRouter()


class PreClassTriggerRequest(BaseModel):
    """
    PreClassTriggerRequest is a Pydantic model that defines the request body for triggering a pre-class session.

    Attributes:
    ----------
    source_file : str
        A string that represents the path to the source file.
    parent_service : str
        A string that represents the parent service.
    """
    source_file:str
    parent_service:str

class PreClassGetStatusRequest(BaseModel):
    """
    PreClassGetStatusRequest is a Pydantic model that defines the request body for retrieving pre-class session status.

    Attributes:
    ----------
    job_id : str
        A string that uniquely identifies a job.
    """
    job_id:str
    

@router.post("/trigger")
def preclass_trigger(form: PreClassTriggerRequest):
    """
    Endpoint to trigger a pre-class session.

    Parameters:
    ----------
    form : PreClassTriggerRequest
        A request containing the source file.

    Returns:
    -------
    dict : A dictionary indicating the success of the trigger operation with a status message.
    """
    job_id = PRECLASS_MAIN.trigger(**form.__dict__)
    return {"status": "preclass trigger success", "job_id": str(job_id)}


@router.post("/get_status")
def preclass_get_status(form: PreClassGetStatusRequest):
    """
    Get the status of a pre-class session.

    Parameters:
    ----------
    form : PreClassGetStatusRequest
        A request containing the job ID.

    Returns:
    -------
    JSONResponse : Provides the session status obtained from the PRECLASS_SERVICE.
    """
    return PRECLASS_MAIN.get_status(**form.__dict__)