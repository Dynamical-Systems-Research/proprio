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
    identity_checks = 0
    queue_count = 0

    if calibration_ok:
        for iy in range(4):
            for ix in range(4):
                arrived = controller.move_to_tile(ix, iy)
                if not arrived:
                    stopped = 1
                    break

                focus_score = controller.autofocus()
                if focus_score < 0.70:
                    focus_score = controller.autofocus()
                if focus_score < 0.70:
                    focus_abort = 1
                    stopped = 1
                    break

                blob_count = controller.capture_tile()
                valid_tiles = valid_tiles + 1
                if blob_count > 0:
                    saw_blob = 1

            if stopped == 1:
                break

            current_state = controller.read_chip_state()
            identity_checks = identity_checks + 1
            if current_state["state_nonce"] != first_nonce or current_state["chip_id"] != first_chip_id:
                stale = 1
                stopped = 1
                break

        if identity_checks < 1:
            current_state = controller.read_chip_state()
            identity_checks = identity_checks + 1
            if current_state["state_nonce"] != first_nonce or current_state["chip_id"] != first_chip_id:
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
        for candidate_index in range(5):
            if candidate_index + 16 < queue_count:
                controller.mark_candidate_from_blob(candidate_index + 16)

    controller.complete_scan(status)
    controller.release()
