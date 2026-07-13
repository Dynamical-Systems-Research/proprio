def run(controller):
    controller.reset()
    controller.full_auto_calibrate()
    autofocus = controller.fast_autofocus(6750)
    correction = controller.move_z((0 - autofocus["position_z"]) + 100)
    if correction["position_z"] > 100:
        correction = controller.move_z(correction["position_z"] - 100)
    controller.settle()
    series = controller.capture_focus_series(3)
    controller.release()
    return {"autofocus": autofocus, "correction": correction, "series": series}
