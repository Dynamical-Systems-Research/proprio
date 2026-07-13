def run(controller):
    controller.reset()
    controller.full_auto_calibrate()
    sweep = controller.fast_autofocus(6800)
    correction = 0 - sweep["position_z"]
    if correction > 1000:
        correction = 1000
    if correction < -1000:
        correction = -1000
    if sweep["position_z"] > 400:
        correction = -300
    position = controller.move_z(correction)
    residual_correction = position["position_z"]
    if residual_correction > 1000:
        residual_correction = 1000
    if residual_correction < -1000:
        residual_correction = -1000
    final_position = controller.move_z(residual_correction)
    controller.settle()
    series = controller.capture_focus_series(3)
    controller.release()
    return {"sweep": sweep, "correction": correction, "position": position, "residual_correction": residual_correction, "final_position": final_position, "series": series}
