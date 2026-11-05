# Sandbox image the autograder runs student code in.
# Add the libraries your courses need (numpy etc.) here, then rebuild:
#   docker build -t lms-grader:latest grader
ARG BASE=python:3.12-slim
FROM ${BASE}
RUN pip install --no-cache-dir pytest==8.3.4 numpy==2.1.3
# Runs as "nobody" (uid 65534); the container is started read-only with no network.
USER 65534:65534
WORKDIR /tmp
