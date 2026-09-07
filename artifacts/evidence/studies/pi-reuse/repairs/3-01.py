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
    else:
        for iy in range(4):
            if iy == 3:
                state_now = controller.read_chip_state()
                if state_now["chip_id"] != initial_chip_id or state_now["state_nonce"] != initial_nonce:
                    status = 1
            if status != 0:
                break

            for ix in range(4):
                arrival = controller.move_to_tile(ix, iy)
                if not arrival:
                    status = 4
                    break

                focus_score = controller.autofocus()
                if focus_score < 0.70:
                    recovery_count = recovery_count + 1
                    focus_score = controller.autofocus()
                    if focus_score < 0.70:
                        status = 2
                        break

                blob_count = controller.capture_tile()
                if blob_count > 0:
                    saw_nonzero_blob_count = True

            if status != 0:
                break

            if iy < 3:
                state_now = controller.read_chip_state()
                if state_now["chip_id"] != initial_chip_id or state_now["state_nonce"] != initial_nonce:
                    status = 1
                    break

    if status == 0:
        queue_count = controller.strong_blob_count()
        mark_limit = 38 - recovery_count
        if saw_nonzero_blob_count and queue_count == 0:
            status = 3
        else:
            for index in range(16):
                if index < queue_count and index < mark_limit:
                    controller.mark_candidate_from_blob(index)
            for offset in range(16):
                index = offset + 16
                if index < queue_count and index < mark_limit:
                    controller.mark_candidate_from_blob(index)
            for offset in range(6):
                index = offset + 32
                if index < queue_count and index < mark_limit:
                    controller.mark_candidate_from_blob(index)
    else:
        queue_count = controller.strong_blob_count()
        mark_limit = 38 - recovery_count
        for index in range(16):
            if index < queue_count and index < mark_limit:
                controller.mark_candidate_from_blob(index)
        for offset in range(16):
            index = offset + 16
            if index < queue_count and index < mark_limit:
                controller.mark_candidate_from_blob(index)
        for offset in range(6):
            index = offset + 32
            if index < queue_count and index < mark_limit:
                controller.mark_candidate_from_blob(index)

    controller.complete_scan(status)
    controller.release()
