def run(controller):
    controller.reset()
    controller.full_auto_calibrate()
    autofocus = controller.fast_autofocus(4000)
    controller.settle()
    series = controller.capture_focus_series(3)
    controller.release()
    return {"autofocus": autofocus, "series": series}
