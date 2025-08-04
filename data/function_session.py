from pymongo import MongoClient
# from datetime import datetime, timedelta
# from bson import ObjectId

from config import MONGO


client = MongoClient(
    MONGO.HOST,
    MONGO.PORT
).inclass.function_session


def create(
        user_id: str,
        course_id: str,
        agenda_id: str,
        session_id: str,
        function_idx: int,
        call: str,
        value: dict,
        status: dict,
        is_done: bool,
):
    return client.insert_one(dict(
        user_id=user_id,
        course_id=course_id,
        agenda_id=agenda_id,
        session_id=session_id,
        function_idx=function_idx,
        call=call,
        value=value,
        status=status,
        is_done=is_done,
    )).inserted_id
