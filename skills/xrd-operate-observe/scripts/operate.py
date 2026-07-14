def run(controller):
    controller.reset()
    controller.select_calibrant("lab6")
    frame = controller.acquire_frame()
    controller.release()
    return {"case_id": frame["case_id"], "calibrant": frame["calibrant"]}
