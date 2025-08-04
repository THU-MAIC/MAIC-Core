import os
import sys

from pymongo import MongoClient
from bson import ObjectId

from utils import get_channel, get_logger, now
from config import MONGO

import fitz  # PyMuPDF

def convert_pdf_to_png(input_file, output_dir):
	"""
	Convert a PDF file to a series of PNG images, one for each page.

	Args:
		input_file (str): Path to the input PDF file
		output_dir (str): Directory where the PNG images will be saved

	Returns:
		None
	"""
	# Ensure the output directory exists
	if not os.path.exists(output_dir):
		os.makedirs(output_dir)

	# Open the PDF file
	doc = fitz.open(input_file)

	# Iterate through each page of the PDF
	for page_num in range(len(doc)):
		page = doc.load_page(page_num)  # Load the current page
		pix = page.get_pixmap()  # Render page to an image
		output_path = os.path.join(output_dir, f'{page_num + 1}.png')  # Define output path for the image
		pix.save(output_path)  # Save the image

	print(f"Conversion completed. Images are saved in '{output_dir}'.")


class SERVICE:
	"""
	Service class for handling PDF to PNG conversion jobs using RabbitMQ and MongoDB.
	
	Attributes:
		_collection: MongoDB collection for storing job information (internal use)
		_queue_name (str): Name of the RabbitMQ queue for this service (internal use)
		_logger: Logger instance for the service (internal use)
	"""

	_collection = MongoClient(
		MONGO.HOST,
		MONGO.PORT
		).preclass.pdf2png
	_queue_name = "preclass-pdf2png"

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
		Trigger a new PDF to PNG conversion job.

		Args:
			parent_service (str): Name of the parent service that triggered this job
			lecture_id (ObjectId): MongoDB ObjectId of the lecture
			parent_job_id (ObjectId): MongoDB ObjectId of the parent job

		Returns:
			str: The job ID of the created conversion job
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
		"""
		Callback function for processing PDF to PNG conversion jobs from RabbitMQ.

		Args:
			ch: RabbitMQ channel
			method: RabbitMQ method frame
			properties: RabbitMQ properties
			body: Message body containing the job ID

		Returns:
			None
		"""
		job_id = ObjectId(body.decode())
		job = SERVICE._collection.find_one(dict(_id=job_id))
		lecture_id, parent_service, parent_job_id = job["lecture_id"], job["parent_service"], job["parent_job_id"]
		SERVICE._logger.debug(f"Recieved PreClass PDF2PNG Job - {lecture_id}")

		convert_pdf_to_png(
			input_file=f"buffer/{lecture_id}/pdf/seed_file.pdf",
			output_dir=f"buffer/{lecture_id}/pngs"
			)

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
		"""
		Launch the worker to consume PDF to PNG conversion jobs from RabbitMQ queue.
		The worker runs indefinitely until interrupted with CTRL+C.

		Returns:
			None
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