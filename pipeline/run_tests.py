"""Run every pipeline test without needing pytest. Exit code 1 if any fails.   python pipeline/run_tests.py"""
import glob, importlib, inspect, os, sys, tempfile, pathlib, traceback
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
bad = n = 0
for f in sorted(glob.glob(os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_*.py"))):
    m = importlib.import_module(os.path.basename(f)[:-3])
    for k, fn in sorted(vars(m).items()):
        if not (k.startswith("test_") and callable(fn)): continue
        need = [p for p, v in inspect.signature(fn).parameters.items() if v.default is inspect.Parameter.empty]
        try:
            fn(*[pathlib.Path(tempfile.mkdtemp()) for _ in need]); n += 1          # a required argument is a temp folder
        except Exception:
            bad += 1; print(f"FAILED {m.__name__}.{k}"); traceback.print_exc()
print(f"{n} tests passed, {bad} failed")
sys.exit(1 if bad else 0)
