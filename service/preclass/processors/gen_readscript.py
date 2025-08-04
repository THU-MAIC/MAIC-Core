import sys
import os
from config import MONGO
from pymongo import MongoClient
from bson import ObjectId
from tqdm import tqdm
from service.preclass.model import AgendaStruct, ReadScript
from utils import get_channel, get_logger, now, preclass_context_size as context_size
from service import get_services

class PPTScriptGenerator:
	"""
	PowerPoint Script Generator that processes slides and generates teaching scripts.

	This class handles:
	1. Processing PowerPoint slides from an agenda structure
	2. Generating teaching scripts using LLM for each slide
	3. Maintaining conversation context between slides

	Attributes:
		agenda (AgendaStruct): The agenda structure containing PPT slides and content
		prompt_script (str): System prompt for the LLM to generate teaching scripts
		system (list): System message configuration for LLM interactions
	"""

	def __init__(self, agenda: AgendaStruct) -> None:
		self.agenda = agenda

		self.prompt_script = "This agent speaks Chinese. Lecture Script Writer's primary function is to analyze PowerPoint (PPT) slides based on user inputs and the texts extracted from those slides. It then generates a script for teachers to teach students about the content illustrated on the page, assuming the role of the teacher who also made the slides. The script is intended for the teacher to read out loud, directly engaging with the audience without referring to itself as an external entity. It focuses on educational content, suitable for classroom settings or self-study. It emphasizes clarity, accuracy, and engagement in explanations, avoiding overly technical jargon unless necessary. The agent is not allowed to ask the user any questions even if the provided information is insufficient or unclear, ensuring the responses have to be a script. The script for each slide is limited to no more than two sentences, leaving most of the details to be discussed when interacting with the student's questions. The scripts for each slide has to be consistant to the previouse slide and it is important to make sure the agent's generated return can be directly joined as a fluent and continued script without any further adjustment. The agent should also never assume what is one the next slide before processing it. It adopts a friendly and supportive tone, encouraging learning and curiosity."

		self.system = [
			{
				"role": "system",
				"content": [
					{"type": "text", "text": self.prompt_script},
				],
			}
		]


	def extract(self):
		"""
		Processes the agenda structure and generates scripts for all PPT slides.

		Traverses through the agenda using DFS, generates teaching scripts for each PPT slide
		while maintaining conversation context between consecutive slides.

		Returns:
			AgendaStruct: The processed agenda with generated scripts attached to PPT nodes
		"""
		recent_scripts = []

		agenda = self.agenda

		ppt_num = 0
		def cnt_ppt_num(node):
			nonlocal ppt_num
			if node.type=="ppt":
				ppt_num+=1
		agenda.dfs_recursive_call(cnt_ppt_num)
		bar = tqdm(total=ppt_num, desc="Script Generating")
		
		def generate_script(node):
			nonlocal recent_scripts
			if node.type=="ppt":
				source_content = SERVICE._script_collection.find_one(dict(
					_id=node.content["_id"]
				))["source_content"]
				text = source_content["text"]
				png = source_content.get("pic",None)
				formatted_input = self.format_script(
					role="user",
					message=text,
					image_url=png,
					)
				script = self.iterate_call_script(
					recent_scripts,
					formatted_input
					)
				formatted_input[0]["content"] = formatted_input[0]["content"][:1]
				recent_scripts += formatted_input
				recent_scripts += self.format_script(
					role="assistant",
					message=script,
					)
				recent_scripts = recent_scripts[-2*context_size:]
				node.function.append(
					ReadScript(
						script=script
					)
				)
				bar.update()
		agenda.dfs_recursive_call(generate_script)
		return agenda

	def iterate_call_script(self, agent_messages, new_messages, timeout=300):
		"""
		Makes an LLM call to generate script with conversation context.

		Args:
			agent_messages (list): Previous conversation history
			new_messages (list): New messages to process
			timeout (int): Maximum time to wait in seconds (default: 300)

		Returns:
			str: Generated script response from LLM

		Raises:
			TimeoutError: If the response is not received within the timeout period
		"""
		messages = self.system + agent_messages + new_messages

		openai_job_id = get_services()["openai"].trigger(
			parent_service=SERVICE._queue_name,
			model="gpt-4o-2024-08-06",
			messages=messages,
			max_tokens=4096,
			use_cache=True
		)

		response = get_services()["openai"].get_response_sync(openai_job_id)
		if response:
			return response

		raise TimeoutError(f"OpenAI response timed out after {timeout} seconds")

	def format_script(self, role: str, message: str, image_url: str = None):
		"""
		Formats messages for LLM input in the required structure.

		Args:
			role (str): Role of the message sender ('user' or 'assistant')
			message (str): The text content of the message
			image_url (str, optional): Base64 encoded image URL if present

		Returns:
			list: Formatted message structure for LLM input
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
	"""
	Service class for managing PPT script generation jobs through a message queue.

	Handles:
	1. Job queue management using RabbitMQ
	2. MongoDB storage for job tracking
	3. Worker process for script generation

	Class Attributes:
		_collection: MongoDB collection for job storage
		_result_collection: MongoDB collection for results
		_queue_name (str): RabbitMQ queue name
		_logger: Service logger instance
	"""

	_pre_collection = MongoClient(
		MONGO.HOST,
		MONGO.PORT
		).preclass.gen_showfile

	_collection = MongoClient(
		MONGO.HOST,
		MONGO.PORT
		).preclass.gen_readscript
	
	_script_collection = MongoClient(
		MONGO.HOST,
		MONGO.PORT
		).preclass.gen_description_result

	_result_collection = MongoClient(
		MONGO.HOST,
		MONGO.PORT
		).preclass.gen_readscript_result
	_queue_name = "preclass-gen_readscript"

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
		Triggers a new script generation job.

		Args:
			parent_service (str): Name of the parent service
			lecture_id (ObjectId): ID of the lecture to process
			parent_job_id (ObjectId): ID of the parent job

		Returns:
			str: Generated job ID
		"""
		connection, channel = get_channel(SERVICE._queue_name)
		
		SERVICE._logger.info("Pushing job to MONGO")
		job_id = SERVICE._collection.insert_one(
			dict(
				parent_service=parent_service,
				created_time = now(),
				lecture_id=lecture_id,
				parent_job_id=parent_job_id,
				result_readscript=None
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
		Callback function for processing queue messages.

		Handles:
		1. Job data retrieval from MongoDB
		2. Script generation processing
		3. Result storage and parent service notification

		Args:
			ch: Channel object
			method: Delivery method
			properties: Message properties
			body: Message body containing job ID
		"""
		job_id = ObjectId(body.decode())
		job = SERVICE._collection.find_one(dict(_id=job_id))
		
		lecture_id = job["lecture_id"]

		parent_service = job["parent_service"]
		parent_job_id = job["parent_job_id"]
		SERVICE._logger.debug(f"Recieved PreClass GEN_DESCRIPTION Job - {lecture_id}")
		showfile_job = SERVICE._pre_collection.find_one(dict(lecture_id=lecture_id))
		scripts = PPTScriptGenerator(
		agenda=AgendaStruct.from_dict(showfile_job["result_showfile"])
		).extract()
	
		SERVICE._collection.update_one(
			dict(_id=job_id),
			{"$set":dict(
				completed_time=now(),
				result_readscript=scripts.to_dict()
			)}
		)

		parent_connection, parent_channel = get_channel(parent_service)
		parent_channel.basic_publish(
			exchange="",
			routing_key=parent_service,
			body=str(parent_job_id)
		)
		parent_connection.close()
		SERVICE._logger.info(f"ReadScript Generation Complete For {lecture_id}")
		ch.basic_ack(delivery_tag = method.delivery_tag)
			
		

	@staticmethod
	def launch_worker():
		"""
		Launches the worker process to consume queue messages.

		Starts a continuous process that listens for new jobs and processes them
		using the callback function. Can be terminated with CTRL+C.
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
	SERVICE._logger.warning("STARTING PRECLASS-GEN_READSCRIPT SERVICE")
	SERVICE.launch_worker()