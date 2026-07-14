def run(controller):
    controller.reset()
    controller.set_temperature(80.0)
    controller.wait_for_temperature(200.0, 0.5)
    controller.hold(600.0)
    controller.deactivate()
    return {}
