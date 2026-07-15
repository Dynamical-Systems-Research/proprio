def run(controller):
    controller.reset()

    initial_state = controller.read_chip_state()
    baseline_nonce = initial_state["state_nonce"]

    calibration_ok = controller.calibrate_region()

    saw_blobs = False
    abort_code = 0
    if not calibration_ok:
        abort_code = 4

    for iy in range(4):
        if abort_code != 0:
            break

        for ix in range(4):
            controller.move_to_tile(ix, iy)

            focus_score = controller.autofocus()
            if focus_score < 0.70:
                focus_score = controller.autofocus()
                if focus_score < 0.70:
                    abort_code = 2
                    break

            blob_count = controller.capture_tile()
            if blob_count > 0:
                saw_blobs = True

        if abort_code == 2:
            break

        if abort_code == 0:
            row_state = controller.read_chip_state()
            if row_state["state_nonce"] != baseline_nonce:
                abort_code = 1
                break

    count = controller.strong_blob_count()

    if abort_code == 0:
        if saw_blobs and count == 0:
            abort_code = 3

    if abort_code != 3:
        for i in range(16):
            if i >= count:
                break
            controller.mark_candidate_from_blob(i)

    controller.complete_scan(abort_code)
    controller.release()

    return {"status_code": abort_code}
