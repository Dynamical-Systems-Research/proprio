def run(controller):
    controller.reset()
    controller.open_tray()
    controller.load_plate()
    controller.close_tray()
    blank = controller.read_blank(600, 100)
    sample = controller.read_absorbance(600, 100)
    controller.open_tray()
    controller.unload_plate()
    controller.shutdown()
    return {'blank_absorbance': blank, 'sample_absorbance': sample}
