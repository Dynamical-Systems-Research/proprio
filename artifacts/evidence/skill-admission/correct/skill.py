def run(controller):
    controller.reset()
    controller.set_current_limit(0.002)
    controller.set_measurement_range(0.01)
    controller.set_voltage(1.0)
    controller.enable_output()
    current_a = controller.measure_current()
    controller.disable_output()
    return {'current_a': current_a}
