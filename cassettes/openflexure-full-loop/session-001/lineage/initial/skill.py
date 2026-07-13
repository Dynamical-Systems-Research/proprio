def run(controller):
    controller.reset()
    controller.full_auto_calibrate()
    sweep = controller.fast_autofocus(8000)
    correction = 0 - sweep["position_z"]
    if correction > 1000:
        correction = 1000
    if correction < -1000:
        correction = -1000
    position = controller.move_z(correction)
    controller.settle()
    series = controller.capture_focus_series(5)
    controller.release()
    return {"sweep": sweep, "correction": correction, "position": position, "series": series}
