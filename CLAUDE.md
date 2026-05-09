# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

This repository is currently empty. Update this file once the project structure is established.

# Programming Language
Python 3 is used for this codebase.
Only default libraries are allowed by default. Any additional installations should be approved by a developer.

# code style guide and code review
Use standard pip-8 style guide, do not try to limit strings len by 80 characters in a line, instead, use 120.
Magic numners are not allowed, prefer variables or function/method parameters with default values.
Global variables should not be declared inside functions/methods. 
Prefer spaces, not tabs.
Humans and LLMs will be reading this code and documentation, keep it as clear as possible.
Prefer to have short 20-30 lines functions/methods. You can go up to 40-50 lines when extraction of sume functioanlity as a separate function takes 1-3 lines of code. 
Prefer to reuse code instad of duplicating the existing code.
