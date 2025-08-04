from .classroom_session import ClassroomSession
from .functions import get_function

from bson import ObjectId


def main():
    import time

    session_id = '674ff0c87baecad6fd515719'
    session = ClassroomSession(session_id)
    session.clear_session()

    input_str = ''
    while input_str != 'quit':
        count = 0
        while True:
            count += 1
            if session.is_streaming():
                print('is_streaming')
                time.sleep(1)
                continue

            function_session = session.get_current_function()
            if not function_session:
                print('exit, the classroom session has ended')
                exit(0)

            function_id = str(function_session['_id'])
            executor_name = function_session['call']
            executor = get_function(executor_name)

            value = function_session['value']

            if executor_name != 'ReadScript':
                from pprint import pprint
                pprint(function_session)

            continue_generate = executor.step(
                value=value,
                function_id=function_id,
                classroom_session=session,
            )
            if not continue_generate:
                break
        if executor_name == 'ReadScript':
            continue  # set default to continue mode
        
        input_str = input('User Input(Type Empty Message For Continue Mode): ')
        if input_str.strip() and input_str != 'quit':
            if executor_name == 'AskQuestion':
                session.add_user_message(input_str, 'answer')
            else:
                session.add_user_message(input_str)
                

if __name__ == '__main__':
    main()
