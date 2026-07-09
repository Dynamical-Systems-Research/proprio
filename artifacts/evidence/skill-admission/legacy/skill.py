def run(controller):
    controller.reset()
    controller.set_current_limit(200e-6)
    controller.set_measurement_range(100e-6)
    controller.set_voltage(1.000)
    controller.enable_output()
    current_a = controller.measure_current()
    controller.disable_output()
    return {'current_a': current_a}
