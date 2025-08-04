from pymongo import MongoClient

from config import MONGO


client = MongoClient(
    MONGO.HOST,
    MONGO.PORT
).inclass.module
