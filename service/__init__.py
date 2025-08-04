def get_services():
	from service.llm.openai import OPENAI_SERVICE as OPENAI
	from service.llm.zhipuai import ZHIPUAI_SERVICE as ZHIPUAI
	from service.preclass.main import PRECLASS_MAIN
	from service.preclass.processors.pptx2pdf import SERVICE as PRECLASS_PPTX2PDF
	from service.preclass.processors.pdf2png import SERVICE as PRECLASS_PDF2PNG
	from service.preclass.processors.ppt2text import SERVICE as PRECLASS_PPT2TEXT
	from service.preclass.processors.gen_description import SERVICE as PRECLASS_GEN_DESCRIPTION
	from service.preclass.processors.gen_structure import SERVICE as PRECLASS_GEN_STRUCTURE
	from service.preclass.processors.gen_showfile import SERVICE as PRECLASS_GEN_SHOWFILE
	from service.preclass.processors.gen_readscript import SERVICE as PRECLASS_GEN_READSCRIPT
	from service.preclass.processors.gen_askquestion import SERVICE as PRECLASS_GEN_ASKQUESTION
	
	SERVICE_LIST = dict(
		# LLM API Service
		openai=OPENAI,
		zhipuai=ZHIPUAI,
		# PreClass Service
		preclass_main = PRECLASS_MAIN,
		preclass_pptx2pdf = PRECLASS_PPTX2PDF,
		preclass_pdf2png = PRECLASS_PDF2PNG,
		preclass_ppt2text = PRECLASS_PPT2TEXT,
		preclass_gen_description=PRECLASS_GEN_DESCRIPTION,
		preclass_gen_structure = PRECLASS_GEN_STRUCTURE,
		preclass_gen_showfile = PRECLASS_GEN_SHOWFILE,
		preclass_gen_readscript = PRECLASS_GEN_READSCRIPT,
		preclass_gen_askquestion = PRECLASS_GEN_ASKQUESTION
	)

	return SERVICE_LIST