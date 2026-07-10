def run(controller):
    controller.reset()
    controller.calibrate_channel('A', 0.040)
    controller.calibrate_channel('B', 0.050)
    controller.prime_channel('A', 60)
    controller.prime_channel('B', 60)
    controller.pump_volume('A', 60, 6.0)
    controller.pump_volume('B', 60, 4.0)
    controller.halt_all()
    return {}
