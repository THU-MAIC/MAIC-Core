import sys
import os
import time
import pika
from pymongo import MongoClient
from bson import ObjectId
from openai import OpenAI, RateLimitError
from retry import retry

from config import LLM, MONGO
from utils import get_channel, now, get_logger

from service.llm.base import BASE_LLM_CACHE, NO_CACHE_YET


class OPENAI(BASE_LLM_CACHE):
	"""
	A class to interact with OpenAI's language model while using a cache mechanism to optimize requests.
	Inherits from BASE_LLM_CACHE.
	"""
	def __init__(self, api_key, cache_collection=None, **kwargs):
		"""
		Initializes the OPENAI class.

		Args:
			api_key (str): The API key to authenticate with OpenAI.
			cache_collection (MongoDB collection, optional): The cache collection to use for storing requests and responses.
			**kwargs: Additional keyword arguments for initializing the OpenAI client.
		"""
		self.llm_client = OpenAI(
			api_key=api_key,
			**kwargs
		)
		self.cost = dict()
		self.cache_collection = cache_collection
		if not self.cache_collection:
			self.cache_collection = MongoClient(
				MONGO.HOST,
				MONGO.PORT
				).llm.openai_cache

	@retry(RateLimitError, tries=3)
	def _call_model(self, query, use_cache):
		"""
		Calls the OpenAI model with the given query.

		Args:
			query (dict): The query to send to the OpenAI model.
			use_cache (bool): Whether to use cached responses if available.

		Returns:
			str: The response from the model, either from cache or a new request.
		"""
		response = NO_CACHE_YET
		if use_cache:
			response = self.check_cache(query)
		if response==NO_CACHE_YET:
			response = self.llm_client.chat.completions.create(
				**query
			)
			usage = response.usage.dict()
			for k,v in usage.items():
				if type(v) is int:
					self.cost[k] = self.cost.get(k,0)+v
				elif type(v) is dict:
					for inner_k, inner_v in v.items():
						if inner_v is int:
							self.cost[k+"."+inner_k] = self.cost.get(k+"."+inner_k,0)+inner_v
			response = response.choices[0].message.content
			self.write_cache(query, response, usage)
		return response

class OPENAI_SERVICE:
	"""
	A service class for managing OPENAI LLM requests through a queue mechanism using MongoDB and RabbitMQ.
	"""
	collection = MongoClient(
		MONGO.HOST,
		MONGO.PORT
		).llm.openai
	queue_name = "llm-openai"

	logger = get_logger(
		__name__=__name__,
		__file__=__file__,
	)

	@staticmethod
	def trigger(
		parent_service: str,
		parent_job_id= None, # set this to be ObjectId if need callback
		use_cache=False,
		**query
		) -> str:
		"""
		Creates and triggers a new job for an LLM request.

		Args:
			caller_service (str): The service initiating the request.
			use_cache (bool, optional): Whether to use cached responses if available.
			**query: The query to send to the LLM.

		Returns:
			str: The job ID of the triggered request.
		"""
		connection = pika.BlockingConnection(
			pika.ConnectionParameters(host='localhost'))
		channel = connection.channel()

		channel.queue_declare(
			queue=OPENAI_SERVICE.queue_name,
			durable=True
		)
		OPENAI_SERVICE.logger.info("Writing job to Mongo")
		job_id = OPENAI_SERVICE.collection.insert_one(
			dict(
				parent_service=parent_service,
				parent_job_id=parent_job_id,
				created_time = now(),
				use_cache=use_cache,
				query=query,
			)
		).inserted_id

		OPENAI_SERVICE.logger.info("Pushing job to RabbitMQ")
		channel.basic_publish(
			exchange="",
			routing_key=OPENAI_SERVICE.queue_name,
			body=str(job_id)
		)
		connection.close()

		OPENAI_SERVICE.logger.info("Job pushed to RabbitMQ")
		return job_id

	@staticmethod
	def launch_worker():
		"""
		Launches a worker to process jobs from the RabbitMQ queue.
		The worker interacts with the LLM and stores the response back in MongoDB.
		"""
		try:
			connection = pika.BlockingConnection(pika.ConnectionParameters(host='localhost'))
			channel = connection.channel()

			channel.queue_declare(
				queue=OPENAI_SERVICE.queue_name,
				durable=True
			)
			llm_controller = OPENAI(
				api_key=LLM.OPENAI.API_KEY,
				base_url = LLM.OPENAI.BASE_URL,
			)
			def callback(ch, method, properties, body):
				job_id = ObjectId(body.decode())
				OPENAI_SERVICE.logger.info(f"Recieved LLM Query - {job_id}")
				job = OPENAI_SERVICE.collection.find_one(dict(_id=job_id))
				query = job["query"]
				use_cache = job["use_cache"]
				
				parent_service = job["parent_service"]
				parent_job_id = job["parent_job_id"]

				OPENAI_SERVICE.logger.debug(f"Recieved LLM Query - {query}")

				ret = llm_controller._call_model(
					query=query,
					use_cache=use_cache,
					)
				OPENAI_SERVICE.collection.update_one(
					dict(_id=job_id),
					{"$set":dict(
						completion_time=now(),
						response=ret
					)}
				)
				OPENAI_SERVICE.logger.debug(f"LLM Output - {ret}")
				if parent_job_id:
					parent_connection, parent_channel = get_channel(parent_service)
					parent_channel.basic_publish(
						exchange="",
						routing_key=parent_service,
						body=str(parent_job_id)
					)
					parent_connection.close()
				ch.basic_ack(delivery_tag = method.delivery_tag)
			channel.basic_consume(
				queue=OPENAI_SERVICE.queue_name,
				on_message_callback=callback,
				auto_ack=False,
			)
			OPENAI_SERVICE.logger.info('Worker Launched. To exit press CTRL+C')
			channel.start_consuming()
		except KeyboardInterrupt:
			OPENAI_SERVICE.logger.warning('Shutting Off Worker')
			try:
				sys.exit(0)
			except SystemExit:
				os._exit(0)
	
	@staticmethod
	def get_response(job_id):
		"""
		Retrieves the response of a job with the given ID.

		Args:
			job_id (ObjectId): The ID of the job to retrieve the response for.

		Returns:
			str: The response of the job, or None if the job is not found or has not completed.
		"""
		record = OPENAI_SERVICE.collection.find_one(dict(_id=job_id))
		if not record:
			OPENAI_SERVICE.logger.error(f"Job With ID of {job_id} not found")
		elif "completion_time" not in record:
			OPENAI_SERVICE.logger.error(f"Retrieving Response From Un-Finished Job With ID of {job_id}.")
		else:
			return record["response"]
		return None
	
	@staticmethod
	def get_response_sync(job_id, timeout=300):
		"""
		Retrieves the response of a job with the given ID synchronously.

		Args:
			job_id (ObjectId): The ID of the job to retrieve the response for.
			timeout (int, optional): The maximum time to wait for the job to complete.

		Returns:
			str: The response of the job, or None if the job is not found or has not completed within the timeout.
		"""
		start_time = time.time()
		while (time.time() - start_time) < timeout:
			record = OPENAI_SERVICE.collection.find_one(dict(_id=job_id))
			if not record:
				OPENAI_SERVICE.logger.error(f"Job With ID of {job_id} not found")
				return None
			elif "completion_time" in record:
				return record["response"]
			time.sleep(1)  # Wait 1 second between checks
		
		OPENAI_SERVICE.logger.error(f"Retrieving Response From Job {job_id} Timed Out After {timeout} Seconds")
		return None
	
if __name__=="__main__":
	OPENAI_SERVICE.logger.warning("STARTING LLM SERVICE")
	OPENAI_SERVICE.launch_worker()