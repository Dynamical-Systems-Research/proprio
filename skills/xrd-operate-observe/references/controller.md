# SOURCE: XRD controller contract
# LaB6 calibrant acquisition

The simulator exposes a narrow controller for acquiring one raw two-dimensional
area-detector frame from the preregistered LaB6 calibrant. A drafted `skill.py`
must define exactly:

```python
def run(controller):
    ...
```

It may call only:

- `controller.reset()`
- `controller.select_calibrant(name)`
- `controller.acquire_frame()`
- `controller.release()`

Use the calibrant name `"lab6"`. Reset before selecting the calibrant. Acquire
exactly one frame, then release the detector session before returning. The
acquisition call returns a dictionary containing `case_id`, `calibrant`, and
`exposure_s`. Return a dictionary containing at least `case_id` and `calibrant`.

The drafted `SKILL.md` must state that admission depends on execution against
the raw-frame simulator and the independent preregistered metrology checks.
Model self-judgment is not the admission authority. Simulation verification is
not hardware qualification and does not validate phase assignment or another
scientific interpretation of an unknown sample.
