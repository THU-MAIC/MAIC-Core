# from llm.classroom.worker import ClassroomSession
# from llm.classroom.function import Function
from .base_class import Function
# from data.interface import DBCenter
from bson import ObjectId
from pprint import pprint
# from maic_enum import IdentityDict
# from llm.enum import MAICChatActionDict
from service.inclass.classroom_session import ClassroomSession
from .enums import MAICChatActionDict, IdentityDict


class AskQuestionStatus:
    """
	Enumeration class representing the status of asking a question.

    States:
        - `NEED_TRANSFORM_SENTENCE` (-1): Indicates that the sentence needs to be transformed.
        - `NOT_ASKED` (0): The question has not been asked yet.
        - `WAITING_STUDENT_ANSWER` (1): Waiting for an answer from the student.
        - `CHECKING_DID_STUDENT_ANSWER` (2): Checking if the student has answered. If not answered, transitions to `WAITING_STUDENT_ANSWER`. If answered, transitions to `NEED_CALL_DIRECTOR`.
        - `WAITING_USER_INPUT` (3): Waiting for input from the user after the question has been answered.
        - `NEED_CALL_DIRECTOR` (4): Indicates that it's time to call the director.
        - `WAITING_DIRECTOR_RETURN` (5): Waiting for the director's return.
        - `FINISHED` (9): Indicates the process is finished.
        - `CONTINUE_FINISHED` (10): Finished in "continue mode."
        - `DIRECTOR_NOT_FOUND_FINISHED` (20): Indicates an error where the director was not found.
        - `FORCE_CALL_TEACHER_BEFORE_RETURN` (21): Forces a call to the teacher before returning.
        - `WAIT_FINISH` (22): Waiting for the finish signal.
        - `TEACHER_RESPONSE_FINISHED` (23): Indicates the teacher's response has finished.
	"""
    NEED_TRANSFORM_SENTENCE = -1
    NOT_ASKED = 0
    WAITING_STUDENT_ANSWER = 1  # TODO Need to implement llm to check whether is the user's input actually trying to answer the question.
    CHECKING_DID_STUDENT_ANSWER = 2  # TODO Not Implemented
    WAITING_USER_INPUT = 3
    NEED_CALL_DIRECTOR = 4
    WAITING_DIRECTOR_RETURN = 5
    FINISHED = 9  # Director Selected Finished
    CONTINUE_FINISHED = 10  # Finished In Continue Mode
    DIRECTOR_NOT_FOUND_FINISHED = 20  # Error Finish

    FORCE_CALL_TEACHER_BEFORE_RETURN = 21
    WAIT_FINISH = 22
    TEACHER_RESPONSE_FINISHED = 23



class AskQuestionAgentNameConst:
    """
    Define the agent names used in the AskQuestion function.
    """
    USER_NAME = "真人学生" # Real Student
    END_SEQUENCE_NAME = "PPT翻页员" # Slide Pager


class AskQuestion(Function):
    """
    Implementation For `askQuestion` function on the student-end. Each `askQuestion` consists of a question that must be asked to the student.
	"""
    init_status = {
        "phase": AskQuestionStatus.NEED_TRANSFORM_SENTENCE,
        "llm_job_id": None,
        "agent_talked": False,
        "force_agent": False,
        "student_answer": "",
        "student_answer_correct": False,
    }

    @staticmethod
    def format_question(value, with_answer=True):
        """
        Formats the question based on the question type (multiple choice or single choice).

        Args:
            value (dict): Contains question details such as type, text, options, and answer.
            with_answer (bool, optional): Whether to include the correct answer in the output. Defaults to True.

        Returns:
            str: The formatted question string.
            str (optional): The correct answer, if `with_answer` is True.
        """
        question_str = ""
        answer = ""
        if value["question_type"] == "multiple choice":
            question_str += f"(多选题) " # multiple choice
            question_str += value["question"] + "\n"
            for i, option in enumerate(value["selects"]):
                # convert i to capital letter
                i_to_capital = chr(ord('A') + i)
                question_str += f"{i_to_capital}. {option}\n"
            if with_answer:
                val_capital = [chr(ord('A') + i) for i in value['answer']]
                answer = ''.join(sorted(val_capital))
        elif value["question_type"] == "single choice":
            question_str += f"(单选题) " # single choice
            question_str += value["question"] + "\n"
            for i, option in enumerate(value["selects"]):
                i_to_capital = chr(ord('A') + i)
                question_str += f"{i_to_capital}. {option}\n"
            if with_answer:
                val_capital = [chr(ord('A') + i) for i in value['answer']]
                answer = ''.join(sorted(val_capital))
        else:
            print("Question Type Not Implemented")

        if with_answer:
            return question_str, answer
        return question_str

    @staticmethod
    def format_question_obj(value: dict, with_answer=True):
        """
        Formats a question object, optionally excluding fields such as 'answer' and 'analysis'.

        Args:
            value (dict): The question object to format.
            with_answer (bool, optional): Whether to include fields such as 'answer' and 'analysis'. Defaults to True.

        Returns:
            dict: The formatted question object with added 'pure_text' field.
        """

        if not with_answer:
            if "answer" in value.keys():
                value.pop("answer")
            if "analysis" in value.keys():
                value.pop("analysis")
        value["pure_text"] = AskQuestion.format_question(
            value=value,
            with_answer=False,
        )
        return value

    @staticmethod
    def step(
            value: dict,
            function_id: str,
            classroom_session: ClassroomSession,
    ):
        """
        Handles the step-wise execution of the AskQuestion function, transitioning between phases like question preparation, 
        presenting the question, evaluating the student's answer, and concluding with feedback.
        
        Phases:
            1. `NEED_TRANSFORM_SENTENCE`: The question needs to be transformed.
            2. `NOT_ASKED`: The question has not been asked yet.
            3. `WAITING_STUDENT_ANSWER`: Waiting for an answer from the student.
            4. `FORCE_CALL_TEACHER_BEFORE_RETURN`: Forces a call to the teacher to check the student's answer.
            5. `WAIT_FINISH`: Waiting for the finish signal.
            6. `TEACHER_RESPONSE_FINISHED`: Indicates the teacher's response has finished.

        Args:
            value (dict): The question data, including type, options, and answer.
            function_id (str): The unique identifier for the current function.
            classroom_session (ClassroomSession): The classroom session object to interact with the student and agents.

        Returns:
            bool: Whether the function is ready to move to the next step.
        """
        function = classroom_session.get_current_function()
        function_status = function.get("status")
        classroom_session.set_step_id()
        if function_status["phase"] == AskQuestionStatus.NEED_TRANSFORM_SENTENCE:
            classroom_session.disable_user_input(function_id=function_id)
            agent_id = classroom_session.get_teacher_agent_id()
            classroom_session.send_markdown_message(
                function_id=function_id,
                message="在继续学习之前，先来答题互动一下吧", # Before keep going, let's answer some questions.
                speaker_id=agent_id,
            )
            function_status["phase"] = AskQuestionStatus.NOT_ASKED
            classroom_session.update_function_status(
                function_id=function_id,
                status=function_status,
            )
            return True
        elif function_status["phase"] == AskQuestionStatus.NOT_ASKED:
            classroom_session.disable_user_input(function_id=function_id)

            formatted_question = AskQuestion.format_question(
                value=value,
                with_answer=False,
            )
            # Send The Question via Teacher Agent
            agent_id = classroom_session.get_teacher_agent_id()
            # classroom_session.send_markdown_message(
            # 	function_id=function_id,
            # 	message=formatted_question,
            # 	speaker_id=agent_id,
            # 	)
            classroom_session.send_function_to_message(
                function_id=function_id,
                content=AskQuestion.format_question_obj(value, with_answer=False),
                speaker_id=agent_id,
                action=MAICChatActionDict.QUESTION.value,
            )
            function_status["phase"] = AskQuestionStatus.WAITING_STUDENT_ANSWER
            classroom_session.force_user_input(function_id=function_id)
            classroom_session.update_function_status(
                function_id=function_id,
                status=function_status,
            )
            # classroom_session.enable_user_input()
            return False
        elif function_status["phase"] == AskQuestionStatus.WAITING_STUDENT_ANSWER:
            classroom_session.disable_user_input(function_id=function_id)
            question_history = classroom_session.get_action_history(
                max_return=1,
                action_type=MAICChatActionDict.QUESTION.value,
            )
            answer_history = classroom_session.get_action_history(
                max_return=1,
                action_type=MAICChatActionDict.USER_ANSWER.value,
            )
            if (len(answer_history) < 1) or (answer_history[-1]["action_time"] < question_history[-1][
                "action_time"]):  # User didn't input anything
                # classroom_session.send_message(
                # 	function_id=function_id,
                # 	message="请回答问题", # Please answer the question.
                # 	speaker_id=classroom_session.get_teacher_agent_id()
                # )
                classroom_session.force_user_input(function_id=function_id)
                return False
            # User did input something
            # Append answer to function status
            # student_answer = "".join(sorted(answer_history[-1]["content"]["value"]))
            student_answer = answer_history[-1]['content']
            function_status["student_answer"] = student_answer
            question, answer = AskQuestion.format_question(
                value=value,
                with_answer=True,
            )
            function_status["student_answer_correct"] = (student_answer == answer)
            agent_id = classroom_session.get_teacher_agent_id()
            # return answer and analysis to student
            classroom_session.send_function_to_message(
                function_id=function_id,
                content=AskQuestion.format_question_obj(value, with_answer=True),
                speaker_id=agent_id,
                action=MAICChatActionDict.ANSWER.value,
            )

            # # Call director
            # function_status["phase"]=AskQuestionStatus.NEED_CALL_DIRECTOR
            # function_status["force_agent"]=True

            # Call teacher then finish
            function_status["phase"] = AskQuestionStatus.FORCE_CALL_TEACHER_BEFORE_RETURN
            classroom_session.update_function_status(
                function_id=function_id,
                status=function_status,
            )
            return True
        elif (
                function_status["phase"] == AskQuestionStatus.FORCE_CALL_TEACHER_BEFORE_RETURN
        ):
            agent_id = classroom_session.get_teacher_agent_id()
            formatted_question, formatted_answer = AskQuestion.format_question(
                value=value,
                with_answer=True,
            )
            instruction = classroom_session.get_agent_by_id(agent_id)["instruction"]

            history = classroom_session.get_history()
            context_ids = [item["_id"] for item in history if item is not None]
            pprint(history)
            agent_list_to_format_history = list(
                set(classroom_session.get_agent_list() + ["user"] + [slic["actor"] for slic in history]))
            agent_dict = AskQuestion.get_agent_id2name_dict(
                classroom_session,
                agent_list_to_format_history
            )
            student_answer = function_status["student_answer"]
            is_correct = "学生回答对了" if function_status["student_answer_correct"] else "学生回答错了"
            scene_instruction = f"现在课堂处于提问小测环节。当前问题是{formatted_question}，标准答案是{formatted_answer}，学生给出的答案是{student_answer}。{is_correct}。请你对他的回答做出点评，解释正确的答案，并鼓励他继续学习。".replace(
                "学生", AskQuestionAgentNameConst.USER_NAME)
            # translation: now the classroom is in the question test stage. The current question is {formatted_question}, the correct answer is {formatted_answer}.
            # And the student's answer is {student_answer}. {is_correct}. Please give your evaluation of his answer, explain the correct answer, and encourage him to continue learning.
            instruction = instruction + scene_instruction

            formatted_history = '\n'.join(
                [
                    AskQuestion.format_history_for_agent(item, agent_dict)
                    for item in history
                ] + [
                    "你的回复是：", "" # "Your reply is":
                ]
            )
            request = dict(
                messages=[
                    dict(role="system", content=instruction),
                    dict(role="user", content=formatted_history),
                ]
            )
            # print("Check if goes to call_agent_job")
            call_agent_job = classroom_session.send_streamed_model_request(
                function_id=function_id,
                request=request,
                speaker_id=agent_id,
                try_list=["glm-4"],
            )
            # function_status["llm_job_id"]=call_agent_job
            function_status["phase"] = AskQuestionStatus.WAIT_FINISH
            function_status["agent_talked"] = True
            classroom_session.update_function_status(
                function_id, function_status
            )
            # classroom_session.enable_user_input()
            return True
        elif (
                function_status["phase"] == AskQuestionStatus.WAIT_FINISH
        ):
            function_status["phase"] = AskQuestionStatus.TEACHER_RESPONSE_FINISHED
            classroom_session.update_function_status(
                function_id=function_id,
                status=function_status
            )
            classroom_session.to_next_function()
            return True

    @staticmethod
    def is_agent_teacher(agent_id, classroom_session):
        """
        Checks if the given agent is a teacher.

        Args:
            agent_id (str or ObjectId): The ID of the agent to check.
            classroom_session (ClassroomSession): The classroom session to query agent details.

        Returns:
            bool: True if the agent is a teacher, False otherwise.
        """
        if type(agent_id) == str:
            agent_id = ObjectId(agent_id)
        agent_type = classroom_session.get_agent_by_id(agent_id)["agent_type"]
        return (agent_type == IdentityDict.AI_TEACHER.value)

    @staticmethod
    def is_agent_ta(agent_id, classroom_session):
        """
        Checks if the given agent is a teaching assistant (TA).

        Args:
            agent_id (str or ObjectId): The ID of the agent to check.
            classroom_session (ClassroomSession): The classroom session to query agent details.

        Returns:
            bool: True if the agent is a TA, False otherwise.
        """
        if type(agent_id) == str:
            agent_id = ObjectId(agent_id)
        agent_type = classroom_session.get_agent_by_id(agent_id)["agent_type"]
        return (agent_type == IdentityDict.AI_ASSISTANT.value)

    @staticmethod
    def format_history(message, agent_dict):
        """
        Formats a message's history for logging purposes.

        Args:
            message (dict): The message containing content and actor information.
            agent_dict (dict): A mapping of agent IDs to their names.

        Returns:
            str: A formatted string representing the message's actor and content.
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
        Formats a message history for presenting to an agent.

        Args:
            message (dict): The message containing content and actor information.
            agent_dict (dict): A mapping of agent IDs to their names.

        Returns:
            str: A formatted string for the agent, with actor and content details.
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
    def get_agent_name_by_id(agent_id, classroom_session):
        """
        Retrieves the name of an agent by their ID.

        Args:
            agent_id (str or ObjectId): The ID of the agent.
            classroom_session (ClassroomSession): The classroom session to query agent details.

        Returns:
            str: The name of the agent.
        """
        if agent_id == "user":
            return AskQuestionAgentNameConst.USER_NAME
        if type(agent_id) == str:
            agent_id = ObjectId(agent_id)
        return classroom_session.get_agent_by_id(agent_id)["name"]

    @staticmethod
    def get_agent_id2name_dict(classroom_session: ClassroomSession, agent_list: list):
        """
        Creates a dictionary mapping agent IDs to their names.

        Args:
            classroom_session (ClassroomSession): The classroom session to query agent details.
            agent_list (list): A list of agent IDs.

        Returns:
            dict: A dictionary mapping agent IDs to their names.
        """
        agent_dict = {
            str(agent_id): AskQuestion.get_agent_name_by_id(agent_id, classroom_session)
            for agent_id in agent_list
        }
        return agent_dict

    @staticmethod
    def get_agent_role(agent_id, classroom_session):
        """
        Retrieves the role and identity of an agent.
        
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
            classroom_session (ClassroomSession): The classroom session to query agent details.

        Returns:
            dict: A dictionary containing the agent's identity and role description.
        """
        if agent_id == "user":
            return dict(
                identity=IdentityDict.STUDENT.value,
                role=f"{AskQuestionAgentNameConst.USER_NAME}：整个班级存在的意义就是为了能够教会{AskQuestionAgentNameConst.USER_NAME}学明白题目的正确答案以及为什么。")
        agent_name = classroom_session.get_agent_by_id(agent_id)["name"]
        if agent_name == "小刘老师" or agent_name == "小詹老师": # Prof. Liu or Prof. Zhan
            return dict(
                identity=IdentityDict.AI_TEACHER.value,
                role=f"{agent_name}: 知道问题的真正答案。当学生回答后，会对题目进行讲解。")
        if agent_name == "助教": # Teaching Assistant
            return dict(
                identity=IdentityDict.AI_ASSISTANT.value,
                role=f"助教: 负责维持课堂秩序，当学生刚刚发表了过激的言论，或一直在尝试偏离课程讨论的主题时，助教会站出来维持课堂的纪律。除此之外助教不会说话。")
        if agent_name == "显眼包": # Class Clown
            return dict(
                identity=IdentityDict.AI_STUDENT.value,
                role=f"显眼包: 当{AskQuestionAgentNameConst.USER_NAME}很久没有说话，或者说了跟当前问题不相关的话的时候，会通过插科打诨的方式强行把课程的主题和{AskQuestionAgentNameConst.USER_NAME}跑题的话结合在一起。帮助老师把课程引回到问题的讨论上去")
        if agent_name == "好奇宝宝": # Inquisitive Mind
            return dict(
                identity=IdentityDict.AI_STUDENT.value,
                role=f"好奇宝宝: 好奇宝宝会在{AskQuestionAgentNameConst.USER_NAME}没有明白正确答案的时候提出一些前置问题。帮助{AskQuestionAgentNameConst.USER_NAME}更好的找到理解问题正确答案的角度。")
        if agent_name == "笔记员": # Note Taker
            return dict(
                identity=IdentityDict.AI_STUDENT.value,
                role=f"笔记员: 笔记员是一个勤奋的记录笔记的学生。他会在老师已经给出正确的答案后，对讨论进行总结，记下最适合{AskQuestionAgentNameConst.USER_NAME}在期末复习的时候找回理解问题正确答案的思路。")
        if agent_name == "思考者": # Deep Thinker
            return dict(
                identity=IdentityDict.AI_STUDENT.value,
                role=f"思考者: 思考者会在{AskQuestionAgentNameConst.USER_NAME}理解了问题，但是没有完全理解的时候，找到{AskQuestionAgentNameConst.USER_NAME}没有理解的部分并提出更深入的问题，以确定{AskQuestionAgentNameConst.USER_NAME}真的理解了。")
        # print(f"llm/classroom/functions/askQuestion.py: {agent_name} Role Not Defined")
        return {}

    @staticmethod
    def async_call_director(
            classroom_session: ClassroomSession, history: list, agent_list: list, ban_end_sequence: bool, **kwargs
    ):
        """
        Initiates a call to the director to determine the next actor in the conversation based on the roles and history.

        Args:
            classroom_session (ClassroomSession): The classroom session object for managing interactions.
            history (list): The conversation history to use as context.
            agent_list (list): List of agents eligible to respond.
            ban_end_sequence (bool): Whether to disallow special end-sequence roles.

        Returns:
            dict: The job object containing details of the call to the director.
        """
        context_ids = [slic["id"] for slic in history if slic is not None]
        agent_list_to_format_history = list(
            set(classroom_session.get_agent_list() + ["user"] + [slic["actor"] for slic in history]))
        agent_dict = AskQuestion.get_agent_id2name_dict(
            classroom_session,
            agent_list_to_format_history
        )
        history = "\n".join([
            AskQuestion.format_history(message, agent_dict) for message in history
        ])

        agent_roles = [AskQuestion.get_agent_role(agent_id, classroom_session) for agent_id in agent_list]

        teacher_roles = [agent["role"] for agent in agent_roles if
                         agent and agent["identity"] == IdentityDict.AI_TEACHER.value]
        assistant_roles = [agent["role"] for agent in agent_roles if
                           agent and agent["identity"] == IdentityDict.AI_ASSISTANT.value]
        student_roles = [agent["role"] for agent in agent_roles if agent and (
                agent["identity"] == IdentityDict.STUDENT.value or agent[
            "identity"] == IdentityDict.AI_STUDENT.value)]

        teacher_roles = '\n'.join(teacher_roles) if teacher_roles else "教师类演员不可选" # Teacher roles unavailable
        assistant_roles = '\n'.join(assistant_roles) if assistant_roles else "助教类演员不可选" # Assistant roles unavailable
        student_roles = '\n'.join(student_roles) if assistant_roles else "学生类演员不可选" # Student roles unavailable

        control_roles = f"{AskQuestionAgentNameConst.END_SEQUENCE_NAME}: 他负责控制PPT的翻页，在当前问题的讨论全部结束之后，他会切换到下一个主题。" if not ban_end_sequence else "特殊类演员不可选" # Special roles unavailable.
        # This role takes charge of controlling the slides. When all the discussion is over, it will switch to the next topic.


        agent_roles = f"""
### 老师
{teacher_roles}
### 助教
{assistant_roles}
### 学生
{student_roles}
### 特殊演员
{control_roles}
		""".strip()

        return classroom_session.push_llm_job_to_list(
            request={
                "messages": [
                    {
                        "role": "system",
                        "content": f"你是一个非常优秀的剧本大师。现在你已经确定了可能说出下一句话的候选演员，并给他们分好了他们说话的任务：\n{agent_roles}\n\n用户会告诉你每个演员在剧本里说了什么话。你的任务是在遵守每个演员任务和人设的情况下，判断该轮到哪位演员说话了。你的输出应当只包括演员的名字（例如，直接输出\"{AskQuestionAgentNameConst.USER_NAME}\"这几个字），不应当包括任何额外的标点符号（除非演员的名字里包括符号），你更不应当解释为什么要选择这个演员。有的时候用户所提供的对话历史里会包括其他的角色，你被禁止选择这些演员，因为他们已经确定不会说话了。",
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
        