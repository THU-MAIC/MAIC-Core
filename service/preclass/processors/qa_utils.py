def get_question_type(q):
    """
    Determines if a question is multiple or single choice and strips the choice indicator.
    
    Args:
        q (str): The question text containing choice type indicators
        
    Returns:
        tuple: (stripped_question, question_type)
            - stripped_question (str): Question text with choice indicators removed
            - question_type (str): Either 'multiple choice' or 'single choice'
    """
    if '多选' in q: # multiple choice
        question_type = "multiple choice"
        stripped_question = q.rstrip('（多选）').lstrip('（多选）').rstrip('(多选)').lstrip('(多选)').rstrip('[多选]').lstrip('(多选)')
    else:
        question_type = 'single choice'
        stripped_question = q.rstrip('（单选）').lstrip('（单选）').rstrip('(单选)').lstrip('(单选)').rstrip('[单选]').lstrip('[单选]')
    return stripped_question, question_type

def split_ans(ans_text):
    """
    Converts answer choices (A, B, C, D, E) to their corresponding indices.
    
    Args:
        ans_text (str): String containing answer choices (e.g., 'A', 'BC', 'A,B,C')
        
    Returns:
        list: List of integer indices corresponding to the answer choices (e.g., [0] for A, [1,2] for BC)
    """
    selects_map = {'A': 0, 'B': 1, 'C': 2, 'D': 3, 'E': 4}
    # ans_text = ans_text.split('：')[-1].strip()
    # if ', ' in ans_text:
    #     ans_lis = ans_text.split(', ')
    # elif '、' in ans_text:
    #     ans_lis = ans_text.split('、')
    # elif ',' in ans_text:
    #     ans_lis = ans_text.split(',')
    # elif ' ' in ans_text:
    #     ans_lis = ans_text.split(' ') 
    # else: # single or ABC
    #     ans_lis = []
    #     for c in ans_text:
    #         ans_lis.append(c)
    ans_index_lis = []
    # for ans in ans_lis:
    #     ans_index_lis.append(selects_map[ans])
    for i in ans_text:
        if i in selects_map:
            ans_index_lis.append(selects_map[i])
    return ans_index_lis

def strip_select(select_text):
    """
    Removes answer choice prefixes (A., B., C., etc.) from selection text.
    
    Args:
        select_text (str): Text containing answer choice prefix
        
    Returns:
        str: Clean text with prefix removed
    """
    return select_text.lstrip('A. ').lstrip('B. ').lstrip('C. ').lstrip('D. ').lstrip('E. ').lstrip('A.').lstrip('B.').lstrip('C.').lstrip('D.').lstrip('E.').lstrip('A ').lstrip('B ').lstrip('C ').lstrip('D ').lstrip('E ').lstrip('A').lstrip('B').lstrip('C').lstrip('D').lstrip('E')


import copy

def parse_qa(questions):
    """
    Parses a formatted string of questions into structured question-answer objects.
    
    Args:
        questions (str): Multi-line string containing questions, choices, answers, and references
        
    Returns:
        list: List of dictionaries containing parsed QA data with keys:
            - question (str): The question text
            - question_type (str): Type of question ('multiple choice' or 'single choice')
            - selects (list): List of answer choices
            - answer (list): List of correct answer indices
            - reference (str): Reference text for the question
    """
    theme_qas = []
    cnt = 0
    questions_list = questions.split("\n\n")
    q = "q"
    selects = []
    for ques in questions_list: # '问题': quesiton
        if '问题' in ques and 'A' in ques and 'B' in ques and 'C' in ques and 'D' in ques:
            ques = ques.split('问题', 1)
            ques = ques[1]
            ques = ques.lstrip('问题').lstrip("：")
            ques_list = ques.split('\n')
            if "答案：" in ques: # '答案': answer
                if 'A' not in ques_list[1] and len(ques_list[0]) < 10:
                    q = ques_list[1]
                    q_list = q.split("：", 1)
                    if len(q_list) > 1:
                        if len(q_list[0]) < 2:
                            q = q_list[1]
                        else:
                            if '单选' in q_list[1] or '多选' in q_list[1]:
                                q = q_list[0] + q_list[1]
                            else:
                                q = q_list[0]
                    else:
                        q = q_list[0]
                    ques_index = 2
                    if '单选' or '多选' in ques_list[0]:
                        _, question_type = get_question_type(q)
                    else: # '（单选）' or '（多选）' in ques
                        q, question_type = get_question_type(q)
                else:    
                    q = ques_list[0]
                    q_list = q.split("：", 1)
                    if len(q_list) > 1:
                        if len(q_list[0]) < 2:
                            q = q_list[1]
                        else:
                            if '单选' in q_list[1] or '多选' in q_list[1]:
                                q = q_list[0] + q_list[1]
                            else:
                                q = q_list[0]
                    else:
                        q = q_list[0]
                    ques_index = 1
                    q, question_type = get_question_type(q)
                
                selects = []
                ans_index = 0
                for i, que in enumerate(ques_list[ques_index:]):
                    if "答案：" in que:
                        ans = que.lstrip('答案：')
                        ans = split_ans(ans)
                        ans_index = i + ques_index
                        break
                    selects.append(strip_select(que))
                
                if "引用文本：" in ques: # reference
                    for que in ques_list[ans_index + 1:]:
                        if "引用文本：" in que:
                            ref = que.lstrip('引用文本：')
                            break
                            
                    theme_qas.append({'question': q, 'question_type': question_type, 'selects': copy.deepcopy(selects), 'answer': ans, 'reference': ref})
                    cnt += 1
            else:
                if 'A' not in ques_list[1] and len(ques_list[0]) < 10:
                    q = ques_list[1]
                    q_list = q.split("：", 1)
                    if len(q_list) > 1:
                        if len(q_list[0]) < 2:
                            q = q_list[1]
                        else:
                            if '单选' in q_list[1] or '多选' in q_list[1]:
                                q = q_list[0] + q_list[1]
                            else:
                                q = q_list[0]
                    else:
                        q = q_list[0]
                    ques_index = 2
                    if '单选' or '多选' in ques_list[0]:
                        _, question_type = get_question_type(q)
                    else: # '（单选）' or '（多选）' in ques
                        q, question_type = get_question_type(q)
                else:
                    q = ques_list[0]
                    q_list = q.split("：", 1)
                    if len(q_list) > 1:
                        if len(q_list[0]) < 2:
                            q = q_list[1]
                        else:
                            if '单选' in q_list[1] or '多选' in q_list[1]:
                                q = q_list[0] + q_list[1]
                            else:
                                q = q_list[0]
                    else:
                        q = q_list[0]
                    ques_index = 1
                    q, question_type = get_question_type(q)
                
                selects = [strip_select(select) for select in ques_list[ques_index: ]]
        elif "答案：" in ques:
            if q == "q":
                continue
            if "引用文本" in ques:
                que_list = ques.split('\n')
                ans = que_list[0].lstrip('答案：')
                ans = split_ans(ans)
                ref = que_list[1].lstrip('引用文本：')
                theme_qas.append({'question': q, 'question_type': question_type, 'selects': selects, 'answer': ans, 'reference': ref})
                cnt += 1
            else:
                ans = ques.lstrip("答案：")
                ans = split_ans(ans)
        elif "引用文本：" in ques:
            if q == "q":
                continue
            ref = ques.lstrip('引用文本：')
            theme_qas.append({'question': q, 'question_type': question_type, 'selects': selects, 'answer': ans, 'reference': ref})
            cnt += 1
        else:
            continue    
    return theme_qas