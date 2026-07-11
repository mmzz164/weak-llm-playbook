#!/usr/bin/env python3
"""The whole loop in ~10 seconds, offline — no model, no GPU, no API key.

Starts a deterministic mock "weak model" (it alternates between two plausible
implementations of top_n: value-sorted vs first-n), then runs the real
pipeline (selffix.py --run) against it. Watch it:

  1. detect the divergence   (the spec hole you didn't know you left)
  2. pin the behavior        (revised prompt, alternatives kept as comments)
  3. re-probe                (verify the ambiguity is gone: holes 2 -> 0)
  4. execute + replay-verify (artifact reproduces every measured behavior)

Everything printed is exactly what a real endpoint would produce.

usage: python3 demo/demo.py
"""
import os
import socket
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(HERE), "skill", "weak-llm-playbook", "scripts")

DRAFT = "Implement top_n(lst, n) that returns the top n items of the numeric list lst."
INPUTS = "[[[3,1,2],2],[[],2],[[5],2],[[2,2,1],2],[[3,1,2],0],[[3,1,2],-1]]"


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def main():
    port = free_port()
    srv = subprocess.Popen([sys.executable, os.path.join(HERE, "mock_model.py")],
                           env=dict(os.environ, PORT=str(port)))
    try:
        time.sleep(0.8)
        with tempfile.TemporaryDirectory() as td:
            draft = os.path.join(td, "draft.txt")
            inputs = os.path.join(td, "inputs.json")
            open(draft, "w").write(DRAFT)
            open(inputs, "w").write(INPUTS)
            print(f"== the draft you might have written ==\n{DRAFT}\n")
            print("== running the real pipeline against a deterministic mock model ==\n")
            rc = subprocess.run([sys.executable, os.path.join(SCRIPTS, "selffix.py"),
                                 draft, inputs, f"http://127.0.0.1:{port}", "--run"]).returncode
            print(f"\ndemo exit code: {rc} (0 = hole found, pinned, verified, executed, "
                  "replay-verified)")
            return rc
    finally:
        srv.kill()


if __name__ == "__main__":
    sys.exit(main())
