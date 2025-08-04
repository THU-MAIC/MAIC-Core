from bson import ObjectId
import pika
import sys
import os

from pymongo import MongoClient

from service import get_services
from utils import get_logger, now, change_file_path, get_channel
from config import MONGO

from data.lecture import create_lecture

class PRECLASS_MAIN:
	"""Main service class for handling the pre-class lecture processing pipeline.
	
	This class manages a multi-stage workflow for processing lecture materials,
	including converting presentations to different formats and generating
	various educational materials.
	"""

	class STAGE:
		"""Enumeration of processing stages for the pre-class pipeline."""
		START=0
		PPTX2PDF=1
		PDF2PNG=2
		PPT2TEXT=3

		GEN_DESCRIPTION=4
		GEN_STRUCTURE=5

		GEN_SHOWFILE=6
		GEN_READSCRIPT=7
		GEN_ASKQUESTION=8

		PUSH_AGENDA=99

		FINISHED=100
	_collection = MongoClient(
		MONGO.HOST,
		MONGO.PORT
		).preclass.main
	_queue_name = "preclass-main"

	_logger = get_logger(
	__name__=__name__,
	__file__=__file__,
	)

	@staticmethod
	def get_status(job_id: str):
		job = PRECLASS_MAIN._collection.find_one(dict(_id=ObjectId(job_id)))
		if job is None:
			return {"status": "job not found"}
		return job["stage"]

	@staticmethod
	def trigger(parent_service: str, source_file: str) -> str:
		"""Initiates a new pre-class processing job.
		
		Args:
			parent_service (str): Identifier of the parent service initiating this job
			source_file (str): Path to the source presentation file to be processed
			
		Returns:
			str: The ID of the created job
			
		Notes:
			Creates a new job in MongoDB and pushes it to RabbitMQ queue for processing.
			Moves the source file to a buffer location for processing.
		"""
		
		connection, channel = get_channel(PRECLASS_MAIN._queue_name)

		PRECLASS_MAIN._logger.info("Moving File To Buffer Location")

		filename = os.path.basename(source_file)
		basename, _ = os.path.splitext(filename)

		lecture_id = create_lecture(source_file_name=basename)

		buffer_path = f"buffer/{lecture_id}"
		change_file_path(
			source_file,
			buffer_path,
			"seed_file"
		)
		
		PRECLASS_MAIN._logger.info("Pushing job to MONGO")
		job_id = PRECLASS_MAIN._collection.insert_one(
			dict(
				parent_service=parent_service,
				created_time = now(),
				lecture_id=lecture_id,
				stage=PRECLASS_MAIN.STAGE.START,
				value=dict(),
			)
		).inserted_id

		PRECLASS_MAIN._logger.info("Pushing job to RabbitMQ")
		channel.basic_publish(
			exchange="",
			routing_key=PRECLASS_MAIN._queue_name,
			body=str(job_id)
		)
		connection.close()
		
		PRECLASS_MAIN._logger.info("Job pushed to RabbitMQ")
		return job_id

	@staticmethod
	def launch_worker():
		"""Launches the worker process for handling pre-class processing jobs.
		
		
		Establishes a connection to RabbitMQ and begins consuming messages from the queue.
		Each message triggers the appropriate stage of processing based on the job's
		current stage. The worker can be terminated using CTRL+C.
		
		Raises:
			KeyboardInterrupt: When the worker is manually stopped
		"""
		try:
			connection = pika.BlockingConnection(pika.ConnectionParameters(host='localhost'))
			channel = connection.channel()

			channel.queue_declare(
				queue=PRECLASS_MAIN._queue_name,
				durable=True
			)
			
			def callback(ch, method, properties, body):
				job_id = ObjectId(body.decode())
				job = PRECLASS_MAIN._collection.find_one(dict(_id=job_id))
				lecture_id, stage, value = job["lecture_id"], job["stage"], job["value"]
				PRECLASS_MAIN._logger.debug(f"Recieved PreClass Main Job - {lecture_id}")
				if stage==PRECLASS_MAIN.STAGE.START:
					PRECLASS_MAIN._collection.update_one(
						dict(_id=job_id),
						{"$set":dict(
							stage=PRECLASS_MAIN.STAGE.PPTX2PDF
						)}
					)
					sub_job_id = get_services()["preclass_pptx2pdf"].trigger(
						parent_service=PRECLASS_MAIN._queue_name,
						lecture_id=lecture_id,
						parent_job_id=job_id,
						)
					PRECLASS_MAIN._logger.debug(f"{job_id} Trigger PPTX2PDF Service {sub_job_id}")
					ch.basic_ack(delivery_tag = method.delivery_tag)
				elif stage==PRECLASS_MAIN.STAGE.PPTX2PDF:
					PRECLASS_MAIN._collection.update_one(
						dict(_id=job_id),
						{"$set":dict(
							stage=PRECLASS_MAIN.STAGE.PDF2PNG
						)}
					)
					
					sub_job_id = get_services()["preclass_pdf2png"].trigger(
						parent_service=PRECLASS_MAIN._queue_name,
						lecture_id=lecture_id,
						parent_job_id=job_id,
						)
					PRECLASS_MAIN._logger.debug(f"{job_id} Trigger PDF2PNG Service {sub_job_id}")
					ch.basic_ack(delivery_tag = method.delivery_tag)
				elif stage==PRECLASS_MAIN.STAGE.PDF2PNG:
					PRECLASS_MAIN._collection.update_one(
						dict(_id=job_id),
						{"$set":dict(
							stage=PRECLASS_MAIN.STAGE.PPT2TEXT
						)}
					)
					sub_job_id = get_services()["preclass_ppt2text"].trigger(
						parent_service=PRECLASS_MAIN._queue_name,
						lecture_id=lecture_id,
						parent_job_id=job_id,
						)
					PRECLASS_MAIN._logger.debug(f"{job_id} Trigger PPT2TEXT Service {sub_job_id}")
					ch.basic_ack(delivery_tag = method.delivery_tag)
				elif stage==PRECLASS_MAIN.STAGE.PPT2TEXT:
					PRECLASS_MAIN._collection.update_one(
						dict(_id=job_id),
						{"$set":dict(
							stage=PRECLASS_MAIN.STAGE.GEN_DESCRIPTION
						)}
					)
					sub_job_id = get_services()["preclass_gen_description"].trigger(
						parent_service=PRECLASS_MAIN._queue_name,
						lecture_id=lecture_id,
						parent_job_id=job_id,
						)
					PRECLASS_MAIN._logger.debug(f"{job_id} Trigger GEN_DESCRIPTION Service {sub_job_id}")
					ch.basic_ack(delivery_tag = method.delivery_tag)
				elif stage==PRECLASS_MAIN.STAGE.GEN_DESCRIPTION:
					PRECLASS_MAIN._collection.update_one(
						dict(_id=job_id),
						{"$set":dict(
							stage=PRECLASS_MAIN.STAGE.GEN_STRUCTURE
						)}
					)
					sub_job_id = get_services()["preclass_gen_structure"].trigger(
						parent_service=PRECLASS_MAIN._queue_name,
						lecture_id=lecture_id,
						parent_job_id=job_id
						)
					
					PRECLASS_MAIN._logger.debug(f"{job_id} Trigger GEN_STRUCTURE Service {sub_job_id}")
					ch.basic_ack(delivery_tag = method.delivery_tag)
				elif stage==PRECLASS_MAIN.STAGE.GEN_STRUCTURE:
					PRECLASS_MAIN._collection.update_one(
						dict(_id=job_id),
						{"$set":dict(
							stage=PRECLASS_MAIN.STAGE.GEN_SHOWFILE
						)}
					)
					sub_job_id = get_services()["preclass_gen_showfile"].trigger(
						parent_service=PRECLASS_MAIN._queue_name,
						lecture_id=lecture_id,
						parent_job_id=job_id
						)
					PRECLASS_MAIN._logger.debug(f"{job_id} Trigger GEN_SHOWFILE Service {sub_job_id}")
					ch.basic_ack(delivery_tag = method.delivery_tag)
				elif stage==PRECLASS_MAIN.STAGE.GEN_SHOWFILE:
					PRECLASS_MAIN._collection.update_one(
						dict(_id=job_id),
						{"$set":dict(
							stage=PRECLASS_MAIN.STAGE.GEN_READSCRIPT
						)}
					)
					sub_job_id = get_services()["preclass_gen_readscript"].trigger(
						parent_service=PRECLASS_MAIN._queue_name,
						lecture_id=lecture_id,
						parent_job_id=job_id
						)
					PRECLASS_MAIN._logger.debug(f"{job_id} Trigger GEN_READSCRIPT Service {sub_job_id}")
					ch.basic_ack(delivery_tag = method.delivery_tag)
				elif stage==PRECLASS_MAIN.STAGE.GEN_READSCRIPT:
					PRECLASS_MAIN._collection.update_one(
						dict(_id=job_id),
						{"$set":dict(
							stage=PRECLASS_MAIN.STAGE.GEN_ASKQUESTION
						)}
					)	
					sub_job_id = get_services()["preclass_gen_askquestion"].trigger(
						parent_service=PRECLASS_MAIN._queue_name,
						lecture_id=lecture_id,
						parent_job_id=job_id
						)
					PRECLASS_MAIN._logger.debug(f"{job_id} Trigger GEN_ASKQUESTION Service {sub_job_id}")
					ch.basic_ack(delivery_tag = method.delivery_tag)
				else:
					PRECLASS_MAIN._logger.info(f"Stage: {stage}")
			channel.basic_consume(
				queue=PRECLASS_MAIN._queue_name,
				on_message_callback=callback,
				auto_ack=False,
			)
			PRECLASS_MAIN._logger.info('Worker Launched. To exit press CTRL+C')
			channel.start_consuming()
		except KeyboardInterrupt:
			PRECLASS_MAIN._logger.warning('Shutting Off Worker')
			try:
				sys.exit(0)
			except SystemExit:
				os._exit(0)

if __name__=="__main__":
	PRECLASS_MAIN._logger.warning("STARTING PRECLASS-MAIN SERVICE")
	PRECLASS_MAIN.launch_worker()