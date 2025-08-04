from pymongo import MongoClient
from bson import ObjectId

from config import MONGO
from utils import now
client = MongoClient(
	MONGO.HOST,
	MONGO.PORT
	).lecture

def create_lecture(source_file_name):
	lecture_id = client.info.insert_one(dict(
		lecture_name=source_file_name,
		creation_date = now(),
	)).inserted_id
	return lecture_id

def insert_file_snippet(
	lecture_id: ObjectId,
	content: any,
	idx: int,
	file_type: str,
	**kwargs
	):
	file_snippet_id = client.file_snippet.insert_one(dict(
		lecture_id=lecture_id,
		content=content,
		idx=idx,
		file_type=file_type,
		**kwargs
	)).inserted_id
	return file_snippet_id

def find_info(
	query,
	**kwargs
	):
	return client.info.find_one(query,**kwargs)

def find_file_snippet(
	query,
	**kwargs
	):
	return client.file_snippet.find_one(query,**kwargs)