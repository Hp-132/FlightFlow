"""Run in a subprocess by test_crash_injection.py: processes exactly one
saga step message, guaranteed to hard-crash (os._exit) at the point named
in REFLIGHT_FORCE_CRASH_AT before it can finish -- proving the parent
test's subsequent redelivery is what actually completes the step.
"""

import json
import sys

from reflight.worker.main import _handle_message

if __name__ == "__main__":
    saga_id, step = sys.argv[1], sys.argv[2]
    _handle_message(json.dumps({"saga_id": saga_id, "step": step}).encode())
    print("did not crash -- REFLIGHT_FORCE_CRASH_AT was not honored")
    sys.exit(0)
