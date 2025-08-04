NO_CACHE_YET=None


class BASE_LLM_CACHE:
	"""
	A base class for implementing caching of queries and responses for a Language Model (LLM).
	This class is intended to be inherited and implemented by a subclass.
	"""
	def __init__(self):
		"""
		Initializes the BASE_LLM_CACHE class.
		This base class cannot be directly instantiated; it must be inherited and implemented.
		"""
		raise Exception("Inherit and implement this class.")
	
	def check_cache(self, query):
		"""
		Checks if a cached response exists for the provided query.

		Args:
			query: The query to check in the cache.

		Returns:
			The cached response if available, otherwise a constant (NO_CACHE_YET).
			Also updates the internal usage cost for cached responses.
		"""
		query_len = len(str(query))
		response = self.cache_collection.find_one(dict(request=query,query_len=query_len))
		
		if not response:
			return NO_CACHE_YET
		
		for k,v in response["usage"].items():
			if type(v) is int:
				self.cost[k] = self.cost.get(k,0)+v
			elif type(v) is dict:
				for inner_k, inner_v in v.items():
					if inner_v is int:
						self.cost[k+"."+inner_k] = self.cost.get(k+"."+inner_k,0)+inner_v
		return response["response"]
	
	def write_cache(self, query, response, usage):
		"""
		Writes the provided query, response, and usage information to the cache.

		Args:
			query: The query to be cached.
			response: The response to be cached.
			usage: The token usage information.
		"""
		query_len = len(str(query))
		content = dict(
			request=query,
			response=response,
			query_len=query_len,
			usage=usage,
		)
		self.cache_collection.update_one(
			dict(
				request=content["request"],
				query_len=query_len,
				),
			{
				"$set":content,
								"$inc": {f"cumulative_sum.{k}": v for k, v in usage.items() if type(v) in [int,float]}
			},
			upsert=True
			)
		
	def print_usage(self):
		"""
		Prints the cumulative token usage statistics.
		"""
		# Prepare the text to be displayed inside the panel
		text = ""
		for k, v in self.cost.items():
			text += f"{k}: {v}\n"

		# Create a panel with the prepared text
		print(text.strip(), title="Generation Cost (Token)")

	def clear_usage(self):
		"""
		Clears the stored usage statistics.
		"""
		self.cost = dict()
	
