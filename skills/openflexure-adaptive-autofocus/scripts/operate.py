def run(controller):
    controller.reset()
    controller.full_auto_calibrate()
    sweep = controller.fast_autofocus(7000)
    probe = controller.move_z(100)
    correction = probe["position_z"]
    if probe["position_z"] > sweep["position_z"]:
        correction = 0 - probe["position_z"]
    if correction > 1000:
        correction = 1000
    if correction < -1000:
        correction = -1000
    final_position = controller.move_z(correction)
    controller.settle()
    series = controller.capture_focus_series(3)
    controller.release()
    return {"sweep": sweep, "probe": probe, "correction": correction, "final_position": final_position, "series": series}
