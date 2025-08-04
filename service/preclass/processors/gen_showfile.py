import sys
import os
from bson import ObjectId
from service.preclass.model import AgendaStruct, ShowFile
from pymongo import MongoClient
from utils import get_channel, get_logger, now
from config import MONGO

class SourceFileBinder:
	"""
	Binds source files to agenda nodes by extracting and associating ShowFile objects.
	
	Args:
		agenda (AgendaStruct): The agenda structure to process
	"""
	def __init__(self, agenda: AgendaStruct) -> None:
		self.agenda = agenda

	def extract(self):
		"""
		Traverses the agenda structure and binds source files to PPT nodes.
		
		Returns:
			AgendaStruct: The processed agenda with bound source files
		"""
		def bind_source_source(node):
			if node.type=="ppt":
				source_content = SERVICE._script_collection.find_one(dict(
					_id=node.content["_id"]
				))["source_content"]
				node.function.append(
					ShowFile(
						file_id=source_content["source_file"][0]["index"]
					)
				)
		agenda = self.agenda
		agenda.dfs_recursive_call(bind_source_source)
		return agenda

class SERVICE:
	"""
	Service class for handling show file generation tasks through a message queue system.
	Provides functionality for triggering jobs and processing them asynchronously.
	"""

	_collection = MongoClient(
		MONGO.HOST,
		MONGO.PORT
		).preclass.gen_showfile
	
	_pre_collection = MongoClient(
		MONGO.HOST,
		MONGO.PORT
		).preclass.gen_structure

	_script_collection = MongoClient(
		MONGO.HOST,
		MONGO.PORT
		).preclass.gen_description_result

	_queue_name = "preclass-gen_showfile"

	_logger = get_logger(
		__name__=__name__,
		__file__=__file__,
	)

	@staticmethod
	def trigger(
			parent_service: str,
			lecture_id: ObjectId,
			parent_job_id: ObjectId
			) -> str:
		"""
		Triggers a new show file generation job.

		Args:
			parent_service (str): Name of the parent service
			lecture_id (ObjectId): ID of the lecture to process
			parent_job_id (ObjectId): ID of the parent job

		Returns:
			str: The ID of the created job
		"""
		connection, channel = get_channel(SERVICE._queue_name)
		
		SERVICE._logger.info("Pushing job to MONGO")
		
		job_id = SERVICE._collection.insert_one(
			dict(
				parent_service=parent_service,
				created_time = now(),
				lecture_id=lecture_id,
				parent_job_id=parent_job_id
			)
		).inserted_id

		SERVICE._logger.info("Pushing job to RabbitMQ")
		channel.basic_publish(
			exchange="",
			routing_key=SERVICE._queue_name,
			body=str(job_id)
		)
		connection.close()
		
		SERVICE._logger.info("Job pushed to RabbitMQ")
		return job_id

	@staticmethod
	def callback(ch, method, properties, body):
		"""
		Callback function for processing show file generation jobs from the message queue.

		Args:
			ch: Channel object from RabbitMQ
			method: Method frame from RabbitMQ
			properties: Properties frame from RabbitMQ
			body: Message body containing the job ID
		"""
		job_id = ObjectId(body.decode())
		job = SERVICE._collection.find_one(dict(_id=job_id))
		
		lecture_id = job["lecture_id"]
		parent_service = job["parent_service"]
		parent_job_id = job["parent_job_id"]
		SERVICE._logger.debug(f"Recieved PreClass GEN_SHOWFILE Job - {lecture_id}")
		pre_job = SERVICE._pre_collection.find_one(dict(lecture_id=lecture_id))
		agenda = AgendaStruct.from_dict(pre_job["result_structure"])

		scripts = SourceFileBinder(
			agenda=agenda
		).extract()

		SERVICE._collection.update_one(
				dict(_id=job_id),
				{"$set": dict(
					result_showfile=scripts.to_dict(),
					completion_time=now()
				)}
			)
		parent_connection, parent_channel = get_channel(parent_service)
		parent_channel.basic_publish(
			exchange="",
			routing_key=parent_service,
			body=str(parent_job_id)
		)
		parent_connection.close()
		SERVICE._logger.info(f"ShowFile Generation Complete For {lecture_id}")
		ch.basic_ack(delivery_tag = method.delivery_tag)
		
		

	@staticmethod
	def launch_worker():
		"""
		Launches a worker process to consume and process jobs from the message queue.
		Can be terminated with CTRL+C.
		"""
		try:
			connection, channel = get_channel(SERVICE._queue_name)
			
			channel.basic_consume(
				queue=SERVICE._queue_name,
				on_message_callback=SERVICE.callback,
				auto_ack=False,
			)
			SERVICE._logger.info('Worker Launched. To exit press CTRL+C')
			channel.start_consuming()
		except KeyboardInterrupt:
			SERVICE._logger.warning('Shutting Off Worker')
			try:
				sys.exit(0)
			except SystemExit:
				os._exit(0)

if __name__ == "__main__":
	SERVICE._logger.warning("STARTING PRECLASS-GEN_SHOWFILE SERVICE")
	SERVICE.launch_worker()