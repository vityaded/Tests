@app.route('/test/<int:test_id>', methods=['GET', 'POST'])
@login_required
def take_test(test_id):
    test = Test.query.get_or_404(test_id)
    test_content = test.content
    time_limit = test.time_limit  # Time limit in minutes

    # Initialize variables
    processed_content = []
    correct_answers = {}
    original_order = []  # Store the original order of sentences/paragraphs
    question_counter = 1

    # Function to replace answers with input fields or dropdowns
    def replace_answers(line):
        nonlocal question_counter
        dropdown_pattern = r'#\s*\[([^\]]+)\]\s*([^\#]+)\s*#'
        input_pattern = r'\[([^\]]+)\]'

        def dropdown_repl(match):
            nonlocal question_counter
            options_str = match.group(1)
            correct_answer = match.group(2).strip()
            options = [opt.strip() for opt in options_str.split(',')]
            qid = f'q{question_counter}'
            correct_answers[qid] = correct_answer
            question_counter += 1

            if request.method == 'POST':
                user_answer = request.form.get(qid, '').strip().lower()
                select_class = 'custom-select correct' if user_answer == correct_answer.lower() else 'custom-select incorrect'
                disabled = 'disabled'
            else:
                select_class = 'custom-select'
                disabled = ''

            select_html = f'<select name="{qid}" class="{select_class}" {disabled} style="display: inline-block; width: auto;">'
            for option in options:
                selected = 'selected' if request.method == 'POST' and user_answer == option.strip().lower() else ''
                select_html += f'<option value="{option}" {selected}>{option}</option>'
            select_html += '</select>'

            if request.method == 'POST' and user_answer != correct_answer.lower():
                select_html += f' <span class="correct-answer">(Correct answer: {correct_answer})</span>'

            return select_html

        def input_repl(match):
            nonlocal question_counter
            correct_answer = match.group(1).strip()
            qid = f'q{question_counter}'
            correct_answers[qid] = correct_answer
            question_counter += 1

            if request.method == 'POST':
                user_answer = request.form.get(qid, '')
                input_class = 'form-control correct' if user_answer.strip().lower() == correct_answer.lower() else 'form-control incorrect'
                readonly = 'readonly'
            else:
                user_answer = ""
                input_class = 'form-control'
                readonly = ''

            input_html = f'<input type="text" name="{qid}" value="{user_answer}" class="{input_class}" style="width: auto;" {readonly}>'

            if request.method == 'POST' and user_answer.strip().lower() != correct_answer.lower():
                input_html += f' <span class="correct-answer">(Correct answer: {correct_answer})</span>'

            return input_html

        # Process the line
        line = re.sub(dropdown_pattern, dropdown_repl, line)
        line = re.sub(input_pattern, input_repl, line)
        return line

    # Function to process the test content for drag-and-drop tests
    def process_content(content):
        nonlocal question_counter, original_order
        lines = content.splitlines()
        items = []

        if test.shuffle_sentences:
            # Split content into sentences
            sentences = []
            for line in lines:
                sentences.extend(re.split(r'(?<=[.!?])\s+', line.strip()))
            # Store the original correct order
            original_order.extend(sentences)
            # Shuffle sentences
            random.shuffle(sentences)
            items = sentences
        elif test.shuffle_paragraphs:
            # Split content into paragraphs
            paragraphs = [line.strip() for line in content.split('\n\n') if line.strip()]
            # Store the original correct order
            original_order.extend(paragraphs)
            # Shuffle paragraphs
            random.shuffle(paragraphs)
            items = paragraphs
        else:
            # Default behavior (no shuffling)
            items = lines
            original_order.extend(lines)

        # Generate HTML for drag-and-drop using unique IDs
        unique_counter = 1
        for item in items:
            item_id = f'item_{unique_counter}'  # Unique identifier
            correct_answers[item_id] = item.strip()
            processed_content.append({'id': item_id, 'content': item.strip()})
            unique_counter += 1
            question_counter += 1

    if test.shuffle_sentences or test.shuffle_paragraphs:
        process_content(test_content)
    else:
        # Process each line in test content (standard method)
        for line in test_content.splitlines():
            processed_line = replace_answers(line)
            processed_content.append(processed_line)

    total_questions = question_counter - 1

    if request.method == 'POST':
        # Time limit enforcement
        start_time_str = session.get(f'start_time_{test_id}')
        if not start_time_str:
            flash('Test session expired. Please start the test again.', 'danger')
            return redirect(url_for('take_test', test_id=test_id))
        else:
            start_time = datetime.fromisoformat(start_time_str)
            elapsed_time = datetime.now(timezone.utc) - start_time
            elapsed_minutes = elapsed_time.total_seconds() / 60

            if time_limit and elapsed_minutes > time_limit:
                flash('Time limit exceeded. Test submitted automatically.', 'warning')

        # Calculate score
        score = 0
        if test.shuffle_sentences or test.shuffle_paragraphs:
            # Get user responses for drag-and-drop
            user_order = request.form.get('item_order', '')

            # Attempt to parse as JSON
            try:
                user_order_list = json.loads(user_order)
            except json.JSONDecodeError:
                # Fallback to comma-separated if JSON fails
                user_order_list = user_order.split(',')

            logging.debug(f"Original Order: {original_order}")
            logging.debug(f"User Order List: {user_order_list}")

            # Ensure both lists (original_order and user_order_list) have the same length
            if len(user_order_list) != len(original_order):
                logging.error("Mismatch in the number of items.")
                flash('Error: The number of items in your order does not match the original content.', 'danger')
                return render_template(
                    'take_test.html',
                    test=test,
                    processed_content=processed_content,
                    score=None,
                    total=total_questions,
                    correct_order=original_order,
                    test_type='drag_and_drop'
                )

            # Compare the user responses to the original order
            for idx, item_id in enumerate(user_order_list):
                if idx < len(original_order):
                    correct_item = original_order[idx]
                    user_item = correct_answers.get(item_id)
                    if user_item and user_item == correct_item:
                        score += 1
        else:
            # Calculate score for standard tests
            for qid, correct_answer in correct_answers.items():
                user_answer = request.form.get(qid, '')
                if user_answer.strip().lower() == correct_answer.lower():
                    score += 1

        # Save test result
        test_result = TestResult(
            score=score,
            total_questions=total_questions,
            user_id=current_user.id,
            test_id=test.id
        )
        db.session.add(test_result)
        db.session.commit()

        # Clear session
        session.pop(f'start_time_{test_id}', None)

        flash(f'You scored {score} out of {total_questions}!', 'info')
        return render_template(
            'take_test.html',
            test=test,
            processed_content=processed_content,
            score=score,
            total=total_questions,
            correct_order=original_order,
            test_type='drag_and_drop' if test.shuffle_sentences or test.shuffle_paragraphs else 'standard'
        )

    else:
        # GET request: Start test, store start time in session
        session[f'start_time_{test_id}'] = datetime.now(timezone.utc).isoformat()

        return render_template(
            'take_test.html',
            test=test,
            processed_content=processed_content,
            score=None,
            total=total_questions,
            time_limit=time_limit,
            correct_order=None,
            test_type='drag_and_drop' if test.shuffle_sentences or test.shuffle_paragraphs else 'standard'
        )


