def get_function(name):
	from .askQuestion import AskQuestion
	from .readScript import ReadScript
	from .showFile import ShowFile
	return dict(
		AskQuestion=AskQuestion,
		ReadScript=ReadScript,
		ShowFile=ShowFile,
	)[name]
