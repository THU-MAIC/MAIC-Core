class MockLLMService:
    @classmethod
    def trigger(cls, *args, **kwargs):
        print('mock check_llm_job_done' + '=' * 20)
        return 123456

    @classmethod
    def check_llm_job_done(cls, *args, **kwargs):
        print('mock check_llm_job_done' + '=' * 20)
        return True

    @classmethod
    def get_llm_job_response(cls, *args, **kwargs):
        print('mock get_llm_job_reponse' + '=' * 20)
        return 'mock response'

