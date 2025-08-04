from typing import List
from utils import preclass_context_size as context_size

class AgendaStruct:
	"""A tree structure representing an agenda or outline with hierarchical nodes.
	
	Attributes:
		title (str): The title/heading of this agenda item
		children (list): List of child AgendaStruct or PPTPageStruct objects
	"""

	type = "node"

	def __init__(self, title, children=None, function=None) -> None:
		self.title = title
		self.children = children if children is not None else []
		self.function = function if function is not None else []

	def formalize(self):
		"""
		Return a string representation of the title/heading of this agenda item
		"""
		return self.title
	
	def get_structure_trace(self):
		"""Generate a formatted string representation of the structure's hierarchy.
		
		Returns:
			str: Indented string showing the structure trace
		"""
		current_stack = ["- " + self.title.lstrip("- ")]
		complete_stack = [
			("[The current page is not under this subsection] " if type(node)!=PPTPageStruct else "") + \
			node.formalize().lstrip("- ") \
			for node in self.children[-context_size:-1]]
		complete_stack = ["- " + trace for trace in complete_stack]
		in_process_trace = [node.get_structure_trace() for node in self.children[-1:]]
		stack="\n".join(current_stack+complete_stack+in_process_trace).replace("\n", "\n\t")
		return stack
	
	def __str__(self):
		stack = "\n".join(
			["- " + self.title.lstrip("- ")]
			+ ["- " + node.formalize().lstrip("- ") for node in self.children[-3:-1]]
			+ [str(node) for node in self.children[-1:]]
		).replace("\n", "\n\t")
		return stack

	def serialize(self):
		stack = "\n".join(
			["- " + self.title.lstrip("- ")]
			+ ["\t" + str(func) for func in self.function]
			+ [node.serialize() for node in self.children]
		).replace("\n", "\n\t")
		return stack

	def insert_page(self, page, trace) -> bool:
		"""Insert a page into the agenda structure following the given trace path.
		
		Args:
			page: The page object to insert
			trace (list): List of section titles forming path to insertion point
			
		Returns:
			bool: True if page was inserted successfully, False otherwise
		"""
		assert trace.pop(0) == self.title
		if len(trace) == 1:
			self.children.append(page)
			return True

		# Gather Sub-Section Title
		direct_children_title = trace[0]

		# Find Current Sub-Section To Insert
		if len(self.children):
			if self.children[-1].formalize()[2:]==direct_children_title and type(self.children[-1]) == PPTPageStruct:
				return False
			if self.children[-1].formalize() == direct_children_title:
				self.children[-1].insert_page(page, trace)
				return True

		# Create New Sub-Section When None Is Avaliable
		self.children.append(AgendaStruct(direct_children_title))
		self.children[-1].insert_page(page, trace)
		return True

	def dfs_recursive_call(self, function):
		"""
		Recursively call the given function on each node in the agenda structure.
		
		Args:
			function: The function to be called on each node
		"""
		function(self)
		for child in self.children:
			child.dfs_recursive_call(function)
	
	def flatten(self):
		"""
		Return a flattened list of all nodes in the agenda structure.
		
		Returns:
			list: List of all nodes in the agenda structure
		"""
		self.children = sum([child.flatten() for child in self.children], [])
		return self.children
	
	def to_dict(self):
		"""
		Return a dictionary representation of the agenda structure.
		
		Returns:
			dict: Dictionary representation of the agenda structure
		"""
		return dict(
			type=self.type,
			title=self.title,
			children=[child.to_dict() for child in self.children],
			function=[func.to_dict() for func in self.function]
		)
	
	@classmethod
	def from_dict(cls, dict):
		"""
		Create an agenda structure from a dictionary representation.
		
		Args:
			dict: Dictionary representation of the agenda structure
		
		Returns:
			AgendaStruct: The agenda structure object
		"""
		if dict["type"] == "node":
			return cls(
				dict["title"], 
				[AgendaStruct.from_dict(child) for child in dict["children"]], 
				[FunctionBase.from_dict(func) for func in dict["function"]]
			)
		else:
			return PPTPageStruct(
				dict["content"],
				dict["stringified"], 
				[FunctionBase.from_dict(func) for func in dict["function"]]
			)


class PPTPageStruct:
	"""Represents a PowerPoint page/slide in the agenda structure.
	
	Attributes:
		content: The actual page/slide content
		stringified (str): String representation of the page
	"""

	type = "ppt"

	def __init__(self, page, stringified, function=None) -> None:
		self.content = page
		self.stringified = stringified
		self.function = function if function is not None else []

	def formalize(self):
		return self.stringified

	def get_structure_trace(self):
		return str(self)
	
	def __str__(self):
		return self.formalize()

	def serialize(self):
		return (
			self.formalize()
			+ "\n"
			+ "\n".join(["\t" + str(func) for func in self.function])
		)

	def dfs_recursive_call(self, function):
		function(self)
	
	def flatten(self, condition=None):
		return [self]
	
	def to_dict(self):
		return dict(
			type=self.type,
			content=self.content,
			stringified=self.stringified,
			function=[func.to_dict() for func in self.function]
		)
	
	@classmethod
	def from_dict(cls, dict):
		return cls(dict["content"], dict["stringified"], [FunctionBase.from_dict(func) for func in dict["function"]])


class FunctionBase:
	"""Base class for defining interactive functions/actions within the agenda.
	
	Attributes:
		call (str): Function identifier/name
		label (str): Display label for the function
		value (dict): Parameters/values for the function
	"""

	def __init__(self, call: str, label: str, value: dict):
		self.call = call
		self.label = label
		self.value = value

	def __call__(self):
		raise Exception(
			"Never Directly Call FunctionBase Class. You Should Inherit From This Class",
		)

	def to_dict(self):
		return dict(call=self.call, label=self.label, value=self.value)

	@classmethod
	def from_dict(cls, dict):
		return cls(dict["call"], dict["label"], dict["value"])


class ShowFile(FunctionBase):
	"""Function to display a file.
	
	Args:
		file_id: Identifier for the file to be shown
	"""

	def __init__(self, file_id):
		super().__init__("ShowFile", "展示文件", dict(file_id=file_id))

	def __str__(self):
		return f"Function: {self.call}(file_id={self.value['file_id']})"


class ReadScript(FunctionBase):
	"""Function to read a script/text.
	
	Args:
		script (str): The script content to be read
	"""

	def __init__(self, script):
		super().__init__("ReadScript", "读讲稿", dict(script=script))

	def __str__(self):
		return f"Function: {self.call}(script={self.value['script']})"

class AskQuestion(FunctionBase):
	"""Function to present a question to users.
	
	Args:
		question (str): The question text
		question_type: Type/category of question
		selects: Available answer options
		answer: Correct answer
		reference: Reference material (commented out)
	"""

	def __init__(self, question, question_type, selects, answer, reference):
		super().__init__("AskQuestion", "提出问题", dict(
			question=question,
			question_type=question_type,
			selects=selects,
			answer=answer,
			# reference=reference,
			# recent_scripts=recent_scripts
			))

	def __str__(self):
		value_str = ",".join([k+"="+str(v) for k,v in self.value.items()])
		return f"Function: {self.call}({value_str})"