def run(controller):
    controller.reset()
    controller.full_auto_calibrate()
    autofocus = controller.fast_autofocus(7000)
    correction = controller.move_z(0 - autofocus["position_z"])
    controller.settle()
    series = controller.capture_focus_series(3)
    controller.release()
    return {"autofocus": autofocus, "correction": correction, "series": series}
