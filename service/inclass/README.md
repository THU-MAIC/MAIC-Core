# InClass 调用逻辑

假设当前的状态是
```bash
刚调用完classroom_function.to_next_function()，这个函数会把当前的最后一个function设为is_done=True
```

这个时候我们重新调用get_current_function会设置新的function并且传给我们（这个函数的逻辑是把最靠前的还没有done的function返回，如果没有就从agenda里按照dfs进行搜索，直到找到下一个有function的agenda并把agenda,functions全都抄录一遍），

我们假设这个function.type是ReadScript。

在get_current_function加载agenda里的function的时候就会到每一个function的实现里把初始状态复制到function的status里，ReadScript的初始状态是这个
```json
init_status = { 
    "phase": ReadScriptStatus.UNREAD, # 代表讲稿还没有念过
    "llm_job_id": None, 用来存llm的job id
    "agent_talked": False, 用来记录用户上一次说完话我们有没有让agent理他
}
```

调完get_current_function我没记错的话下一步的逻辑是executer = FUNCTION_LIST.get(function.type)
这一步的作用是按照当前function的类型找到执行器，比如readscript的执行器就是service.inclass.functions.readScript.py里的ReadScript类

这个时候我们再调用
```bash
continue_generate = executor.step(function.value, classroom_session, ...)
```
按照ReadScript.step的逻辑 我们会发现当前的phase是ReadScriptStatus.UNREAD，所以我们执行这一段逻辑
```python
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
```
因为我们念完讲稿就应该允许学生交互了，所以返回False

我们假设学生此时发了条消息（在发消息的时候我们顺带会通过classroom_session.add_user_message去吧用户的消息怼到 数据库的消息历史里），或者点了连续模式

我们此时又从前端调用后端的接口，触发了后端的逻辑 然后，在后端的逻辑里：
```python
continue_generate =  True
while continue_generate:
    function = classroom_session.get_current_function()
    executer = FUNCTION_LIST.get(function.type)
    continue_generate = executor.step(function.value, classroom_session, ...)
```

因为此时正在执行的function还是前一次调用的readScript，所以我们又进入了ReadScript的执行器（executor）
但是因为上次我们在返回前把状态改成了`function_status["phase"] = ReadScriptStatus.WAITING_USER_INPUT`，也就是上一次后端推理的结束状态是“等待用户输入”，所以根据这个逻辑，我们先判断用户是否说话了（红色部分），然后如果用户没说话那就说明我们进入了连续模式（绿色部分）：我们看看是不是能概率触发强制让现眼包说话的逻辑（如果这个概率成功触发了那就是黄色部分，因为我把调现眼包的逻辑写到了FORCE_AGENT_TO_HEATUP_TALK里，所以我们把这个设为新的phase并且return True来让后端切换到调现眼包的逻辑里），如果没触发（蓝色部分的逻辑）那就按照连续模式的常规逻辑结束当前readScript的function，并且通过return True来触发后端的下次调用，通过下一次后端逻辑里的get_current_function来切换到下一个function的逻辑（蓝色部分，CONTINUE_FINISH代表连续模式结束）

[Need Picture Here]

最后如果用户说话了，那就得调用导演，所以我们把phase设为NEED_CALL_DIRECTOR然后返回True，来让后端继续生成


这样我们就能够同时支持命令行调试还有部署时直接在有限的进程数（worker）下去分时服用

在命令行的调试器里(伪代码)：
```python
while True:
    continue_generate = True
    while continue_generate:
        function = classroom_session.get_current_function()
        if function.status.llm_job_id != None: # 检查是否还有正在执行的llm调用
            if classroom_session.check_llm_job_done():
                pass # 写把llm返回填回去的逻辑
            else:
                sleep(0.1)
                continue
        executer = FUNCTION_LIST.get(function.type)
        continue_generate = executor.step(function.value, classroom_session, ...)
    user_input = input("Input nothing to simulate continue mode")
    if user_input:
        classroom_session.add_user_message(user_input)
```

在并行的上线版本里(伪代码)
```python
def worker.handle_job(job_id, job_session_id, user_input):
    classroom_session = ClassroomSession(job_session_id):
    if user_input:
        classroom_session.add_user_message(user_input)
        function = classroom_session.get_current_function()
    if function.status.llm_job_id != None: # 检查是否还有正在执行的llm调用
        if classroom_session.check_llm_job_done()
            pass # 写把llm返回填回去的逻辑
        else:
            push_job_to_rabbitmq(job_id, job_session_id, None)
    else:
        executer = FUNCTION_LIST.get(function.type)
        continue_generate = executor.step(function.value, classroom_session, ...)
        if continue_generate:
            push_job_to_rabbitmq(job_id, job_session_id, None)
```

前者（命令行版本）通过sleep的等待把异步调用转成同步，

后者（并行线上版本）每次每个session只处理一次step，处理完了还没结束（continue_generate=True）也是推到任务队列的最后，让其他用户也能先跑一点生成再轮训回到这个session，执行下一次step


# InClass Execution Workflow

This document explains the execution logic of the InClass module for handling classroom functions. The system is designed to support both debugging through a command-line interface and concurrent deployments with limited worker processes.

## Execution Workflow Overview

### Initial State

The system starts with the following state:

- Just completed `classroom_function.to_next_function()`, which marks the last function as `is_done=True`.

At this point, invoking get_current_function() initializes a new function. This function searches for the next uncompleted task in the agenda using depth-first search (DFS). If found, it updates the agenda and function list accordingly. For example, assume the new function has a type ReadScript.

When the agenda loads a function, its initial state is copied into the function’s status. For ReadScript, the default status is:

```json
{
    "phase": "UNREAD",   // Indicates the script hasn't been read.
    "llm_job_id": null,  // Stores the job ID of an LLM task.
    "agent_talked": false // Tracks if the agent has responded to the user's last input.
}
```

### Function Executor Initialization

After get_current_function completes, the next step is to find the executor for the function type:

```python
executor = FUNCTION_LIST.get(function.type)
```

For example, the executor for ReadScript is implemented in `service.inclass.functions.readScript.py` under the ReadScript class.

#### Function Execution: ReadScript Example

When calling:

```python
continue_generate = executor.step(function.value, classroom_session, ...)
```

The ReadScript.step method is invoked. If the current phase is UNREAD, the following logic is executed:

```python
if function_status["phase"] == ReadScriptStatus.UNREAD:
    classroom_session.disable_user_input(function_id=function_id)
    teacher_id = classroom_session.get_teacher_agent_id()
    classroom_session.send_script_to_message(function_id, value, teacher_id)
    function_status["phase"] = ReadScriptStatus.WAITING_USER_INPUT
    classroom_session.update_function_status(
        function_id=function_id, status=function_status
    )
    classroom_session.enable_user_input(function_id=function_id)
    return False
```
Here:
- The teacher reads the script (send_script_to_message).
- User input is disabled and then re-enabled after the phase is updated to WAITING_USER_INPUT.
- The function returns False to indicate that user interaction is now allowed.

Handling User Interaction or Continuous Mode

If a user sends a message (logged into the database via `classroom_session.add_user_message`) or activates continuous mode, the backend logic proceeds as follows:

```python
continue_generate = True
while continue_generate:
    function = classroom_session.get_current_function()
    executor = FUNCTION_LIST.get(function.type)
    continue_generate = executor.step(function.value, classroom_session, ...)
```

When revisiting the ReadScript executor:
- If the phase is `WAITING_USER_INPUT`, it checks if:
    - User spoke: Updates the phase to `NEED_CALL_DIRECTOR` and returns `True`, prompting further backend logic for director handling.
- If continuous mode triggered: 
    - Evaluates whether to force the agent to speak (probabilistic trigger).
    - If triggered, 
        - Updates the phase to `FORCE_AGENT_TO_HEATUP_TALK` and returns `True`. 
    - Otherwise:
        - Marks the ReadScript function as complete.
        - Returns `True` to initiate the next function in the agenda (`CONTINUE_FINISH`).

## Execution Workflow Diagram

[Diagram Placeholder for Workflow]

## Supporting Debugging and Deployment

### Command-Line Debugging (Pseudo-Code)

The debugging mode simulates execution through synchronous loops:

```python
while True:
    continue_generate = True
    while continue_generate:
        function = classroom_session.get_current_function()
        if function.status.llm_job_id:
            if classroom_session.check_llm_job_done():
                # Process LLM output
                pass
            else:
                sleep(0.1)
                continue
        executor = FUNCTION_LIST.get(function.type)
        continue_generate = executor.step(function.value, classroom_session, ...)
    user_input = input("Input (leave blank for continuous mode): ")
    if user_input:
        classroom_session.add_user_message(user_input)
```

Here, asynchronous LLM calls are converted into synchronous steps using sleep polling.

### Production Deployment (Pseudo-Code)


```python
def worker.handle_job(job_id, job_session_id, user_input):
    classroom_session = ClassroomSession(job_session_id)
    if user_input:
        classroom_session.add_user_message(user_input)
    function = classroom_session.get_current_function()
    if function.status.llm_job_id:
        if classroom_session.check_llm_job_done():
            # Process LLM output
            pass
        else:
            push_job_to_queue(job_id, job_session_id, None)
    else:
        executor = FUNCTION_LIST.get(function.type)
        continue_generate = executor.step(function.value, classroom_session, ...)
        if continue_generate:
            push_job_to_queue(job_id, job_session_id, None)
```

In the concurrent online version:
- Each worker processes one step per session.
- If the function isn’t complete, it requeues the session for the next available worker.
- This ensures fair resource sharing across sessions.

By following these principles, InClass supports both scalable deployment and flexible debugging, ensuring robustness in various scenarios.