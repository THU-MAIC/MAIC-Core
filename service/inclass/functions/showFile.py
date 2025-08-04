# from llm.classroom.function import Function
from .base_class import Function
# from llm.classroom.worker import ClassroomSession
from service.inclass.classroom_session import ClassroomSession

class ShowFile(Function):
    init_status = {}

    @staticmethod
    def step(
        value: dict,
        function_id: str,
        classroom_session: ClassroomSession,
    ):
        """
        Executes the main logic for displaying a file during a classroom session.

        Args:
            value (dict): Contains the file data or parameters necessary for display.
            function_id (str): Unique identifier for the current function execution.
            classroom_session (ClassroomSession): Instance of the classroom session manager.

        Returns:
            bool: Always returns True after processing the file and moving to the next function.
        """
        print("Check if the session is showing file")
        classroom_session.set_step_id()
        classroom_session.disable_user_input(function_id=function_id)
        classroom_session.reset_displayed_file(value, function_id=function_id)
        classroom_session.to_next_function()
        return True
