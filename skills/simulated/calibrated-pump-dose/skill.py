def run(controller):
    controller.reset()
    controller.calibrate(0.050)
    controller.prime(75)
    controller.pump_volume(75, 10.0)
    controller.halt()
    return {}
