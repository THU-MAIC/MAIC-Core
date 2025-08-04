# Slide2Lecture
This repository contains the major elements in the paper of `slide2lecture`. We will provide the detailed documentations once the paper is publically released. 

## Env

```bash
pip install PyMuPDF python-pptx retry
docker build -t preclass-converter --network=host service/preclass
```

## How To Run: MQ

Start all workers:
```bash
python -m service.llm.openai

python -m service.preclass.main

python -m service.preclass.processors.pptx2pdf
python -m service.preclass.processors.pdf2png
python -m service.preclass.processors.ppt2text
python -m service.preclass.processors.gen_description
python -m service.preclass.processors.gen_structure
python -m service.preclass.processors.gen_readscript
python -m service.preclass.processors.gen_showfile
python -m service.preclass.processors.gen_askquestion
```

Trigger a job in python:
```python
from service.preclass.main import SERVICE

source_file = 'xxx.pptx'
parent_service = 'xxx'

SERVICE.trigger(parent_service=parent_service, source_file=source_file)
```

Trigger a job via API:
```python
post(
    url='http://localhost:8000/preclass/trigger',
    json={
        'parent_service': 'xxx',
        'source_file': 'xxx.pptx'
    }
)
```

See more details in `api/preclass.py`

---

The final result(a list of lecture agenda) will be saved in the `preclass.agenda` collection in the mongoDB.

## Database: MQ

The service uses MongoDB as its database. Each processor retrieves its tasks in a separate collection under the `preclass` database:

- `preclass.main`: Stores the main task
- `preclass.pptx2pdf`: Stores PDF conversion tasks
- `preclass.pdf2png`: Stores PNG image tasks 
- `preclass.ppt2text`: Stores text extraction tasks
- `preclass.gen_description`: Stores slide description generation tasks
- `preclass.gen_description_result`: Stores the result of the `gen_description` tasks
- `preclass.gen_structure`: Stores lecture structurization tasks
- `preclass.gen_structure_result`: Stores the result of the `gen_structure` tasks
- `preclass.gen_readscript`: Stores reading scripts generation tasks
- `preclass.gen_showfile`: Stores show_file function generation tasks
- `preclass.gen_askquestion`: Stores Q&A generation tasks
- `preclass.agenda`: Stores the structured lecture agenda

Each task document contains:
- `lecture_id`: Unique identifier for the lecture
- `parent_service`: The service that triggers the task
- `created_time`: Timestamp of task creation
- `completion_time`: Timestamp of task completion


## How To Run: One Command

```bash
service/preclass/extraction.sh course.pptx
```

## Maintainer
Daniel Zhang-Li