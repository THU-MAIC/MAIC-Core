from fastapi import APIRouter
from fastapi.responses import JSONResponse
from service.inclass.main import INCLASS_SERVICE
from pydantic import BaseModel

router = APIRouter()


class InClassTriggerRequest(BaseModel):
    """
    InClassTriggerRequest is a Pydantic model that defines the request body for triggering an in-class session.

    Attributes:
    ----------
    session_id : str
        A string that uniquely identifies a session.
    user_input : str, optional
        A string or dictionary that represents user input or interactions, defaults to an empty string.
    """
    session_id:str
    user_input:str="" # Set this to str or dict for user input string or user interactions

class InClassGetStatusRequest(BaseModel):
    """
    InClassGetStatusRequest is a Pydantic model that defines the request body for retrieving in-class session status.

    Attributes:
    ----------
    session_id : str
        A string that uniquely identifies a session.
    """
    session_id:str
    

@router.post("/trigger")
def inclass_trigger(form: InClassTriggerRequest):
    """
    Endpoint to trigger an in-class session.

    Parameters:
    ----------
    form : InClassTriggerRequest
        A request containing the session ID and optional user input.

    Returns:
    -------
    dict : A dictionary indicating the success of the trigger operation with a status message.
    """
    INCLASS_SERVICE.trigger(**form.__dict__)
    return {"status": "inclass trigger success"}
    # try:
    #     session = SessionService.create(form.__dict__)
    #     return JSONResponse(**BaseSuccessCode.OK.http_response(data=session))
    # except MAICError as e:
    #     return e.http_response()
    # except Exception as e:
    #     return JSONResponse(
    #         **BaseErrorCode.UNKNOWN_ERROR.__message__(str(e)).http_response()
    #     )

@router.post("/get_status")
def inclass_get_status(form: InClassGetStatusRequest):
    """
    Get the status of an in-class session.

    Parameters:
    ----------
    form : InClassGetStatusRequest
        A request containing the session ID.

    Returns:
    -------
    JSONResponse : Provides the session status obtained from the INCLASS_SERVICE.
    """
    # print(form.__dict__)
    # print(**form.__dict__)
    return INCLASS_SERVICE.get_status(**form.__dict__)
