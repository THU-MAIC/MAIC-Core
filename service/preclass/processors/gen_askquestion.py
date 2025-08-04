from pymongo import MongoClient
from bson import ObjectId
import sys
import os
from tqdm import tqdm
from service.preclass.model import AgendaStruct, ReadScript, AskQuestion
from service.preclass.processors.qa_utils import parse_qa
from config import MONGO
from utils import get_channel, get_logger, now, preclass_context_size as context_size
from service import get_services

class QAGenerator:
	"""
	Generator for creating AskQuestion functions during preclass generation.
	
	This class processes an agenda structure and generates multiple-choice questions
	based on the teaching content (scripts) found within the agenda nodes.
	
	Args:
		agenda (AgendaStruct): The agenda structure containing teaching content and nodes
	"""
	def __init__(self, agenda: AgendaStruct) -> None:
		self.agenda = agenda

	def get_prompt(self, recent_scripts):
		"""
		Generates a prompt for the LLM to create multiple-choice questions.
		
		Args:
			recent_scripts (list[str]): List of recent teaching scripts, with the last one
				being the current content to focus on
		
		Returns:
			str: The formatted prompt for question generation, or None if input is invalid
		"""
		if len(recent_scripts) < 1:
			print("script len < 1, error")
			prompt = None
		elif len(recent_scripts) == 1:
			text = recent_scripts[0]
			prompt = f'请根据给出的教学内容，出3道选择题及答案，并说明该题目引用了哪些段落的教学内容。所出题目需要与教学内容紧密相关。\n\n\
				<教学内容开始>\n{text}\n<教学内容结束>\n\n\
				选择题格式如下所示：\n\n\
				问题：[问题描述]（注明多选还是单选）\n\
				A. [选项A]\n\
				B. [选项B]\n\
				C. [选项C]\n\
				D. [选项D]\n\
				E. [选项E]\n\
				答案：[该题目答案]\n\
				引用文本：[出题所引用的教学内容文本]\n\n\
				注意，若题目类型为多选题，则正确答案一定超过1个，否则为单选题。\n\
				模型输出仅包含3道问题、选项、答案与引用文本，且严格按照上述规定的选择题格式进行输出。在书写答案时，请直接输出选项所对应的索引字母，不要重复选项的内容。'
			# prompt = f'Please create 3 multiple-choice questions and answers based on the given teaching content, and specify which paragraphs of the teaching content were referenced for each question. The questions should be closely related to the teaching content.\n\n\
			# <Start of Teaching Content>\n{text}\n<End of Teaching Content>\n\n\
			# The format of the multiple-choice questions is as follows:\n\n\
			# Question: [Description of the question] (Specify whether it is single choice or multiple choice)\n\
			# A. [Option A]\n\
			# B. [Option B]\n\
			# C. [Option C]\n\
			# D. [Option D]\n\
			# E. [Option E]\n\
			# Answer: [Correct answer for the question]\n\
			# Referenced Text: [Teaching content referenced for the question]\n\n\
			# Note: If the question type is multiple choice, there must be more than one correct answer; otherwise, it should be single choice.\n\
			# The model output should contain only 3 questions, options, answers, and referenced text, strictly following the format specified above. When writing the answers, only output the corresponding letter index of the options without repeating the content of the options.'

		else:
			previous_text = ""
			for i in range(len(recent_scripts) - 1):
				previous_text += recent_scripts[i] + "\n"
			current_text = recent_scripts[-1]
			prompt = f'请根据给出的教学内容，出3道选择题及答案，并说明该题目引用了哪些段落的教学内容。其中，教学内容分为“先前教学内容”与“当前教学内容”，所出题目需要与“当前教学内容”紧密相关，且与“先前教学内容”部分相关（即主要基于“当前教学内容”出题，同时需要兼顾“先前教学内容”）。\n\n\
				<先前教学内容开始>\n{previous_text}\n<先前教学内容结束>\n\n\
				<当前教学内容开始>\n{current_text}\n<当前教学内容结束>\n\n\
				选择题格式如下所示：\n\n\
				问题：[问题描述]（注明多选还是单选）\n\
				A. [选项A]\n\
				B. [选项B]\n\
				C. [选项C]\n\
				D. [选项D]\n\
				E. [选项E]\n\
				答案：[该题目答案]\n\
				引用文本：[出题所引用的教学内容文本]\n\n\
				注意，若题目类型为多选题，则正确答案一定超过1个，否则为单选题。\n\
				模型输出仅包含3道问题、选项、答案与引用文本，且严格按照上述规定的选择题格式进行输出。在书写答案时，请直接输出选项所对应的索引字母，不要重复选项的内容。'
			# prompt = f'Please create 3 multiple-choice questions and answers based on the given teaching content, and specify which paragraphs of the teaching content were referenced for each question. The teaching content is divided into "Previous Teaching Content" and "Current Teaching Content". The questions should be closely related to the "Current Teaching Content" while also being connected to the "Previous Teaching Content" (i.e., primarily based on the "Current Teaching Content" with consideration of the "Previous Teaching Content").\n\n\
			# <Start of Previous Teaching Content>\n{previous_text}\n<End of Previous Teaching Content>\n\n\
			# <Start of Current Teaching Content>\n{current_text}\n<End of Current Teaching Content>\n\n\
			# The format of the multiple-choice questions is as follows:\n\n\
			# Question: [Description of the question] (Specify whether it is single choice or multiple choice)\n\
			# A. [Option A]\n\
			# B. [Option B]\n\
			# C. [Option C]\n\
			# D. [Option D]\n\
			# E. [Option E]\n\
			# Answer: [Correct answer for the question]\n\
			# Referenced Text: [Teaching content referenced for the question]\n\n\
			# Note: If the question type is multiple choice, there must be more than one correct answer; otherwise, it should be single choice.\n\
			# The model output should contain only 3 questions, options, answers, and referenced text, strictly following the format specified above. When writing the answers, only output the corresponding letter index of the options without repeating the content of the options.'
		return prompt    


	def gen_qa(self, recent_scripts, use_cache=True, timeout=300):
		"""
		Generates questions and answers using an LLM based on the provided scripts.
		
		Args:
			recent_scripts (list[str]): List of recent teaching scripts
			use_cache (bool, optional): Whether to use cached LLM responses. Defaults to True
			timeout (int, optional): Maximum time to wait in seconds. Defaults to 300
			
		Returns:
			str: Raw LLM response containing generated questions and answers
			
		Raises:
			TimeoutError: If the response is not received within the timeout period
		"""
		content = self.get_prompt(recent_scripts)
		messages = [{"role": "user", "content": content}]
		openai_job_id = get_services()["openai"].trigger(
			parent_service=SERVICE._queue_name,
			model="gpt-4o-2024-08-06",
			messages=messages,
			max_tokens=4096,
			use_cache=use_cache
		)
		
		response = get_services()["openai"].get_response_sync(openai_job_id)
		if response:
			return response
		
		raise TimeoutError(f"OpenAI response timed out after {timeout} seconds")


	def extract(self):
		"""
		Processes the agenda structure to generate and insert questions at appropriate nodes.
		
		Traverses the agenda tree, identifies nodes requiring questions, generates Q&A content
		using the LLM, and attaches AskQuestion functions to the nodes.
		
		Returns:
			AgendaStruct: The modified agenda structure with added question functions
		"""
		# only keep the last 5 records
		recent_scripts = []  

		agenda = self.agenda
		
		ppt_num = 0
		def cnt_ppt_num(node):
			nonlocal ppt_num
			if node.type=="ppt":
				ppt_num+=1
		agenda.dfs_recursive_call(cnt_ppt_num)
		bar = tqdm(total=ppt_num, desc="Question Generating")

		for i in range(len(agenda.children)):
			if agenda.children[i].type=="ppt":
				continue
			if len(agenda.children[i].children) >= 3:
				agenda.children[i].children[-1].function.append(AskQuestion)

		def generate_question(node):
			nonlocal recent_scripts
			if node.type=="ppt":
				function_list = node.function
				for function in function_list:
					if function.call == "ReadScript":
						script = function.value['script']
						recent_scripts = recent_scripts[-context_size:]
						recent_scripts.append(script)
						# assume ReadScript function only appears once in each ppt
						break
				
				if node.function[-1] == AskQuestion:
					node.function = node.function[:-1]
					# generate qa based on recent_scripts
					raw_reply = self.gen_qa(recent_scripts) 
					# format qa
					qas = parse_qa(raw_reply)  
		
					cnt = 0
					max_retries = 3
					while len(qas) != 3 and cnt < max_retries:
						raw_reply = self.gen_qa(recent_scripts, use_cache=False)
						qas = parse_qa(raw_reply)

					for qa in qas:
						question, question_type, selects, answer, reference = qa.values()
						# create 3 AskQuestion functions per page
						node.function.append(
							AskQuestion(
								question,
								question_type,
								selects,
								answer,
								reference,
								# recent_scripts
							)
						)
				bar.update()
		agenda.dfs_recursive_call(generate_question)
		return agenda

class SERVICE:
	"""
	Service class for managing the question generation workflow using RabbitMQ.
	
	Handles job queuing, processing, and result storage for the question generation
	service. Uses MongoDB for persistent storage and RabbitMQ for job queue management.
	"""
	_collection = MongoClient(
		MONGO.HOST,
		MONGO.PORT
		).preclass.gen_askquestion
	
	_pre_collection = MongoClient(
		MONGO.HOST,
		MONGO.PORT
		).preclass.gen_readscript

	_agenda_collection = MongoClient(
		MONGO.HOST,
		MONGO.PORT
		).preclass.agenda
	
	_lecture_agenda_collection = MongoClient(
		MONGO.HOST,
		MONGO.PORT
		).lecture.agenda

	_queue_name = "preclass-gen_askquestion"

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
		Triggers a new question generation job.
		
		Args:
			parent_service (str): Name of the parent service
			lecture_id (ObjectId): ID of the lecture being processed
			parent_job_id (ObjectId): ID of the parent job
			
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
				result_askquestion=None
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
		Callback function for processing question generation jobs from RabbitMQ.
		
		Args:
			ch: RabbitMQ channel
			method: RabbitMQ method frame
			properties: RabbitMQ properties
			body: Message body containing the job ID
		"""
		job_id = ObjectId(body.decode())
		job = SERVICE._collection.find_one(dict(_id=job_id))
		
		lecture_id = job["lecture_id"]

		parent_service = job["parent_service"]
		parent_job_id = job["parent_job_id"]
		SERVICE._logger.debug(f"Recieved PreClass GEN_ASKQUESTION Job - {lecture_id}")

		readscript_job = SERVICE._pre_collection.find_one(dict(lecture_id=lecture_id))
		agenda = AgendaStruct.from_dict(readscript_job["result_readscript"])

		scripts = QAGenerator(
			agenda=agenda
		).extract()

		SERVICE._collection.update_one(
			dict(_id=job_id),
			{"$set": dict(
				completed_time=now(),
				result_askquestion=scripts.to_dict()
			)}
		)

		# push agenda to mongo
		def push(node, lecture_agenda_parent_id=None, agenda_parent_id=None, index=0):
			if node.type == "ppt":
				d = dict(
					lecture_id=lecture_id,
					parent_id=agenda_parent_id,
					index=index,
					description=node.content["description"],
					type="ppt",
					function=[func.to_dict() for func in node.function]
				)
				agenda_id = SERVICE._agenda_collection.insert_one(d).inserted_id

				d_lecture = d.copy()
				del d_lecture["_id"]
				d_lecture["preclass_agenda_id"] = agenda_id
				d_lecture["parent_id"] = lecture_agenda_parent_id
				lecture_agenda_id = SERVICE._lecture_agenda_collection.insert_one(d_lecture).inserted_id

			else:
				d = dict(
					lecture_id=lecture_id,
					index=index,
					parent_id=agenda_parent_id,
					title=node.title,
					type="node",
					function=[func.to_dict() for func in node.function]
				)
				agenda_id = SERVICE._agenda_collection.insert_one(d).inserted_id

				d_lecture = d.copy()
				del d_lecture["_id"]
				d_lecture["preclass_agenda_id"] = agenda_id
				d_lecture["parent_id"] = lecture_agenda_parent_id
				lecture_agenda_id = SERVICE._lecture_agenda_collection.insert_one(d_lecture).inserted_id

				index = 0
				for child in node.children:
					push(child, lecture_agenda_id, agenda_id, index)
					index += 1
		
		push(scripts)

		parent_connection, parent_channel = get_channel(parent_service)
		parent_channel.basic_publish(
				exchange="",
				routing_key=parent_service,
				body=str(parent_job_id)
			)
		parent_connection.close()
		SERVICE._logger.info(f"AskQuestion Generation Complete For {lecture_id}")
		ch.basic_ack(delivery_tag = method.delivery_tag)
			
		

	@staticmethod
	def launch_worker():
		"""
		Launches the worker process to consume and process jobs from the RabbitMQ queue.
		
		The worker runs continuously until interrupted with CTRL+C.
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
	SERVICE._logger.warning("STARTING PRECLASS-GEN_ASKQUESTION SERVICE")
	SERVICE.launch_worker()