# Invalidated sequential pilot

This run was interrupted after four cases because a single external simulator serialized the
entire 60-case battery. It is excluded from all metrics. The replacement run assigns each case
to one of four isolated OpenFlexure server processes; each process still executes its cases
sequentially with a full reset.
