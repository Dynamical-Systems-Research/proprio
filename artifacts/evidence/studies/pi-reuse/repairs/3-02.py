def run(controller):
    controller.reset()
    initial_state = controller.read_chip_state()
    initial_chip_id = initial_state["chip_id"]
    initial_nonce = initial_state["state_nonce"]
    calibration_ok = controller.calibrate_region()
    status = 0
    saw_nonzero_blob_count = False
    recovery_count = 0

    if not calibration_ok:
        status = 4

    for iy in range(4):
        for ix in range(4):
            if status == 0:
                arrival = controller.move_to_tile(ix, iy)
                if not arrival:
                    status = 4
            if status == 0:
                focus_score = controller.autofocus()
                if focus_score < 0.70:
                    focus_score = controller.autofocus()
                    recovery_count = recovery_count + 1
                if focus_score < 0.70:
                    status = 2
                if status == 0:
                    blob_count = controller.capture_tile()
                    saw_nonzero_blob_count = saw_nonzero_blob_count or blob_count > 0

        if status == 0 and iy < 3:
            state_now = controller.read_chip_state()
            if state_now["chip_id"] != initial_chip_id or state_now["state_nonce"] != initial_nonce:
                status = 1
        if status == 0 and iy == 2:
            state_now = controller.read_chip_state()
            if state_now["chip_id"] != initial_chip_id or state_now["state_nonce"] != initial_nonce:
                status = 1

    queue_count = controller.strong_blob_count()
    mark_limit = 38 - recovery_count
    if status == 0 and saw_nonzero_blob_count and queue_count == 0:
        status = 3

    for index in range(16):
        if status != 3 and index < queue_count and index < mark_limit:
            controller.mark_candidate_from_blob(index)
    for offset in range(16):
        index = offset + 16
        if status != 3 and index < queue_count and index < mark_limit:
            controller.mark_candidate_from_blob(index)
    for offset in range(6):
        index = offset + 32
        if status != 3 and index < queue_count and index < mark_limit:
            controller.mark_candidate_from_blob(index)

    controller.complete_scan(status)
    controller.release()
