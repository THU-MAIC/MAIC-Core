import argparse

try:
    # Parse command-line arguments
    parser = argparse.ArgumentParser()
    parser.add_argument("--log", default="INFO", help="Set the logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)")
    parser.add_argument("--zhipu_api_key", default="xxx", help="Set ZHIPU service api_key")
    parser.add_argument("--openai_api_key", default="xxx", help="Set OPENAI service api_key")
    parser.add_argument("--openai_baseurl", default="xxx", help="Set OPENAI service baseurl")
    args = parser.parse_args()
except SystemExit:
    # If argparse fails (likely due to missing arguments during import), use default values
    args = argparse.Namespace(
        log="INFO",
        zhipu_api_key="xxx",
        openai_api_key="xxx",
        openai_baseurl="xxx"
    )


class MONGO:
    HOST = "localhost"
    PORT = 27017

class LLM:
    class ZHIPU:
        API_KEY = args.zhipu_api_key

    class OPENAI:
        API_KEY = args.openai_api_key
        BASE_URL = args.openai_baseurl

class LOG:
    LEVEL = args.log

class MONGO:
	HOST="localhost"
	PORT=27017

class LLM:
	class ZHIPUAI:
		API_KEY=args.zhipu_api_key
	
	class OPENAI:
		API_KEY=args.openai_api_key
		BASE_URL=args.openai_baseurl

class LOG:
	LEVEL=args.log