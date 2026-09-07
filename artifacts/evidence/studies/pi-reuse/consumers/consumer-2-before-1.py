def run(controller):
    controller.reset()

    first_state = controller.read_chip_state()
    first_chip_id = first_state["chip_id"]
    first_nonce = first_state["state_nonce"]
    calibration_ok = controller.calibrate_region()

    status = 4
    stopped = 0
    stale = 0
    focus_abort = 0
    valid_tiles = 0
    saw_blob = 0
    queue_count = 0
    focus_retries = 0
    arrived = 0
    focus_score = 0.0
    current_state = first_state

    for iy in range(4):
        for ix in range(4):
            if calibration_ok and stopped == 0:
                arrived = controller.move_to_tile(ix, iy)
            if calibration_ok and stopped == 0 and arrived:
                focus_score = controller.autofocus()
            if calibration_ok and stopped == 0 and arrived and focus_score < 0.70:
                focus_retries = focus_retries + 1
                focus_score = controller.autofocus()
            if calibration_ok and stopped == 0 and arrived and focus_score < 0.70:
                focus_abort = 1
                stopped = 1
            if calibration_ok and stopped == 0 and arrived and focus_score >= 0.70:
                blob_count = controller.capture_tile()
                valid_tiles = valid_tiles + 1
                if blob_count > 0:
                    saw_blob = 1
            if calibration_ok and stopped == 0 and not arrived:
                stopped = 1

        if calibration_ok:
            current_state = controller.read_chip_state()
        if calibration_ok and current_state["state_nonce"] != first_nonce:
            stale = 1
            stopped = 1
        if calibration_ok and current_state["chip_id"] != first_chip_id:
            stale = 1
            stopped = 1

    queue_count = controller.strong_blob_count()

    if stale == 1:
        status = 1
    if stale == 0 and focus_abort == 1:
        status = 2
    if stale == 0 and focus_abort == 0 and stopped == 1:
        status = 4
    if stale == 0 and focus_abort == 0 and stopped == 0:
        if valid_tiles == 16:
            if saw_blob == 1 and queue_count == 0:
                status = 3
            if saw_blob == 0 or queue_count > 0:
                status = 0
        if valid_tiles != 16:
            status = 4

    if status != 3:
        for candidate_index in range(16):
            if candidate_index < queue_count:
                controller.mark_candidate_from_blob(candidate_index)
        for candidate_index in range(6):
            if candidate_index + 16 < queue_count:
                controller.mark_candidate_from_blob(candidate_index + 16)

    controller.complete_scan(status)
    controller.release()
