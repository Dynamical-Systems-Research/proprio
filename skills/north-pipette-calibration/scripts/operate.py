def run(controller):
    controller.reset()
    info = controller.sample_info()
    target = info['target_volume_ml']
    liquid = info['liquid']

    # Read capacity constraints to respect reported tip-capacity bound
    controller.get_constraints(target)

    # Select initial overaspiration based on liquid type (starting calibration ratios)
    if liquid == 'water':
        overaspirate = 0.025 * target
    else:
        overaspirate = 0.0625 * target

    # Perform measurement with 3 replicates at starting conditions
    result = controller.measure(target, overaspirate, 20, 1, 3)

    # Check qualification and revise if accuracy or repeatability is unacceptable
    if result['relative_error'] > 0.04 or result['coefficient_of_variation'] > 0.05:
        overaspirate = overaspirate * (target / result['mean_volume_ml'])
        result = controller.measure(target, overaspirate, 20, 1, 3)

    controller.cleanup()
    return result
