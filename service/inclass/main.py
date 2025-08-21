
import sys
import os

import pika
from pymongo import MongoClient
from bson import ObjectId, json_util
from openai import OpenAI, RateLimitError
from retry import retry
import json

from config import LLM, MONGO
from utils import get_channel, now, get_logger

from .classroom_session import ClassroomSession
from .functions import get_function
from enum import StrEnum


class INCLASS_SERVICE_STATUS(StrEnum):
	'''
	Define the status of an in-class session.
	
	Status:
	- `TRIGGERED`: the inclass worker is triggered in mongo
	- `CLASS_ENDED`: the inclass worker is finished
	- `STREAMING`: the inclass worker is waiting llms to generate
	- `PROCESSED`: the inclass worker is processed 
	'''
	TRIGGERED = "triggered" # the inclass worker is triggered in mongo
	CLASS_ENDED = "class_ended" # the inclass worker is finished
	STREAMING = "streaming" # the inclass worker is waiting llms to generate
	PROCESSED = "processed" # the inclass worker is processed 


class INCLASS_SERVICE:
	"""
	A service class for handling in-class session. It has four main methods:
	- trigger: Triggers an in-class session by processing user input and updating the session state.
	- launch_worker: Launches a worker that listens to a RabbitMQ queue and processes session jobs.
	- get_status: Retrieves the current status of a given in-class session.
	- get_updates: Retrieves updates for a given in-class session. (NOT IMPLEMENTED YET)
	"""
	collection = MongoClient(
		MONGO.HOST,
		MONGO.PORT
	).inclass.session
	queue_name = "inclass-main"

	logger = get_logger(
		__name__=__name__,
		__file__=__file__,
	)
	
	def add_user_to_lecture(
			user_id,
			lecture_id,
		):
		return INCLASS_SERVICE.collection.insert_one(
			dict(
				user_id=user_id,
				lecture_id=lecture_id,
				agent=[],
				parent_job_id=None,
				parent_service="",
			)
		)

	@staticmethod
	def trigger(
			session_id,
			user_input:str="", # Set this to str or dict for user input string or user interactions
			parent_service:str="",
			parent_job_id= None, # set this to be ObjectId if need callback
	) -> str:
		"""
		Triggers an in-class session by processing user input and updating the session state.

		Args:
			session_id (str): The unique identifier for the session.
			user_input (str, optional): The user input string or interactions. Defaults to an empty string.
			parent_service (str, optional): The parent service identifier.
			parent_job_id (ObjectId, optional): The parent job identifier for callback purposes.

		Returns:
			str: The session ID of the triggered session.
		"""

		connection = pika.BlockingConnection(
			pika.ConnectionParameters(host='localhost'))
		channel = connection.channel()

		channel.queue_declare(
			queue=INCLASS_SERVICE.queue_name,
			durable=True
		)
		session = ClassroomSession(session_id)
		function_session = session.get_current_function()
		if not function_session:
			INCLASS_SERVICE.logger.info(f"Class is over for Session ID {session_id}")
			return session_id
		executor_name = function_session['call']
		# print(function_session)
		if user_input:
			INCLASS_SERVICE.logger.info("Adding User Input to History")
			user_input = user_input.strip()
			if executor_name == 'AskQuestion':
				session.add_user_message(user_input, 'answer')
			else:
				session.add_user_message(user_input)

		INCLASS_SERVICE.logger.info("Setting Session Status to Triggered in Mongo")
		INCLASS_SERVICE.collection.update_one(
			dict(
				_id=ObjectId(session_id)
			),
			{
				"$set": {
					"state": INCLASS_SERVICE_STATUS.TRIGGERED.value,
					"parent_service": parent_service,
					"parent_job_id": parent_job_id,
				}
			}
		)

		INCLASS_SERVICE.logger.info("Pushing job to RabbitMQ")
		channel.basic_publish(
			exchange="",
			routing_key=INCLASS_SERVICE.queue_name,
			body=session_id
		)
		connection.close()

		INCLASS_SERVICE.logger.info("Job pushed to RabbitMQ")
		return session_id

	@staticmethod
	def launch_worker():
		"""
		Launches a worker that listens to a RabbitMQ queue and processes session jobs.

		Continuously consumes tasks from a RabbitMQ queue, executes in-class session logic,
		and manages session state based on interaction and generation outcomes.

		Returns:
			None
		"""
		try:
			connection = pika.BlockingConnection(pika.ConnectionParameters(host='localhost'))
			channel = connection.channel()

			channel.queue_declare(
				queue=INCLASS_SERVICE.queue_name,
				durable=True
			)
			def callback(ch, method, properties, body):
				session_id = ObjectId(body.decode())

				INCLASS_SERVICE.logger.info(f"Entering InClass Session Job - {session_id}")

				session = ClassroomSession(session_id)
				continue_generate = False
				if session.is_streaming(): # If LLM is still generating
					
					INCLASS_SERVICE.logger.info(f"Entering is_streaming - {session_id}")
					continue_generate = True
				else:
					function_session = session.get_current_function()
					if not function_session: # If Classroom Already Finished
						INCLASS_SERVICE.collection.update_one(
							dict(_id=ObjectId(session_id)),
							{ "$set": { "state": INCLASS_SERVICE_STATUS.CLASS_ENDED.value, } }
						)
						ch.basic_ack(delivery_tag = method.delivery_tag)
						return

					function_id = str(function_session['_id'])
					executor_name = function_session['call']
					executor = get_function(executor_name)

					value = function_session['value']

					continue_generate = executor.step(
						value=value,
						function_id=function_id,
						classroom_session=session,
					)
				if continue_generate:
					INCLASS_SERVICE.collection.update_one(
						dict(
							_id=ObjectId(session_id)
						),
						{ "$set": { "state": INCLASS_SERVICE_STATUS.STREAMING.value,} }
					)
					ch.basic_reject(delivery_tag=method.delivery_tag, requeue=True)
				else:
					INCLASS_SERVICE.collection.update_one(
						dict(
							_id=ObjectId(session_id)
						),
						{ "$set": { "state": INCLASS_SERVICE_STATUS.PROCESSED.value,} }
					)
					ch.basic_ack(delivery_tag = method.delivery_tag)

				INCLASS_SERVICE.logger.info(f"Session Processed {session_id}")
			
			channel.basic_consume(
				queue=INCLASS_SERVICE.queue_name,
				on_message_callback=callback,
				auto_ack=False,
			)
			INCLASS_SERVICE.logger.info('Worker Launched. To exit press CTRL+C')
			channel.start_consuming()
		except KeyboardInterrupt:
			INCLASS_SERVICE.logger.warning('Shutting Off Worker')
			try:
				sys.exit(0)
			except SystemExit:
				os._exit(0)
		
	@staticmethod
	def get_status(
		session_id=str,
	) -> str:
		"""
		Retrieves the current status of a given in-class session.

		Args:
			session_id (str): The unique identifier for the session.

		Returns:
			str: A JSON string representation of the session status or an error message if not found.
		"""
		try:
			# get session status
			session_status = INCLASS_SERVICE.collection.find_one(
				dict(
					_id=ObjectId(session_id)
				)
			)
			if not session_status:
				return "Session not found"
			# Convert the MongoDB document to a JSON string
			session_status_json = json.dumps(session_status, default=json_util.default)
			return session_status_json  # Return serialized JSON
		except Exception as e:
			INCLASS_SERVICE.logger.error(f"Error in INCLASS_SERVICE get_status: {e}")
			return "ERROR in INCLASS_SERVICE get_status"
		
	
	@staticmethod
	def get_updates():
		pass
	
# # TODO: Write Get Update Logic
# @staticmethod
# def get_response(job_id):
# 	record = INCLASS_SERVICE.collection.find_one(dict(_id=job_id))
# 	if not record:
# 		INCLASS_SERVICE.logger.error(f"Job With ID of {job_id} not found")
# 	elif "completion_time" not in record:
# 		INCLASS_SERVICE.logger.error(f"Retrieving Response From Un-Finished Job With ID of {job_id}.")
# 	else:
# 		return record["response"]
# 	return None

if __name__=="__main__":
	INCLASS_SERVICE.logger.warning("STARTING INCLASS SERVICE")
	INCLASS_SERVICE.launch_worker()
