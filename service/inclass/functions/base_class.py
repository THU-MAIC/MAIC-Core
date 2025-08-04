from service.inclass.classroom_session import ClassroomSession


class Function:
    '''
    This is the base class for all functions.
    '''
    init_status = {}

    @staticmethod
    def step(
            value: dict,
            function_id: str,
            classroom_session: ClassroomSession,
    ) -> bool:
        '''
        This is the main function step. The return value indicates whether it is required to force calling another function step. (No matter did we change the function or not, always get the latest function call `step()`)
        
        Args:
            value (dict): The input value for the function.
            function_id (str): The function id.
            classroom_session (ClassroomSession): The classroom session object.
        
        Returns:
            bool: Whether it is required to force calling another function step.
        '''
        pass