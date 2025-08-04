# from data.models.function_session import FunctionSession
# from llm.classroom.function import Function
from .base_class import Function
# from llm.classroom.worker import ClassroomSession
from service.inclass.classroom_session import ClassroomSession
from bson import ObjectId
# from configuration import MAICConfig
from random import random, choice
from pprint import pprint
# from maic_enum import DictionaryEncoding, DictionaryEnum, IdentityDict
# from util import CommonUtil
from service.inclass.functions.enums import IdentityDict


class ReadScriptStatus:
    '''
    Defines the possible states of the ReadScript function.
    
    States:
        - UNREAD (0): The script has not been read yet.
        - NEED_CALL_DIRECTOR (1): The script has been read and the director needs to be called.
        - WAITING_DIRECTOR_RETURN (2): The director has been called and is waiting for the user's input.
        - WAITING_USER_INPUT (3): The user has been asked to type something and is waiting for the director's response.
        - FINISHED (4): The script has been read and the user has finished reading it.
        - CONTINUE_FINISHED (5): The user has finished reading the script and the classroom should continue.
        - TOO_MUCH_ROUND_FINISHED (6): The user has finished reading the script and the classroom should continue, but the user has been too slow.
        - FORCE_AGENT_TO_HEATUP_TALK (9): The user has been asked to type something and the frontend send a signal to continue classroom. The user's input is already in the history if the user did type something.
    '''
    UNREAD = 0
    NEED_CALL_DIRECTOR = 1
    WAITING_DIRECTOR_RETURN = 2
    WAITING_USER_INPUT = 3
    FINISHED = 4
    CONTINUE_FINISHED = 5
    TOO_MUCH_ROUND_FINISHED = 6
    FORCE_AGENT_TO_HEATUP_TALK = 9  # disabled


class ReadScriptDirectorConst:
    '''
    Defines the constants used in the ReadScript function.
    
    Constants:
        - USER_NAME (str): The name of the user, "真人学生" (Real Student).
        - TEACHER_NAME (str): The name of the teacher, "老师" (Teacher).
        - END_SEQUENCE_NAME (str): The name of the end sequence, "上课" (Continue class).
    '''
    USER_NAME = "真人学生"
    TEACHER_NAME = "老师"
    END_SEQUENCE_NAME = "上课"



class ReadScript(Function):
    init_status = {
        "phase": ReadScriptStatus.UNREAD,
        "llm_job_id": None,
        "agent_talked": False,
    }

    @staticmethod
    def map_activation(activation: str) -> float:
        """
        Maps the given activation level to a corresponding numerical value.

        Args:
            activation (str): The activation level, which can be "low", "middle", or "high".

        Returns:
            float: The mapped numerical value for the activation level. Return 0.05 for "low", 0.1 for "middle", and 0.2 for "high". Returns -1 if the activation level is invalid.
        """
        if activation == "low":
            return 0.05
        elif activation == "middle":
            return 0.1
        elif activation == "high":
            return 0.2
        return -1

    @staticmethod
    def step(
        value: dict,
        function_id: str,
        classroom_session: ClassroomSession,
    ):
        """
        Handles the state transitions and logic for the ReadScript function based on the current status.
        
        Phases:
            - UNREAD: Script Not Read Yet. Disables user input, sends script to message, and waits for user to read and type response.
            - NEED_CALL_DIRECTOR: Time to call the director. Update the chat history and send to the director, and wait for the director's response.
            - WAITING_USER_INPUT: User was asked to type something and the frontend send a signal to continue classroom. User's input is already in the history if the user did type something.
            - FORCE_AGENT_TO_HEATUP_TALK: Select the "显眼包" agent to say something to heat-up the discussion.
            - WAITING_DIRECTOR_RETURN: Check whether the director is returned and jummp to the next status accordingly (selected_speaker: user or teacher or a specific agent).

        Args:
            value (dict): The input values related to the function.
            function_id (str): The unique identifier for the function instance.
            classroom_session (ClassroomSession): The classroom session object managing the function's state.

        Returns:
            bool: Whether the function should continue execution.
        """
        function_status = classroom_session.get_current_function()["status"]
        # from pprint import pprint
        # print('\ncurrent_function in readScript:')
        # pprint(classroom_session.get_current_function())
        classroom_session.set_step_id()
        if function_status["phase"] == ReadScriptStatus.UNREAD:  # Script Not Read Yet
            classroom_session.disable_user_input(function_id=function_id)
            teacher_id = classroom_session.get_teacher_agent_id()
            classroom_session.send_script_to_message(function_id, value, teacher_id)
            function_status["phase"] = ReadScriptStatus.WAITING_USER_INPUT
            classroom_session.update_function_status(
                function_id=function_id, status=function_status
            )
            classroom_session.enable_user_input(function_id=function_id)
            return False
        elif (
            function_status["phase"] == ReadScriptStatus.NEED_CALL_DIRECTOR
        ):  # Time to call the director
            classroom_session.disable_user_input(function_id=function_id)
            agent_list = classroom_session.get_agent_list()
            history = classroom_session.get_history(max_return=12)

            if history[0]["function_id"] == function_id and len(history) >= 12:
                function_status["phase"] = ReadScriptStatus.TOO_MUCH_ROUND_FINISHED
                classroom_session.update_function_status(function_id, function_status)
                classroom_session.to_next_function()
                return True

            agent_list += ["user"]

            if history:
                last_spoken_character = history[-1]["actor"]
                if last_spoken_character in agent_list:
                    agent_list.remove(last_spoken_character)
            # print("Available Agents", agent_list)
            # Trigger Director Call
            call_director_job = ReadScript.async_call_director(
                classroom_session=classroom_session,
                history=history,
                agent_list=agent_list,
            )
            function_status["phase"] = ReadScriptStatus.WAITING_DIRECTOR_RETURN
            function_status["llm_job_id"] = call_director_job
            classroom_session.update_function_status(function_id, function_status)
            return True
        elif (
            function_status["phase"] == ReadScriptStatus.WAITING_USER_INPUT
        ):  # User was asked to type something and the frontend send a signal to continue classroom. User's input is already in the history if the user did type something
            classroom_session.disable_user_input(function_id=function_id)
            history_list = classroom_session.get_history(max_return=1)
            history = history_list[-1] if history_list else None
            if history is not None and history["actor"] != "user":  # if continuous mode
                history = classroom_session.get_history(max_return=2)
                no_one_spoken = (
                    len(history) == 1 or history[0]["function_id"] != function_id
                )  # whether no one has spoken yet
                if no_one_spoken and (
                    random()
                    < ReadScript.map_activation(classroom_session.get_activation())
                ):  # Force 学生Agent
                    function_status["llm_job_id"] = None
                    classroom_session.disable_user_input(function_id=function_id)
                    function_status["phase"] = (
                        ReadScriptStatus.FORCE_AGENT_TO_HEATUP_TALK
                    )
                    classroom_session.update_function_status(
                        function_id, function_status
                    )
                    return True
                else:
                    function_status["phase"] = ReadScriptStatus.CONTINUE_FINISHED
                    classroom_session.update_function_status(
                        function_id, function_status
                    )
                    classroom_session.to_next_function()
                    return True

            function_status["phase"] = ReadScriptStatus.NEED_CALL_DIRECTOR
            classroom_session.update_function_status(function_id, function_status)
            return True
        elif (
            function_status["phase"] == ReadScriptStatus.FORCE_AGENT_TO_HEATUP_TALK
        ):  # Select an agent to say something to heat-up the discussion
            agent_list = classroom_session.get_agent_list()
            agent_dict = ReadScript.get_agent_id2name_dict(
                classroom_session, agent_list + ["user"]
            )
            reversed_agent_dict = {v: k for k, v in agent_dict.items()}
            if "显眼包" in reversed_agent_dict: # Class Clown
                agent_id = reversed_agent_dict["显眼包"]
                # print(agent_id)
                # Select agent some available list
                possible_agent_list = [agent_id]
                agent_id = choice(possible_agent_list)

                # Gather system prompt for the agent
                instruction = classroom_session.get_agent_by_id(agent_id)["instruction"]

                # Assemble chat history and send llm call
                history = classroom_session.get_history()
                context_ids = [str(slic["_id"]) for slic in history if slic is not None]
                agent_list_to_format_history = list(
                    set(agent_list + ["user"] + [slic["actor"] for slic in history])
                )
                agent_dict_to_format_history = ReadScript.get_agent_id2name_dict(
                    classroom_session, agent_list_to_format_history
                )
                formatted_history = (
                    "\n".join(
                        [
                            ReadScript.format_history_for_agent(
                                item, agent_dict_to_format_history
                            )
                            for item in history
                        ]
                    )
                    + "\n你的回复是：\n" # "Your reply is:"
                )
                request = dict(
                    messages=[
                        dict(role="system", content=instruction),
                        dict(role="user", content=formatted_history),
                    ]
                )
                call_agent_job = classroom_session.send_streamed_model_request(
                    function_id=function_id,
                    request=request,
                    speaker_id=agent_id,
                    try_list=["glm-4"],
                )
                function_status["phase"] = ReadScriptStatus.NEED_CALL_DIRECTOR
                function_status["agent_talked"] = True
                classroom_session.update_function_status(function_id, function_status)
                return True
            else:
                function_status["phase"] = ReadScriptStatus.CONTINUE_FINISHED
                classroom_session.update_function_status(function_id, function_status)
                classroom_session.to_next_function()
                return True
        elif (
            function_status["phase"] == ReadScriptStatus.WAITING_DIRECTOR_RETURN
        ):  # Check whether the director is returned and gather the selected agent and make it talk.
            if classroom_session.check_llm_job_done(function_status["llm_job_id"]):

                # response = classroom_session.get_llm_job_response(
                #     function_status["llm_job_id"]
                # )
                # if response.is_error():
                #     # 如果出现错误，直接结束则注释该部分即可
                #     FunctionSession.update(
                #         {"_id": CommonUtil.str_to_object_id(function_id)},
                #         {
                #             "status": dict(
                #                 phase=ReadScriptStatus.FINISHED,
                #                 llm_job_id=None,
                #                 agent_talked=False,
                #             ),
                #             "is_done": True,
                #         },
                #     )
                #     classroom_session.enable_user_input(function_id)
                #     return False
                #
                # selected_speaker = response.content()

                selected_speaker = classroom_session.get_llm_job_response(
                    function_status["llm_job_id"]
                )

                agent_list = classroom_session.get_agent_list()
                teacher_agent = classroom_session.get_teacher_agent_id()
                agent_name_list = [
                    ReadScript.get_agent_name_by_id(agent, classroom_session)
                    for agent in agent_list
                    if agent != teacher_agent
                ] + [ReadScriptDirectorConst.TEACHER_NAME]
                # print("Selected", selected_speaker)

                history = classroom_session.get_history()
                # Handle cases where user is asked to speak twice in a role
                if (
                    history
                    and selected_speaker.strip() == ReadScriptDirectorConst.USER_NAME
                    and history[-1]["actor"] == "user"
                ):
                    selected_speaker = ReadScriptDirectorConst.TEACHER_NAME

                if selected_speaker.strip() in agent_name_list:
                    agent_list = classroom_session.get_agent_list()
                    agent_list_to_format_history = list(
                        set(agent_list + ["user"] + [slic["actor"] for slic in history])
                    )
                    agent_dict = ReadScript.get_agent_id2name_dict(
                        classroom_session, agent_list_to_format_history
                    )
                    reversed_agent_dict = {v: k for k, v in agent_dict.items()}
                    agent_id = reversed_agent_dict[selected_speaker]
                    instruction = classroom_session.get_agent_by_id(agent_id)[
                        "instruction"
                    ]
                    context_ids = [str(slic["_id"]) for slic in history if slic is not None]
                    formatted_history = (
                        "\n".join(
                            [
                                ReadScript.format_history_for_agent(item, agent_dict)
                                for item in history
                            ]
                        )
                        + "\n你的回复是：\n" # "Your reply is:"
                    )
                    request = dict(
                        messages=[
                            dict(role="system", content=instruction),
                            dict(role="user", content=formatted_history),
                        ],
                    )
                    call_agent_job = classroom_session.send_streamed_model_request(
                        function_id=function_id,
                        request=request,
                        speaker_id=agent_id,
                        try_list=["glm-4"],
                    )
                    # function_status["llm_job_id"]=call_agent_job
                    function_status["phase"] = ReadScriptStatus.NEED_CALL_DIRECTOR
                    function_status["agent_talked"] = True
                    classroom_session.update_function_status(
                        function_id, function_status
                    )
                    # classroom_session.enable_user_input()
                    return True
                elif (
                    selected_speaker.strip() == ReadScriptDirectorConst.USER_NAME
                ):  # Selected user to speak
                    function_status["llm_job_id"] = None
                    function_status["phase"] = ReadScriptStatus.WAITING_USER_INPUT
                    function_status["agent_talked"] = False
                    classroom_session.update_function_status(
                        function_id, function_status
                    )
                    classroom_session.enable_user_input(function_id)
                    return False
                else:  # Error handling when the director selected someone outside of the given list
                    if function_status["agent_talked"] == True:
                        function_status["llm_job_id"] = None
                        function_status["phase"] = ReadScriptStatus.WAITING_USER_INPUT
                        function_status["agent_talked"] = False
                        classroom_session.update_function_status(
                            function_id, function_status
                        )
                        classroom_session.enable_user_input(function_id=function_id)
                        return False
                    function_status["llm_job_id"] = None
                    function_status["phase"] = ReadScriptStatus.FINISHED
                    classroom_session.update_function_status(
                        function_id, function_status
                    )
                    classroom_session.to_next_function()
                    return True

            else:
                # Waiting For Return
                return True
        return True

    @staticmethod
    def get_agent_name_by_id(agent_id, classroom_session):
        """
        Retrieves the name of an agent by its ID.

        Args:
            agent_id (str or ObjectId): The ID of the agent.
            classroom_session (ClassroomSession): The classroom session instance.

        Returns:
            str: The name of the agent.
        """
        if agent_id == "user":
            return ReadScriptDirectorConst.USER_NAME
        if type(agent_id) == str:
            agent_id = ObjectId(agent_id)
        return classroom_session.get_agent_by_id(agent_id)["name"]

    @staticmethod
    def format_history(message, agent_dict):
        """
        Formats a message from the conversation history for logging purposes.

        Args:
            message (dict): The message dictionary containing actor and content information.
            agent_dict (dict): A mapping of agent IDs to their names.

        Returns:
            str: The formatted history string with actor and content.
        """
        content = message.get("content")
        if isinstance(content, str):
            content = content
        elif isinstance(content, dict) and "value" in content.keys():
            content = content["value"]
        else:
            content = message
        return f"actor: {agent_dict[message['actor']]}, content: {content}"

    @staticmethod
    def format_history_for_agent(message, agent_dict):
        """
        Formats a message for a specific agent by embedding the actor's name in the message content.

        Args:
            message (dict): The message dictionary containing actor and content information.
            agent_dict (dict): A mapping of agent IDs to their names.

        Returns:
            str: The formatted message string for the agent.
        """
        content = message.get("content")
        if isinstance(content, str):
            content = content
        elif isinstance(content, dict) and "value" in content.keys():
            content = content["value"]
        else:
            content = message
        return f"<!-- {agent_dict[message['actor']]} -->{content}\n"

    @staticmethod
    def get_agent_id2name_dict(classroom_session: ClassroomSession, agent_list: list):
        """
        Constructs a mapping of agent IDs to their names.

        Args:
            classroom_session (ClassroomSession): The classroom session instance.
            agent_list (list): A list of agent IDs.

        Returns:
            dict: A dictionary mapping agent IDs to their corresponding names.
        """
        agent_dict = {
            str(agent_id): ReadScript.get_agent_name_by_id(agent_id, classroom_session)
            for agent_id in agent_list
        }
        agent_dict[classroom_session.get_teacher_agent_id()] = (
            ReadScriptDirectorConst.TEACHER_NAME
        )
        return agent_dict

    @staticmethod
    def get_agent_role(agent_id, classroom_session):
        """
        Retrieves the role and identity of an agent based on its ID.
        
        ROLE:
            - "user": the real human student. Role: the whole classroom's purpose is to teach the student the knowledge in the classroom.
            - "小刘老师" or "小詹老师": AI teachers. Role: responsible for teaching and answering students' questions.
            - "助教": AI teaching assistants. Role: responsible for maintaining the classroom order, when students are speaking out of topic or trying to deviate from the course's theme, the assistant will stand up to maintain the classroom's discipline.
            - "显眼包": AI students. Role: Class Clown: Crafted to spark creativity, engender a lively classroom ambiance, and act as a supportive peer, this agent also assists the teacher in steering the class’s focus when the learner’s attention wanders.
            - "好奇宝宝": AI students. Role: Inquisitive Mind: Characterized by a propensity for inquiring about lecture content, this agent fosters a culture of inquiry and dialogue, prompting others to engage in critical thinking and collaborative discourse.
            - "笔记员": AI students. Role: Note Taker: With a penchant for summarizing and disseminating key points from the class discussions, this agent aids in the cognitive organization and retention of information for all participants.
            - "思考者": AI students. Role: Deep Thinker: This agent is dedicated to profound contemplation and to posing thoughtprovoking questions that challenge and extend the intellectual boundaries of the classroom.

        Args:
            agent_id (str): The ID of the agent.
            classroom_session (ClassroomSession): The classroom session instance.

        Returns:
            dict: A dictionary containing the agent's identity and role.
        """
        if agent_id == "user":
            return dict(
                identity=IdentityDict.STUDENT.value,
                role=f"{ReadScriptDirectorConst.USER_NAME}：整个班级存在的意义就是为了能够教会真人学生学明白课堂的知识。",
            )
        agent_name = classroom_session.get_agent_by_id(agent_id)["name"]
        if agent_name == "小刘老师" or agent_name == "小詹老师": # Teaching Assistant
            return dict(
                identity=IdentityDict.AI_TEACHER.value,
                role=f"{ReadScriptDirectorConst.TEACHER_NAME}: 负责授课和回答学生们的问题。当学生提问时，老师会进行回答。",
            )
        if agent_name == "助教": # Teaching Assistant
            return dict(
                identity=IdentityDict.AI_ASSISTANT.value,
                role=f"助教: 负责维持课堂秩序，当学生刚刚发表了过激的言论，或一直在尝试偏离课程讨论的主题时，助教会站出来维持课堂的纪律。",
            )
        if agent_name == "显眼包": # Class Clown
            return dict(
                identity=IdentityDict.AI_STUDENT.value,
                role=f"显眼包: 当{ReadScriptDirectorConst.USER_NAME}很久没有说话，或者说了跟课堂不相关的话的时候，会通过插科打诨的方式强行把课程的主题和学生跑题的话结合在一起。帮助老师把课程引回正轨",
            )
        if agent_name == "好奇宝宝": # Inquisitive Mind
            return dict(
                identity=IdentityDict.AI_STUDENT.value,
                role=f"好奇宝宝: 好奇宝宝是一个非常喜欢提问的学生，会根据老师的授课内容提出有深度、启发学生思考的问题。好奇宝宝需要在老师讲解课程内容时时不时提出一些问题，但不会太过频繁，以免影响老师教学节奏。他的根本目的是帮助{ReadScriptDirectorConst.USER_NAME}学习。",
            )
        if agent_name == "笔记员": # Note Taker
            return dict(
                identity=IdentityDict.AI_STUDENT.value,
                role=f"笔记员: 笔记员是一个勤奋的记录笔记的学生。他会给出自己对前一段时间课堂内容的笔记。需要在一个授课章节结束后出现，给出自己记录的笔记共其他同学们参考。不要太过频繁，仅在大章节结束后出现。",
            )
        if agent_name == "思考者": # Deep Thinker
            return dict(
                identity=IdentityDict.AI_STUDENT.value,
                role=f"思考者: 思考者会反思老师当前的教学内容，提出反例或者质疑，他的问题常常会促进课堂进行更深入的讨论。",
            )
        print(f"llm/classroom/functions/readScript.py: {agent_name} Role Not Defined")
        return {}

    @staticmethod
    def async_call_director(
        classroom_session: ClassroomSession, history: list, agent_list: list, **kwargs
    ):
        """
        Asynchronously triggers the director logic to select the next speaker in the script.

        Args:
            classroom_session (ClassroomSession): The classroom session instance.
            history (list): The conversation history as a list of messages.
            agent_list (list): A list of agent IDs eligible for selection.
            **kwargs: Additional arguments for customization.

        Returns:
            str: The job ID for the director call.
        """
        context_ids = [str(slic.get("_id")) for slic in history if slic is not None]
        agent_list_to_format_history = list(
            set(
                classroom_session.get_agent_list()
                + ["user"]
                + [slic["actor"] for slic in history]
            )
        )
        agent_dict = ReadScript.get_agent_id2name_dict(
            classroom_session, agent_list_to_format_history
        )
        history = "\n".join(
            [ReadScript.format_history(message, agent_dict) for message in history]
        )

        agent_roles = [
            ReadScript.get_agent_role(agent_id, classroom_session)
            for agent_id in agent_list
        ]

        teacher_roles = [
            agent["role"]
            for agent in agent_roles
            if agent and agent["identity"] == IdentityDict.AI_TEACHER.value
        ]
        assistant_roles = [
            agent["role"]
            for agent in agent_roles
            if agent and agent["identity"] == IdentityDict.AI_ASSISTANT.value
        ]
        student_roles = [
            agent["role"]
            for agent in agent_roles
            if agent
            and (
                agent["identity"] == IdentityDict.STUDENT.value
                or agent["identity"] == IdentityDict.AI_STUDENT.value
            )
        ]

        teacher_roles = (
            "\n".join(teacher_roles) if teacher_roles else "教师类演员不可选" # Teacher role unavailable
        )
        assistant_roles = (
            "\n".join(assistant_roles) if assistant_roles else "助教类演员不可选" # Assistant role unavailable
        )
        student_roles = "\n".join(student_roles)
        agent_roles = f"""
### 老师
{teacher_roles}
### 助教
{assistant_roles}
### 学生
{student_roles}

### 特殊演员
{ReadScriptDirectorConst.END_SEQUENCE_NAME}: 这是一个特殊的演员，当你选择它的时候他会令ppt翻页，之后老师便会开始介绍下一页ppt的内容。
		""".strip() # 特殊演员: This is a special actor who will trigger a slide change, and then the teacher will start to introduce the content of the next slide.

        return classroom_session.push_llm_job_to_list(
            request={
                "messages": [
                    {
                        "role": "system",
                        "content": f"你是一个非常优秀的剧本大师。现在你已经确定了可能说出下一句话的候选演员，并给他们分好了他们说话的任务：\n{agent_roles}\n\n用户会告诉你每个演员在剧本里说了什么话。你的任务是在遵守每个演员任务和人设的情况下，判断该轮到哪位演员说话了。你的输出应当只包括演员的名字（例如，直接输出真人学生四个字），不应当包括任何额外的标点符号（除非演员的名字里包括符号），你更不应当解释为什么要选择这个演员。有的时候用户所提供的对话历史里会包括其他的角色，你被禁止选择这些演员，因为他们已经确定不会说话了。",
                        # You are a great script writer. Now you have selected the candidate actors who may speak the next line. You have assigned them their speaking tasks: {agent_roles}. 
                        # The users will tell you what they said to each actor in the script. Your task is to follow each actor's task and persona while deciding who speaks next. 
                        # Your output should only include the actor's name (e.g., "real human student"), and should not include any additional punctuation (unless the actor's name includes a symbol), you should not explain why you chose this actor. 
                        # Sometimes the user's conversation history may include other roles, and you are not allowed to select them, because they have already been determined not to speak.
                    },
                    {
                        "role": "user",
                        "content": f"{history}",
                    },
                ],
                "stream": False,
            },
            try_list=["glm-4"],
        )

