from datetime import datetime

import pymongo
from bson import ObjectId

import data.session as session_db
import data.function_session as function_session_db
import data.agent as agent_db
import data.chat_action_flow as chat_action_flow_db
import data.course as course_db
import data.module as module_db
import data.agenda as agenda_db
import data.lecture as lecture_db

from service.llm.zhipuai import ZHIPUAI_SERVICE
from service.inclass.functions import get_function
import service.inclass.functions.enums as enums


class AgentType:
    TEACHER = '6'
    SCRIPT = '9'


class ClassroomSession:
    """
    A class representing a classroom session.
    """
    def __init__(self, session_id: str):
        """
        Initializes a new ClassroomSession object.

        Args:
            session_id (str): The unique identifier for the session.

        Returns:
            None
        """
        self.session_id = ObjectId(session_id)

        info = self.session_info()
        self.session = info
        self.user_id = info['user_id']
        self.lecture_id = info['lecture_id']
        self.agenda = None

        self.step_id = 0
        self.set_step_id()


    def session_info(self):
        """
        Retrieves session information from the database.

        Returns:
            dict: A dictionary containing session information.
        """
        info = session_db.client.find_one(dict(_id=self.session_id))
        return info


    def clear_session(self):
        """
        Clears the session data from the chat action flow and function session databases.

        Returns:
            None
        """
        print("Clearing Session!!!")
        chat_action_flow_db.client.delete_many(dict(session_id=self.session_id))
        function_session_db.client.delete_many(dict(session_id=self.session_id))


    def get_action_history(self, max_return=12, action_type=enums.MAICChatActionDict.SPEAK.value):
        """
        Retrieves the action history for the session.

        Args:
            max_return (int): Maximum number of messages to return (default is 12).
            action_type (str): The action type to filter the messages by (default is 'speak').

        Returns:
            list: A list of message actions from the chat action flow.
        """
        history_start = self.session.get('history_start', '')
        query = dict(
            session_id=self.session_id,
            action=action_type,
        )
        if history_start:
            query['_id'] = {'$gt': ObjectId(history_start)}

        message_list = list(chat_action_flow_db.client.find(
            query,
            sort=[('action_time', pymongo.DESCENDING)],
            limit=max_return,
        ))
        return message_list[::-1]


    def get_user_input_status(self):
        """
        Retrieves the current status of user input (enabled, disabled, or forced).

        Returns:
            str: The current user input status ('enabled', 'disabled', or 'forced').
        """
        status_action = chat_action_flow_db.client.find_one(
            dict(
                session_id=self.session_id,
                action='allowInput'
            ),
            sort=[('action_time', pymongo.DESCENDING)],
        )
        if not status_action:
            return 'disabled'
        return status_action['privilage']


    def disable_user_input(self, function_id: str):
        """
        Disables user input for the current session.

        Args:
            function_id (str): The function ID associated with disabling input.

        Returns:
            None
        """
        if self.get_user_input_status() == 'disabled':
            return
        chat_action_flow_db.create(
            action='allowInput',
            actor='system',
            session_id=self.session_id,
            step_id=self.step_id,
            privilage='disabled',
            function_id=function_id,
            action_time=datetime.now(),
        )


    def reset_displayed_file(self, value, function_id: str):
        """
        Resets the displayed file content in the session.

        Args:
            value (str): The content to display.
            function_id (str): The function ID for the action.

        Returns:
            None
        """
        chat_action_flow_db.create(
            action='showFile',
            actor='system',
            session_id=self.session_id,
            step_id=self.step_id,
            content=value,
            function_id=function_id,
            action_time=datetime.now(),
        )


    def to_next_function(self):
        """
        Marks the current function as done and proceeds to the next function in the session.

        Returns:
            None
        """
        function_session_db.client.update_one(
            dict(_id=self._get_current_function()['_id']),
            {'$set': {'is_done': True}},
        )


    def get_agent_by_id(self, agent_id: str):
        """
        Retrieves an agent by its ID.

        Args:
            agent_id (str): The agent ID to search for.

        Returns:
            dict: A dictionary containing agent information.
        """
        return agent_db.client.find_one(dict(_id=ObjectId(agent_id)))


    def get_agent_list(self):
        """
        Retrieves a list of agents associated with the session.

        Returns:
            list: A list of agent IDs.
        """
        action_flow = chat_action_flow_db.client.find_one(
            dict(session_id=self.session_id, action='updateAgentList'),
            sort=[('action_time', pymongo.DESCENDING)]
        )
        if action_flow is not None:
            agent_list = action_flow.get('agent_list')
            if agent_list:
                return agent_list

        agent_list = session_db.client.find_one(dict(_id=ObjectId(self.session_id)))['agent']

        if not agent_list:
            agent_list = lecture_db.client.info.find_one(dict(_id=ObjectId(self.lecture_id)))['agent']

        # ClassroomSession.apply_agent
        final_agent_list = []
        for agent_id in agent_list:
            agent = self.get_agent_by_id(agent_id)
            if agent['agent_type'] != enums.IdentityDict.SCRIPT_AGENT.value:
                final_agent_list.append(agent_id)
        return final_agent_list


    def get_teacher_agent_id(self):
        """
        Retrieves the agent ID of the teacher for the session.

        Returns:
            str: The agent ID of the teacher.

        Raises:
            Exception: If the teacher agent is not found.
        """
        for agent_id in self.get_agent_list():
            agent = self.get_agent_by_id(agent_id)
            if agent is not None and agent['agent_type'] == AgentType.TEACHER:
                return agent_id
        else:
            raise Exception('Teacher agent not found')


    def set_step_id(self):
        """
        Sets the step ID for the current session based on the latest action.

        Returns:
            None
        """
        slic = chat_action_flow_db.client.find_one(
            dict(session_id=self.session_id),
            sort=[('action_time', pymongo.DESCENDING)]
        )
        self.step_id = slic['step_id'] + 1 if slic and 'step_id' in slic else 0


    def send_script_to_message(self, function_id: str, value: dict, speaker_id: str):
        """
        Sends a script message to the chat action flow.

        Args:
            function_id (str): The function ID associated with the script.
            value (dict): The script content.
            speaker_id (str): The speaker's agent ID.

        Returns:
            None
        """
        content = dict(
            type=enums.ContentTypeDict.TEXT.value,
            value=value.get('script', ''),
            pure_text=value.get('pure_text', ''),
            render=enums.ContentRenderDict.MARKDOWN.value,
        )
        flow_id = chat_action_flow_db.create(
            action='speak',
            actor=speaker_id,
            session_id=self.session_id,
            step_id=self.step_id,
            content=content,
            type='raw',
            function_id=function_id,
            action_time=datetime.now(),
        )


    def send_markdown_message(self, function_id: str, message: str, speaker_id: str):
        """
        Sends a markdown formatted message to the chat action flow.

        Args:
            function_id (str): The function ID associated with the message.
            message (str): The markdown formatted message.
            speaker_id (str): The speaker's agent ID.

        Returns:
            None
        """
        content = dict(
            type=enums.ContentTypeDict.TEXT.value,
            value=message,
            render=enums.ContentRenderDict.MARKDOWN.value,
        )

        flow = dict(
            action='speak',
            actor=speaker_id,
            session_id=self.session_id,
            step_id=self.step_id,
            content=content,
            type='md',
            function_id=function_id,
            action_time=datetime.now(),
        )
        chat_action_flow_db.create(**flow)
        

    def send_question_to_message(self, function_id: str, content: dict, speaker_id: str):
        """
        Sends a question message to the chat action flow.

        Args:
            function_id (str): The function ID associated with the question.
            content (dict): The question content.
            speaker_id (str): The speaker's agent ID.

        Returns:
            None
        """
        content = dict(
            type=enums.ContentTypeDict.OBJECT.value,
            pure_text=content.pop('pure_text'),
            value=dict(question=content),
            render=enums.ContentRenderDict.HTML.value,
        )
        chat_action_flow_id = chat_action_flow_db.create(
            action=enums.MAICChatActionDict.QUESTION.value,
            actor=speaker_id,
            content=content,
            type='raw',
            function_id=function_id,
            action_time=datetime.now(),
            session_id=self.session_id,
            step_id=self.step_id,
        )


    def send_answer_to_message(self, function_id: str, content: dict, speaker_id: str):
        """
        Sends an answer message to the chat action flow.

        Args:
            function_id (str): The function ID associated with the answer.
            content (dict): The answer content.
            speaker_id (str): The speaker's agent ID.

        Returns:
            None
        """
        message_content = dict(
            type=enums.ContentTypeDict.OBJECT.value,
            value=dict(answer=content.get('answer', ''), analysis=content.get('analysis', '')),
            render=enums.ContentRenderDict.HTML.value,
        )
        flow_id = chat_action_flow_db.create(
            action=enums.MAICChatActionDict.ANSWER.value,
            actor=speaker_id,
            content=message_content,
            type='raw',
            function_id=function_id,
            action_time=datetime.now(),
            session_id=self.session_id,
            step_id=self.step_id,
        )

        question_flow = chat_action_flow_db.client.find_one(dict(
            session_id=self.session_id,
            action=enums.MAICChatActionDict.QUESTION.value,
            function_id=function_id,
        ))
        chat_action_flow_id = question_flow.get('id')


    def send_function_to_message(self, function_id: str, speaker_id: str, content: dict, action):
        """
        Sends a function-specific message to the chat action flow.

        Args:
            function_id (str): The function ID associated with the action.
            speaker_id (str): The speaker's agent ID.
            content (dict): The content for the function.
            action (str): The action type (question, answer, etc.).

        Returns:
            None
        """
        function = function_session_db.client.find_one(dict(_id=ObjectId(function_id)))
        function_call = function['call']
        if function_call == enums.FunctionCallDict.READSCRIPT.value:
            self.send_script_to_message(function_id, content, speaker_id)
            return
        if function_call == enums.FunctionCallDict.ASKQUESTION.value:
            if action == enums.MAICChatActionDict.QUESTION.value:
                self.send_question_to_message(function_id, content, speaker_id)
            elif action == enums.MAICChatActionDict.ANSWER.value:
                self.send_answer_to_message(function_id, content, speaker_id)
            return


    def update_function_status(self, function_id: str, status: dict):
        """
        Updates the status of a function in the session.

        Args:
            function_id (str): The function ID to update.
            status (dict): The new status to set for the function.

        Returns:
            None
        """
        function_session_db.client.update_one(
            dict(_id=ObjectId(function_id)),
            {'$set': {'status': status}},
        )
        chat_action_flow_db.create(
            actor='system',
            action='update_function_status',
            session_id=self.session_id,
            step_id=self.step_id,

            function_id=function_id,
            status=status,
            action_time=datetime.now(),
        )


    def force_user_input(self, function_id: str):
        """
        Forces the user input to be enabled for the current session.

        Args:
            function_id (str): The function ID associated with forcing input.

        Returns:
            None
        """
        if self.get_user_input_status() == 'forced':
            return
        chat_action_flow_db.create(
            action='allowInput',
            actor='system',
            session_id=self.session_id,
            step_id=self.step_id,
            privilage='forced',
            function_id=function_id,
            action_time=datetime.now(),
        )


    def enable_user_input(self, function_id: str):
        """
        Enables user input for the current session.

        Args:
            function_id (str): The function ID associated with enabling input.

        Returns:
            None
        """
        if self.get_user_input_status() == 'enabled':
            return
        chat_action_flow_db.create(
            action='allowInput',
            actor='system',
            session_id=self.session_id,
            step_id=self.step_id,
            privilage='enabled',
            function_id=function_id,
            action_time=datetime.now(),
        )


    def get_activation(self):
        """
        Retrieves the current activation state for the session.

        Returns:
            str: The activation state ('middle' by default).
        """
        return 'middle' 


    def send_streamed_model_request(
            self, function_id: str, request: dict, speaker_id: str, try_list: list):
        """
        Sends a streamed model request to the system.

        Args:
            function_id (str): The function ID associated with the request.
            request (dict): The request data to send.
            speaker_id (str): The speaker's agent ID.
            try_list (list): The list of models to attempt for streaming.

        Returns:
            None
        """
        content = dict(
            type=enums.ContentTypeDict.TEXT.value,
            value='',
            render=enums.ContentRenderDict.MARKDOWN.value,
        )
        request['stream'] = False
        job_id = self.push_llm_job_to_list(
            request,
            try_list,
        )
        chat_action_flow_db.create(
            action='speak',
            actor=speaker_id,
            session_id=self.session_id,
            step_id=self.step_id,
            content=content,
            streaming_id=job_id,
            type='raw',
            function_id=function_id,
            action_time=datetime.now(),
        )


    def _get_current_function(self):
        """
        Retrieves the current function that the session is processing.

        Returns:
            dict: The current function's details.
        """
        return function_session_db.client.find_one(
            dict(
                user_id=self.user_id,
                is_done=False,
                session_id=self.session_id,
            ),
            sort=[('function_idx', pymongo.ASCENDING)]  # ascending
        )


    def get_current_function(self):
        """
        Retrieves the current function for the session.

        Returns:
            dict: The current function's details.
        """
        function_session = self._get_current_function()
        if not function_session:
            self.load_next_agenda()
            function_session = self._get_current_function()
            self.agenda = None
        if function_session is not None:
            agenda_id = function_session.get('agenda_id')
            self.agenda = agenda_db.client.find_one(dict(_id=ObjectId(agenda_id)))
        return function_session


    def _get_last_function_in_list(self):
        """
        Retrieves the last function in the session's function list.

        Returns:
            dict: The last function's details.
        """
        return function_session_db.client.find_one(
            dict(
                user_id=self.user_id,
                session_id=self.session_id,
            ),
            sort=[('function_idx', pymongo.DESCENDING)]  # descending
        )


    def get_all_agenda_of_section_by_lecture(self, lecture_id, parent_agenda_id):
        """
        Retrieves all agenda items of a section by lecture using DFS.

        Args:
            lecture_id (str): The lecture ID to search for.
            parent_agenda_id (str): The parent agenda ID to search for.

        Returns:
            list: A list of agenda items.
        """
        children_agenda_list = agenda_db.client.find(
            dict(
                lecture_id=lecture_id,
                parent_id=parent_agenda_id,
            ),
            sort=[('index', pymongo.ASCENDING)]
        )
        extended_agendas = []
        for children_agenda in children_agenda_list:
            if children_agenda.get('type') == 'ppt': # ppt is a leaf node
                extended_agendas.append(children_agenda)
            else:
                extended_agendas.extend(self.get_all_agenda_of_section_by_lecture(
                    lecture_id, children_agenda.get('_id')
                ))
        return extended_agendas


    def _get_next_agenda_by_lecture(self):
        """
        Retrieves the next agenda item based on the current session progress.

        Returns:
            dict: The next agenda item, or None if no more agendas are available.
        """
        last_function = self._get_last_function_in_list()
        current_agenda_id = last_function['agenda_id'] if last_function else None

        lecture = lecture_db.client.info.find_one(dict(_id=ObjectId(self.lecture_id)))
        if not lecture:
            lecture = {}
        self.parent_lecture_id = lecture.get('parent_id', None)
        sorted_list = lecture.get('sorted_list', [])     
        
        if not sorted_list:
            sorted_agenda_list = []
            agenda_list = agenda_db.client.find(
                dict(lecture_id=self.lecture_id, parent_id=self.parent_lecture_id),
                sort=[("index", 1)],
            )
            for agenda in agenda_list:
                if agenda.get('type') == 'ppt':
                    sorted_agenda_list.append(agenda)
                else:
                    sorted_agenda_list.extend(self.get_all_agenda_of_section_by_lecture(self.lecture_id, agenda.get('_id')))
            sorted_list = [agenda.get('_id') for agenda in sorted_agenda_list]
            lecture_db.client.info.update_one(
                dict(_id=ObjectId(self.lecture_id)),
                {'$set': {'sorted_list': sorted_list}},
            )
        if current_agenda_id is None or current_agenda_id not in sorted_list:
            next_agenda_id = sorted_list[0]
        else:
            agenda_index = sorted_list.index(current_agenda_id)
            if agenda_index == len(sorted_list) - 1:
                next_agenda_id = None
            else:
                next_agenda_id = sorted_list[agenda_index + 1]

        if not next_agenda_id:
            return None
        
        return agenda_db.client.find_one(dict(_id=ObjectId(next_agenda_id)))


    def load_next_agenda(self): 
        """
        Loads the next agenda item for the session.

        Returns:
            None
        """
        next_agenda = self._get_next_agenda_by_lecture()
        if next_agenda is None:
            return  # the chapter is done
        last_function = self._get_last_function_in_list()
        function_idx = last_function['function_idx'] if last_function else -1

        for function in next_agenda['function']:
            function_idx += 1
            print('load_next_agenda', function_idx, next_agenda['_id'], function['call'], function['value'])
            function_session_db.client.insert_one(
                dict(
                    user_id=self.user_id,
                    agenda_id=next_agenda['_id'],
                    session_id=self.session_id,
                    function_idx=function_idx,
                    call=function['call'],
                    value=function['value'],
                    status=get_function(function['call']).init_status,
                    is_done=False,
                )
            )
            
            
    def push_llm_job_to_list(self, request: dict, try_list=None):
        """
        Pushes an LLM job to the job list for execution.

        Args:
            request (dict): The request data for the LLM job.
            try_list (list): The list of models to try (default is ['glm-4']).

        Returns:
            str: The job ID for the submitted LLM job.
        """
        if try_list is None:
            try_list = ['glm-4']
        job_id = ZHIPUAI_SERVICE.trigger(
            query=request,
            caller_service='inclass',
            use_cache=False,
        )
        return job_id


    def check_llm_job_done(self, task_id):
        """
        Checks if an LLM job has completed.

        Args:
            task_id (str): The task ID for the job.

        Returns:
            bool: True if the job is done, False otherwise.
        """
        return ZHIPUAI_SERVICE.check_llm_job_done(task_id)


    def get_llm_job_response(self, task_id) -> str | None:
        """
        Retrieves the response from a completed LLM job.

        Args:
            task_id (str): The task ID for the job.

        Returns:
            str | None: The job's response, or None if the job is not completed.
        """
        return ZHIPUAI_SERVICE.get_llm_job_response(task_id)


    def get_history(self, action_type='speak', max_return=12) -> list:
        """
        Retrieves the chat history for the session.

        Args:
            action_type (str): The action type to filter the messages by (default is 'speak').
            max_return (int): The maximum number of messages to return (default is 12).

        Returns:
            list: A list of messages based on the action type.
        """
        query = dict(
            session_id=self.session_id,
            action=action_type,
        )
        history_start = self.session.get('history_start')
        if history_start:
            query['_id'] = {'$gt': ObjectId(history_start)}

        message_list = list(chat_action_flow_db.client.find(
            query,
            sort=[('action_time', pymongo.DESCENDING)],
            limit=max_return
        ))
        message_list.reverse()
        history = []

        # ClassroomSession.format_chat_action
        for action in message_list:
            action_type = action['action']
            if action_type not in (
                enums.MAICChatActionDict.SPEAK,
                enums.MAICChatActionDict.QUESTION,
                enums.MAICChatActionDict.USER_ANSWER,
            ):
                continue
            if action_type == enums.MAICChatActionDict.QUESTION.value:
                action['content']['value'] = action['content']['pure_text']
            elif action_type == enums.MAICChatActionDict.USER_ANSWER.value:
                if action['content']['type'] == 'list':
                    action['content']['pure_text'] = '我的回答是' + ''.join(sorted(action['content']['value'])) # "My answer is: "
                    action['content']['value'] = action['content']['pure_text']
            history.append(action)

        return history


    def is_streaming(self):
        """
        Checks if the session is currently streaming a response.

        Returns:
            bool: True if the session is streaming, False otherwise.
        """
        latest_history = self.get_history(max_return=1)
        if not latest_history:
            return False
        latest_history = latest_history[-1]

        if 'streaming_id' not in latest_history:
            return False
        streaming_id = latest_history['streaming_id']
        if not self.check_llm_job_done(streaming_id):
            return True

        content = ZHIPUAI_SERVICE.get_llm_job_response(streaming_id)
        # ClassroomSession.fill_streamed_content_to_latest_history
        content = dict(
            type=enums.ContentTypeDict.TEXT.value,
            value=content,
            render=enums.ContentRenderDict.MARKDOWN.value,
        )
        chat_action_flow_db.client.update_one(
            dict(_id=ObjectId(latest_history['_id'])),
            {'$set': {'content': content, 'streaming_done': True}}
        )
        return False


    def add_user_message(self, content: str, user_action: str = 'chat'):
        """
        Adds a user message to the session's chat history.

        Args:
            content (dict): The content of the user's message.
            user_action (str): The user's action (optional).

        Returns:
            None
        """
        function_session = self.get_current_function()
        function_id = str(function_session['_id'])
        function_call = function_session.get('call')

        # Answer question
        if function_call == enums.FunctionCallDict.ASKQUESTION.value \
                and user_action == 'answer':
            flow_id = chat_action_flow_db.create(
                action=enums.MAICChatActionDict.USER_ANSWER.value,
                actor='user',
                session_id=self.session_id,
                step_id=self.step_id,
                content=content,
                type='raw',
                function_id=function_id,
                action_time=datetime.now(),
            )

            question_flow = chat_action_flow_db.client.find_one(dict(
                session_id=self.session_id,
                action=enums.MAICChatActionDict.QUESTION.value,
                function_id=function_id,
            ))
            question_flow_id = question_flow['_id']
            return flow_id
        return chat_action_flow_db.create(
            action='speak',
            actor='user',
            session_id=self.session_id,
            step_id=self.step_id,
            content=content,
            type='raw',
            function_id=function_id,
            action_time=datetime.now(),
        )


    def copy_current_session(self) -> str:
        new_session_id = ObjectId()

        current_session = session_db.client.find_one(dict(_id=self.session_id))

        info = function_session_db.client.find(dict(session_id=self.session_id))
        for i in info:
            i['_id'] = ObjectId()
            i['session_id'] = new_session_id
            function_session_db.client.insert_one(i)

        info = chat_action_flow_db.client.find(dict(session_id=self.session_id))
        for i in info:
            i['_id'] = ObjectId()
            i['session_id'] = new_session_id
            chat_action_flow_db.client.insert_one(i)

        current_session['_id'] = new_session_id
        session_db.client.insert_one(current_session)
        return str(new_session_id)
