from pymongo import MongoClient

from config import MONGO


# client = MongoClient(
#     MONGO.HOST,
#     MONGO.PORT
# ).inclass.agenda

# change to lecture database
client = MongoClient(
    MONGO.HOST,
    MONGO.PORT
).lecture.agenda