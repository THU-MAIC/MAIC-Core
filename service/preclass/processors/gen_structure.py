from service.preclass.model import AgendaStruct, PPTPageStruct
import os
import sys

from pymongo import MongoClient
from bson import ObjectId

from utils import get_channel, get_logger, now, preclass_context_size as context_size
from config import MONGO

from service import get_services
from tqdm import tqdm
from data.lecture import find_info

class Structurelizor:
	"""A class that generates hierarchical structure from PowerPoint presentation scripts.

	This class processes input scripts from PowerPoint slides and organizes them into a 
	hierarchical structure using LLM-based generation. It maintains section/subsection 
	relationships while preserving the original page order.

	Attributes:
		input_scripts: List of PowerPoint page scripts to process
		root_title: Title of the root agenda/section
		prompt: System prompt for the LLM to generate structured outlines
	"""

	def __init__(self, root_agenda_title, input_scripts):
		"""Initialize the Structurelizor.

		Args:
			root_agenda_title (str): Title for the root section of the structure
			input_scripts (list): List of PowerPoint page scripts to process
		"""
		self.input_scripts = input_scripts
		self.root_title = root_agenda_title
		self.prompt = """
This GPT focus solely on creating and organizing index outlines for documents or presentations. This involves structuring content accurately and concisely, using "-" to denote all elements, including different sections and sub-sections, while strictly adhering to the input content without making inferences or alterations. The primary role here is to organize outlines by introducing sections and subsections based on their thematic significance and hierarchical order. It's crucial that only the updated outline is outputted, with no additional words or explanations, ensuring users receive a clean, precise outline that directly reflects the content's organization and thematic division, facilitating straightforward navigation.
During each interaction with the user, this GPT is only allowed to do two things: append the given pages to the existing subsections or create a new subsection that goes under an existing section/subsection and append into it. When the pages shows different focus(e.g. when a page is the cover and some other pages are introduction of a course, they should go under different subsections).
When creating a new subsection, it should make sure that there are more than one pages that falls into it. The new section itself also have to be under an existing section provided within user's given outline. This means all the new sections created by this GPT has to at least have one tab(` `). Most pages (other than cover page) have to go under a subsection instead of directly going under the root section. A page cannot be the children of another page.
It is not allowed to abandon any pages. It is only allowed to add subsections and add tabs(`    `) to the user's given pages as an indication of a page is under a section. This means this GPT has to copy the exact words within user's given outline and concatenate new contents after it. It is not allow to do and replacement or short alias.
In the resulting outline, the pages still have to be ordered by their page number(labled as P[number]). The Page number for each page should also be included in the output as `- P[number]: [title of powerpoint page]`.
""".strip()
		self.system = [
			{
				"role": "system",
				"content": [
					{"type": "text", "text": self.prompt},
				],
			}
		]

	def format_prompt(self, history, current_page, future_page):
		line = "\n"
		prompt = f"""
Current Outline:
{history}

Current Page:
{str(current_page)}

Future Pages:
{line.join([str(page) for page in future_page])}
"""
		return prompt.strip()

	def parse_tab(self,string):
		converted_string = string.replace(" "*4,"\t")
		indent = len(converted_string) - len(converted_string.lstrip("\t"))
		return dict(indent=indent, content=string.lstrip("\t"))

	def find_trace(self, stack, target_page):
		trace = []
		target_page_num = target_page.split(":")[0][2:].strip()
		for record in stack:
			trace = trace[:record["indent"]] + [record["content"].strip()[2:]]
			record_page_num = record["content"].split(":")[0].lstrip()[2:]
			if target_page_num==record_page_num:
				trace[-1] = target_page
				return trace
		return None
	
	def call_generation(self, content, return_formatter=lambda x: x, use_cache=True, timeout=300, **kwargs):
		"""
		Call OpenAI generation with waiting capability.
		
		Args:
			content: The content to send to the model
			return_formatter: Function to format the response
			timeout: Maximum time to wait in seconds
			**kwargs: Additional arguments for the OpenAI trigger
		"""
		formatted_user_content = self.format_user(content)
		messages = self.system + formatted_user_content
		
		openai_job_id = get_services()["openai"].trigger(
			parent_service=SERVICE._queue_name,
			model="gpt-4o-2024-08-06",
			messages=messages,
			max_tokens=4096,
			use_cache=use_cache,
			**kwargs
		)
		response = get_services()["openai"].get_response_sync(openai_job_id, timeout=timeout)
		if response:
			return return_formatter(response)
		raise TimeoutError(f"OpenAI response timed out after {timeout} seconds")
	
	@staticmethod
	def format_user(content):
		return [{"role": "user", "content": [{"type": "text", "text": content}]}]

	@staticmethod
	def format_assistant(content):
		return [{"role": "assistant", "content": [{"type": "text", "text": content}]}]

	def extract(self):
		"""Process input scripts and generate hierarchical structure.

		Returns:
			AgendaStruct: Hierarchical structure of the presentation content
		"""
		scripts = self.input_scripts

		stringified_scripts = []
		for script in scripts:
			stringified_scripts.append(
				PPTPageStruct(
					page = dict(
						_id=script["_id"],
						index=script["index"],
						description=script["description"],
					),
					stringified = self.script2string(script)
				)
			)

		structurelized = AgendaStruct(title=self.root_title)

		bar = tqdm(total=len(stringified_scripts))

		def pop_page():
			page = stringified_scripts.pop(0)
			return page, stringified_scripts[:context_size]

		def structure_page():
			history = structurelized.get_structure_trace()
			current_page, future_page = pop_page()
			trace = None
			prompt = self.format_prompt(
				history=history,
				current_page=current_page,
				future_page=future_page
			)
			use_cache=True
			while not trace:
				if use_cache==False:
					print("Retrying")
				if future_page:
					prediction = self.call_generation(
						prompt,
						use_cache=use_cache,
						stop=str(future_page[0]).split(":")[0]+":"
						)
					if str(current_page) not in prediction:
						use_cache=False
						continue
				else:
					prediction = self.call_generation(
						prompt,
						use_cache=use_cache
						)
				parsed = [self.parse_tab(line) for line in prediction.split("\n")]

				trace = self.find_trace(parsed, target_page=str(current_page))
				if trace[0].strip() != self.root_title:
					tail = "\nThe new sections have to go under a subsection within the root section of " + self.root_title
					if not prompt.endswith(tail):
						prompt = prompt + tail
						trace = None
						continue
					else:
						trace = [self.root_title] + trace
				if structurelized.insert_page(current_page, trace):
					break
				else:
					use_cache=False
					trace=None
					continue

		while stringified_scripts:
			structure_page()
			bar.update(1)
		
		return structurelized

	def script2string(self, script):
		return f"- P{script['index']}: {script['description']}".replace("\n","")

class SERVICE:
	"""Service class for handling structure generation jobs via message queue.

	This service processes PowerPoint scripts to generate hierarchical content structure
	using MongoDB for storage and RabbitMQ for job queue management.
	"""

	_collection = MongoClient(
		MONGO.HOST,
		MONGO.PORT
		).preclass.gen_structure
	
	_pre_result_collection = MongoClient(
		MONGO.HOST,
		MONGO.PORT
		).preclass.gen_description_result
	
	_queue_name = "preclass-gen_structure"

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
		"""Trigger a new structure generation job.

		Args:
			parent_service (str): Name of the parent service
			lecture_id (ObjectId): MongoDB ID of the lecture
			parent_job_id (ObjectId): MongoDB ID of the parent job

		Returns:
			str: ID of the created job
		"""
		connection, channel = get_channel(SERVICE._queue_name)
		
		SERVICE._logger.info("Pushing job to MONGO")
		
		job_id = SERVICE._collection.insert_one(
			dict(
				parent_service=parent_service,
				created_time = now(),
				lecture_id=lecture_id,
				parent_job_id=parent_job_id,
				result_structure=None,
				raw_text=None,
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
		"""Process a structure generation job from the message queue.

		Args:
			ch: RabbitMQ channel
			method: RabbitMQ method frame
			properties: RabbitMQ properties
			body: Message body containing job ID
		"""
		job_id = ObjectId(body.decode())
		job = SERVICE._collection.find_one(dict(_id=job_id))
		
		lecture_id = job["lecture_id"]
		parent_service = job["parent_service"]
		parent_job_id = job["parent_job_id"]
		SERVICE._logger.debug(f"Recieved PreClass GEN_STRUCTURE Job - {lecture_id}")

		# get results of gen_description
		pre_results = list(SERVICE._pre_result_collection.find({"lecture_id": lecture_id}))
		
		if not pre_results:
			SERVICE._logger.warning(f"No pre-results found for lecture_id: {lecture_id}")
			return
		
		basename = find_info(dict(_id=lecture_id))["lecture_name"]

		structurelized = Structurelizor(
			root_agenda_title=basename,
			input_scripts=pre_results,
			).extract()
	
		for i in range(len(structurelized.children)):
			structurelized.children[i].flatten()
		
		SERVICE._collection.update_one(
			dict(_id=job_id),
			{"$set":dict(
				completion_time=now(),
				result_structure=structurelized.to_dict(),
				raw_text=structurelized.serialize(),
			)}
		)

		parent_connection, parent_channel = get_channel(parent_service)
		parent_channel.basic_publish(
			exchange="",
			routing_key=parent_service,
			body=str(parent_job_id)
		)
		parent_connection.close()
		SERVICE._logger.info(f"Structure Generation Complete For {lecture_id}")
		ch.basic_ack(delivery_tag = method.delivery_tag)
	

	@staticmethod
	def launch_worker():
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
	SERVICE._logger.warning("STARTING PRECLASS-GEN_STRUCTURE SERVICE")
	SERVICE.launch_worker()