# Container-image Lambda instead of a zip + layer: Pillow ships compiled
# C extensions that have to match the Lambda execution environment
# exactly, and public Pillow layers are a moving target across regions
# and Python versions. Building on the official base image guarantees the
# binary matches, with no layer ARN to hunt down.
FROM public.ecr.aws/lambda/python:3.13

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY handler.py ${LAMBDA_TASK_ROOT}

CMD ["handler.handler"]
