def run(controller):
    controller.reset()
    controller.open_tray()
    controller.load_plate()
    controller.close_tray()
    blank = controller.read_fluorescence_blank(485, 520, 7)
    sample = controller.read_fluorescence(485, 520, 7)
    controller.open_tray()
    controller.unload_plate()
    controller.shutdown()
    return {"blank": blank, "sample": sample}
