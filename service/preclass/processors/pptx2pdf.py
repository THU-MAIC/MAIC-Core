import os
import sys

import subprocess

from pymongo import MongoClient
from bson import ObjectId

from utils import get_channel, get_logger, now
from config import MONGO

class SERVICE:
	"""A service class that handles PowerPoint to PDF conversion tasks.
	
	This service interfaces with MongoDB for job storage and RabbitMQ for job queue management.
	It uses a Docker container with LibreOffice to perform the actual PPTX to PDF conversion.
	"""
	_collection = MongoClient(
		MONGO.HOST,
		MONGO.PORT
		).preclass.pptx2pdf
	_queue_name = "preclass-pptx2pdf"

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
		"""Triggers a new PPTX to PDF conversion job.
		
		Args:
			parent_service (str): The name of the parent service that initiated this job
			lecture_id (ObjectId): MongoDB ObjectId of the lecture to be processed
			parent_job_id (ObjectId): MongoDB ObjectId of the parent job
			
		Returns:
			str: The job_id of the created conversion task
		"""
		connection, channel = get_channel(SERVICE._queue_name)
		
		SERVICE._logger.info("Pushing job to MONGO")
		job_id = SERVICE._collection.insert_one(
			dict(
				parent_service=parent_service,
				created_time = now(),
				lecture_id=lecture_id,
				parent_job_id=parent_job_id,
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
		"""Processes a PPTX to PDF conversion job from the queue.
		
		Executes the conversion using a Docker container running LibreOffice,
		updates the job status in MongoDB, and notifies the parent service upon completion.
		
		Args:
			ch: RabbitMQ channel
			method: RabbitMQ method frame
			properties: RabbitMQ properties
			body: Message body containing the job_id
		"""
		job_id = ObjectId(body.decode())
		job = SERVICE._collection.find_one(dict(_id=job_id))
		lecture_id, parent_service, parent_job_id = job["lecture_id"], job["parent_service"], job["parent_job_id"]
		SERVICE._logger.debug(f"Recieved PreClass PPTX2PDF Job - {lecture_id}")
		docker_command = [
			'docker', 'run', '--rm',
			'-v', f'{os.getcwd()}/buffer/{lecture_id}:/data',
			'preclass-converter',
			'libreoffice', '--headless', '--convert-to', 'pdf', '--outdir', 'pdf', 'seed_file.pptx'
		]

		result = subprocess.run(docker_command, check=True)
		if result.returncode == 0:
			SERVICE._collection.update_one(
				dict(_id=job_id),
				{"$set": dict(
					completion_time=now()
				)}
			)
			SERVICE._logger.info(f"Conversion Complete For {lecture_id}")
			parent_connection, parent_channel = get_channel(parent_service)
			parent_channel.basic_publish(
				exchange="",
				routing_key=parent_service,
				body=str(parent_job_id)
			)
			parent_connection.close()
			ch.basic_ack(delivery_tag = method.delivery_tag)

	@staticmethod
	def launch_worker():
		"""Launches the worker process to consume jobs from the RabbitMQ queue.
		
		Starts a continuous process that listens for conversion jobs and processes them.
		Can be terminated with CTRL+C.
		
		Raises:
			KeyboardInterrupt: When the worker is manually stopped
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
	SERVICE._logger.warning("STARTING PRECLASS-PPTX2PDF SERVICE")
	SERVICE.launch_worker()