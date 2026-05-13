#!/usr/bin/env python3
# bal — LLM Backend Launcher
# Backwards-compat shim: delegates to the bal package.
# Prefer running as: bal <args> or python -m bal <args>

from bal import main

if __name__ == "__main__":
    main()
