def run(controller):
    controller.reset()
    initial_state = controller.read_chip_state()
    initial_chip_id = initial_state["chip_id"]
    initial_nonce = initial_state["state_nonce"]
    calibration_ok = controller.calibrate_region()
    status = 0
    saw_nonzero_blob_count = False
    recovery_count = 0

    for iy in range(4):
        if calibration_ok and status == 0:
            state_now = controller.read_chip_state()
            if state_now["chip_id"] != initial_chip_id or state_now["state_nonce"] != initial_nonce:
                status = 1
            for ix in range(4):
                arrival = False
                if status == 0:
                    arrival = controller.move_to_tile(ix, iy)
                if status == 0 and not arrival:
                    status = 4
                focus_score = 0.0
                if status == 0 and arrival:
                    focus_score = controller.autofocus()
                if status == 0 and arrival and focus_score < 0.70:
                    recovery_count = recovery_count + 1
                    focus_score = controller.autofocus()
                if status == 0 and arrival and focus_score < 0.70:
                    status = 2
                if status == 0 and arrival and focus_score >= 0.70:
                    blob_count = controller.capture_tile()
                if status == 0 and arrival and focus_score >= 0.70 and blob_count > 0:
                    saw_nonzero_blob_count = True

    queue_count = controller.strong_blob_count()
    if status == 0 and saw_nonzero_blob_count and queue_count == 0:
        status = 3
    mark_limit = 22
    for index in range(16):
        if status != 3 and index < queue_count and index < mark_limit:
            controller.mark_candidate_from_blob(index)
    for offset in range(6):
        index = offset + 16
        if status != 3 and index < queue_count and index < mark_limit:
            controller.mark_candidate_from_blob(index)

    controller.complete_scan(status)
    controller.release()
