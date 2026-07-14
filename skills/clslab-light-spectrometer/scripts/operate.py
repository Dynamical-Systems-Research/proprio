def run(controller):
    controller.reset()
    limits = controller.get_limits()
    max_signal_limit = limits['maximum_signal']
    max_gain = limits['maximum_gain']

    if limits['maximum_signal'] >= 40000:
        gain = 64
    else:
        gain = 16

    controller.configure(100, 999, gain)
    controller.set_rgb(40, 60, 20)
    result = controller.measure()

    for _ in range(8):
        if result['maximum_signal'] > max_signal_limit:
            gain = gain / 2
            controller.configure(100, 999, gain)
            result = controller.measure()
        elif result['minimum_signal'] < 1:
            gain = gain * 2
            if gain > max_gain:
                gain = max_gain
            controller.configure(100, 999, gain)
            result = controller.measure()

    controller.clear()

    return {
        'spectrum': result['spectrum'],
        'minimum_signal': result['minimum_signal'],
        'maximum_signal': result['maximum_signal'],
        'channels': result['channels']
    }
