from service import get_services

if __name__=="__main__":
	pptx_file = "../Towards_AGI-Sec5-AI-Enhanced-Domains.pptx"

	get_services()["preclass_main"].trigger(
		parent_service="test",
		source_file=pptx_file
		)