def run(controller):
    controller.reset()
    controller.connect()
    limits = controller.get_limits()
    max_scan_rate = limits["maximum_scan_rate_v_s"]
    offset = controller.read_zero_offset()
    controller.set_zero_compensation(offset)
    probe = controller.potential_cycle(0.0, -0.5, 0.5, 0.0, max_scan_rate, 1, 0.02)
    probe_min = probe["potential_min_v"]
    probe_max = probe["potential_max_v"]
    lower_v = 0.25 / probe_min
    upper_v = 0.25 / probe_max
    frame = controller.potential_cycle(0.0, lower_v, upper_v, 0.0, max_scan_rate, 1, 0.02)
    controller.disconnect()
    return {"frame": frame}
