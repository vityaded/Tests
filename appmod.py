if test.shuffle_sentences or test.shuffle_paragraphs:
    # Get user responses for drag-and-drop
    user_order = request.form.get('item_order', '')

    # Split the concatenated item_order string into a list of individual item IDs
    user_order_list = user_order.split(',')

    # Ensure both lists (original_order and user_order_list) have the same length
    if len(user_order_list) != len(original_order):
        flash('Error: The number of items in your order does not match the original content.', 'danger')
        return redirect(url_for('take_test', test_id=test_id))

    # Compare the user responses to the original order
    for idx, item_id in enumerate(user_order_list):
        if idx < len(original_order):  # Ensure index doesn't go out of range
            correct_item = original_order[idx].strip()  # Compare with original order, strip spaces for consistency
            user_item = correct_answers.get(item_id.strip())
            if user_item and user_item == correct_item:
                score += 1


