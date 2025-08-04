from pymongo import MongoClient

from config import MONGO


client = MongoClient(
    MONGO.HOST,
    MONGO.PORT
).inclass.conv_msg


def create(
        action_flow_ids,
        session_id,
        action,
        speaker_id,
        user_type,
        agenda_id,
        course_id,
        content,
        created_time,
        have_voice,
        voice_done,
        voice_id,
):
    return client.insert_one(dict(
        action_flow_ids=action_flow_ids,
        session_id=session_id,
        action=action,
        speaker_id=speaker_id,
        user_type=user_type,
        agenda_id=agenda_id,
        course_id=course_id,
        content=content,
        created_time=created_time,
        have_voicce=have_voice,
        voice_done=voice_done,
        voice_id=voice_id,
    )).inserted_id
