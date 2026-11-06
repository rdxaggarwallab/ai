# Sandbox image the autograder runs student code in.
# Add the libraries your courses need (numpy etc.) here, then rebuild:
#   docker build -t lms-grader:latest grader
ARG BASE=python:3.12-slim
FROM ${BASE}
RUN pip install --no-cache-dir pytest==8.3.4 numpy==2.1.3
# The harness runs the hidden tests and talks to the student's code in a separate process
# under a different user. It starts as root only to switch users, then drops to uid 65533.
COPY harness.py /opt/grader/harness.py
RUN chmod 0444 /opt/grader/harness.py
WORKDIR /tmp
