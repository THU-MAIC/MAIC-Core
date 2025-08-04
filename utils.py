import os
import shutil
import logging

import pika
from datetime import datetime
from colorama import Fore, Style, init

from config import LOG

preclass_context_size = 3

now = datetime.now

def get_logger(__name__, __file__):
	"""
	Creates and configures a logger with colored output for different log levels.

	This function sets up a logger that outputs log messages to the console with
	color-coded log levels to make it easier to distinguish between different
	severities. The logger's configuration includes:
	- Log levels with distinct colors (DEBUG, INFO, WARNING, ERROR, CRITICAL).
	- Relative file path display from the directory where the script is executed.
	- Automatic color reset after each log message.

	The function initializes the logger based on the module's `__name__` and `__file__`
	parameters, sets the logging level from a global `LOG.LEVEL` variable, and uses
	`colorama` for colored console output.

	Parameters:
		__name__ (str): The name of the current module, typically passed as `__name__`.
		__file__ (str): The path of the current file, typically passed as `__file__`.

	Returns:
		logging.Logger: A configured logger instance with color-coded log level output.

	Example:
		logger = get_logger(__name__, __file__)
		logger.info("This is an info message")
		logger.error("This is an error message")

	Notes:
		The logger uses a `StreamHandler` to output to the console and a custom
		`ColorFormatter` to add colors to the log level based on the severity.
		It will only add a handler if no handlers are already configured to prevent
		duplicate log entries.
	"""
	# Initialize colorama
	init(autoreset=True)

	# Configure the logger
	logger = logging.getLogger(__name__)

	# Set the logging level based on a variable LOG.LEVEL
	log_level = getattr(logging, LOG.LEVEL.upper(), logging.INFO)
	logger.setLevel(log_level)

	# Get the relative path of the current file from where the script is executed
	relative_file_path = os.path.relpath(__file__, os.getcwd())

	# Define colors for each log level
	LOG_COLORS = {
		'DEBUG': Fore.CYAN,
		'INFO': Fore.GREEN,
		'WARNING': Fore.YELLOW,
		'ERROR': Fore.RED,
		'CRITICAL': Fore.MAGENTA
	}

	# Custom formatter to add color to the log level
	class ColorFormatter(logging.Formatter):
		def format(self, record):
			log_color = LOG_COLORS.get(record.levelname, "")
			record.levelname = f"{log_color}{record.levelname}{Style.RESET_ALL}"
			return super().format(record)

	# Create a console handler (StreamHandler)
	console_handler = logging.StreamHandler()
	console_handler.setLevel(log_level)

	# Create a formatter with color support for the desired log message format
	formatter = ColorFormatter(f'%(levelname)s {relative_file_path}: %(message)s')
	console_handler.setFormatter(formatter)

	# Add the console handler to the logger
	if not logger.handlers:  # Avoid adding multiple handlers if logger is configured again
		logger.addHandler(console_handler)
	return logger

def change_file_path(input_file, new_directory, new_base_name):
	"""
	Change the input file path, keeping the original file extension unchanged and move the file.

	Parameters:
	input_file (str): The original file path with the extension.
	new_directory (str): The new directory where the file should be moved.
	new_base_name (str): The new base name for the file (without extension).

	Returns:
	str: The new file path with the original extension.
	"""
	# Extract the file extension
	_, extension = os.path.splitext(input_file)

	# Create the new directory if it doesn't exist
	if not os.path.exists(new_directory):
		os.makedirs(new_directory)

	# Create the new file path
	new_file_path = os.path.join(new_directory, new_base_name + extension)
	
	# Move the file to the new location
	shutil.move(input_file, new_file_path)
	return new_file_path

def get_channel(queue_name):
	connection = pika.BlockingConnection(
		pika.ConnectionParameters(host='localhost'))
	channel = connection.channel()

	channel.queue_declare(
		queue=queue_name,
		durable=True
	)
	return connection, channel