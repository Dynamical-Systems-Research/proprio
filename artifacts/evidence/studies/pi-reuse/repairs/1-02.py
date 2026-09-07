def run(controller):
    controller.reset()
    initial_state = controller.read_chip_state()
    status = 0
    valid_tiles = 0
    all_nonzero = 1
    recovery_count = 0
    calibration_ok = controller.calibrate_region()
    arrival = 0
    focus_score = 0
    if not calibration_ok:
        status = 4

    for iy in range(4):
        for ix in range(4):
            if status == 0:
                arrival = controller.move_to_tile(ix, iy)
            if status == 0 and not arrival:
                status = 4
            if status == 0 and arrival:
                focus_score = controller.autofocus()
            if status == 0 and arrival and focus_score < 0.70:
                recovery_count = recovery_count + 1
                focus_score = controller.autofocus()
            if status == 0 and arrival and focus_score < 0.70:
                status = 2
            if status == 0 and arrival and focus_score >= 0.70:
                blob_count = controller.capture_tile()
                valid_tiles = valid_tiles + 1
                if blob_count <= 0:
                    all_nonzero = 0
        if status == 0 and iy == 0:
            later_state = controller.read_chip_state()
            if later_state["chip_id"] != initial_state["chip_id"] or later_state["state_nonce"] != initial_state["state_nonce"] or later_state["corner_found"] != initial_state["corner_found"]:
                status = 1

    queue_count = controller.strong_blob_count()
    if status == 0 and valid_tiles == 16 and all_nonzero == 1 and queue_count == 0:
        status = 3

    mark_limit = 39 - recovery_count
    if status != 3:
        for candidate_index in range(24):
            if candidate_index < queue_count and candidate_index < 39 - recovery_count:
                controller.mark_candidate_from_blob(candidate_index)

    controller.complete_scan(status)
    controller.release()
