# data/samples (git-ignored)

Optional place to keep your own **real** input files before you add them in the app.
Nothing here is committed. The app never uses this folder by itself: add files through the Library page
or `python -m app.cli add-file`, which copies them into `data/originals/` (read-only).

Synthetic test inputs are no longer generated here: the automated tests build their own tiny inputs
in a temporary folder (`pipeline/tests/synthetic_samples.py`).
