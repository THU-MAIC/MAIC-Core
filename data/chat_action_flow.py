from pymongo import MongoClient

from config import MONGO


client = MongoClient(
    MONGO.HOST,
    MONGO.PORT
).inclass.chat_action_flow


def create(
        # task_id,
        action,
        actor,
        session_id,
        step_id,
        **kwargs
):
    return client.insert_one(dict(
        # task_id=task_id,
        action=action,
        actor=actor,
        session_id=session_id,
        step_id=step_id,
        **kwargs
    )).inserted_id