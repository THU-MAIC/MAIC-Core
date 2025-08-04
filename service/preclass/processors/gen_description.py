import os
import sys

from pymongo import MongoClient
from bson import ObjectId

from utils import get_channel, get_logger, now
from config import MONGO

from service import get_services
from data.lecture import find_file_snippet

prompt_summarize = f"这个GPT的任务是接受一张关于教学场景的PPT页面的图片和该PPT页面中的文本作为输入，然后用中文输出对这页PPT的描述和总结。它将专注于提取和理解PPT页面上的关键信息，并以简洁、准确的方式进行总结，确保总结内容在2-3句话以内。"
# prompt_summarize = f"The task of this GPT is to accept an image of a PPT slide about a teaching scenario and the text from that PPT slide as input, then output a description and summary of the slide in English. It will focus on extracting and understanding the key information from the slide and provide a concise and accurate summary, ensuring the summary is within 2-3 sentences."

system_summarize = [
			{
				"role": "system",
				"content": [
					{"type": "text", "text": prompt_summarize},
				],
			}
		]

def format_script(role: str, message: str, image_url: str = None):
	"""Format a message for GPT conversation with optional image support.

	Args:
		role (str): The role of the message sender ('system', 'user', or 'assistant')
		message (str): The text content of the message
		image_url (str, optional): Base64 encoded image data. Defaults to None.

	Returns:
		list: A list containing a single dictionary with the formatted message
	"""
	if image_url is None:
		return [
			dict(
				role=role,
				content=[
					dict(
						type="text",
						text=message,
						)
					],
				)
		]
	return [
		dict(
			role=role,
			content=[
				dict(
					type="text",
					text=message
					),
				dict(
					type="image_url",
					image_url=dict(url=f"data:image/png;base64,{image_url}")
					)
			],
		)
	]

class SERVICE:
	"""Service class for generating descriptions of lecture slides using GPT-4 Vision.
	
	This service processes lecture slides by analyzing both text content and images,
	generating concise Chinese descriptions using GPT-4 Vision API. It maintains job
	state in MongoDB and communicates through RabbitMQ for job processing.
	"""
	_collection = MongoClient(
		MONGO.HOST,
		MONGO.PORT
		).preclass.gen_description
	

	_result_collection = MongoClient(
		MONGO.HOST,
			MONGO.PORT
		).preclass.gen_description_result
	_queue_name = "preclass-gen_description"

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
		"""Trigger a new description generation job.

		Args:
			parent_service (str): Name of the parent service that triggered this job
			lecture_id (ObjectId): MongoDB ID of the lecture to process
			parent_job_id (ObjectId): MongoDB ID of the parent job

		Returns:
			str: The ID of the newly created job
		"""
		connection, channel = get_channel(SERVICE._queue_name)
		
		SERVICE._logger.info("Pushing job to MONGO")
		job_id = SERVICE._collection.insert_one(
			dict(
				parent_service=parent_service,
				created_time = now(),
				lecture_id=lecture_id,
				parent_job_id=parent_job_id,
				progress=-1,
				recent_scripts=[],
				openai_job_id=None,
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
		"""Process a description generation job from the queue.

		Handles the processing of individual slides, managing the conversation context
		with GPT-4 Vision, and storing the generated descriptions in the database.

		Args:
			ch: RabbitMQ channel
			method: RabbitMQ method frame
			properties: RabbitMQ properties
			body: Message body containing the job ID
		"""
		job_id = ObjectId(body.decode())
		job = SERVICE._collection.find_one(dict(_id=job_id))
		
		lecture_id = job["lecture_id"]
		progress = job["progress"]
		recent_scripts = job["recent_scripts"]

		openai_job_id = job["openai_job_id"]

		parent_service = job["parent_service"]
		parent_job_id = job["parent_job_id"]
		SERVICE._logger.info(f"Recieved PreClass GEN_DESCRIPTION Job - {lecture_id}, Progress: {progress}")

		# Recieved LLM generated content and add to db
		if progress!=-1:
			current_file_snippet = find_file_snippet(query=dict(lecture_id=lecture_id,idx=progress))
			new_input = format_script(
				role="user",
				message=current_file_snippet["content"],
				image_url=current_file_snippet.get("png_base64", None),
				)
			
			summarization = get_services()["openai"].get_response(openai_job_id)
			new_input[0]["content"] = new_input[0]["content"][:1]
			recent_scripts += new_input
			recent_scripts = recent_scripts + format_script(
				role="assistant",
				message=summarization)
			recent_scripts = recent_scripts[-6:]
			script_info = dict(
				lecture_id=lecture_id,
				index=current_file_snippet["idx"],
				description=summarization,
				source_content=dict(
					text=current_file_snippet["content"],
					pic=current_file_snippet.get("png_base64",None),
					source_file=[
						{
							"file_id": current_file_snippet["_id"],
							"file_type": "png",
							"index": current_file_snippet["idx"],
						}
					],
				),
			)
			SERVICE._result_collection.insert_one(script_info)
		
		progress += 1
		new_file_snippet = find_file_snippet(query=dict(lecture_id=lecture_id,idx=progress))
		if new_file_snippet:
			new_input = format_script(
				role="user",
				message=new_file_snippet["content"],
				image_url=new_file_snippet.get("png_base64", None),
				)
			messages = system_summarize + recent_scripts + new_input
			openai_job_id = get_services()["openai"].trigger(
				parent_service=SERVICE._queue_name,
				parent_job_id=job_id,
				model="gpt-4o-2024-08-06",
				messages=messages,
				max_tokens=4096,
				use_cache=True
				)
			SERVICE._collection.update_one(
				dict(_id=job_id),
				{"$set": dict(
					progress=progress,
					recent_scripts=recent_scripts,
					openai_job_id=openai_job_id,
				)}
			)
			ch.basic_ack(delivery_tag = method.delivery_tag)
		else:
			parent_connection, parent_channel = get_channel(parent_service)
			parent_channel.basic_publish(
				exchange="",
				routing_key=parent_service,
				body=str(parent_job_id)
			)
			parent_connection.close()
			SERVICE._logger.info(f"Conversion Complete For {lecture_id}")
			ch.basic_ack(delivery_tag = method.delivery_tag)
			
		

	@staticmethod
	def launch_worker():
		"""Launch the RabbitMQ worker to process description generation jobs.
		
		Starts consuming messages from the queue and handles graceful shutdown
		on keyboard interrupt.
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
	SERVICE._logger.warning("STARTING PRECLASS-GEN_DESCRIPTION SERVICE")
	SERVICE.launch_worker()