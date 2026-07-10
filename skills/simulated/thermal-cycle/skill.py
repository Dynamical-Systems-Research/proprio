def run(controller):
    controller.reset()
    controller.set_temperature(60.0)
    controller.wait_for_temperature(240.0, 0.5)
    controller.hold(300.0)
    controller.set_temperature(20.0)
    controller.wait_for_temperature(240.0, 0.5)
    controller.hold(120.0)
    controller.deactivate()
    return {}
